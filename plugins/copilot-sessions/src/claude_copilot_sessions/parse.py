"""Parse GitHub Copilot CLI session directories into :mod:`models` objects.

A session is a directory, ``<copilot home>/session-state/<uuid>/``, holding
``workspace.yaml`` (directory, title, timestamps — read by :mod:`locate`)
and ``events.jsonl``: one JSON object per line, shaped like
``{"type": ..., "data": {...}, "id": ..., "timestamp": ..., "parentId": ...}``.

The event types read here:

* ``user.message`` — ``data.content`` is the raw text the user typed.
  ``data.transformedContent`` (what's actually sent to the model, wrapped
  in a ``<current_datetime>`` block and similar) is not used.
* ``assistant.message`` — one per model step; ``data.content`` is its text
  (often empty when the step is pure tool calls) and ``data.toolRequests``
  is a list of tool calls made in that step. ``data.reasoningText`` is
  dropped, like Claude Code's own thinking blocks.
* ``tool.execution_complete`` — paired with a pending tool call by
  ``toolCallId``, filling in its output and status.
* ``system.message`` (the system prompt) and every other event type
  (``session.*``, ``model.*``, ``permission.*``, ``tool.execution_start``,
  ``assistant.turn_*``) carry no conversation content on their own and are
  skipped.

This is reverse-engineered from real session files (Copilot CLI 1.0.90),
not a published schema, so every accessor is defensive.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .locate import read_workspace_yaml
from .models import Message, Part, Session

__all__ = ["derive_title", "parse_session", "parse_timestamp"]


def parse_timestamp(value: Any) -> int | None:
    """ISO-8601 ``"...Z"`` timestamp -> epoch milliseconds, or ``None``."""
    if not isinstance(value, str) or not value:
        return None
    text = value[:-1] + "+00:00" if value.endswith("Z") else value
    try:
        moment = datetime.fromisoformat(text)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return int(moment.timestamp() * 1000)


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _parse_user_message(
    payload: dict[str, Any], ordinal: int, ts: int | None
) -> Message | None:
    text = _str(payload.get("content")).strip()
    if not text:
        return None
    return Message(
        id=str(payload.get("messageId") or f"user_{ordinal}"),
        role="user",
        time_created=ts,
        seq=ordinal,
        parts=[Part(kind="text", text=text)],
    )


def _parse_tool_request(request: Any) -> tuple[str, Part] | None:
    if not isinstance(request, dict):
        return None
    call_id = request.get("toolCallId")
    if not call_id:
        return None
    return str(call_id), Part(
        kind="tool",
        tool=str(request.get("name") or "tool"),
        tool_input=request.get("arguments"),
        status="pending",
    )


def _parse_assistant_message(
    payload: dict[str, Any], ordinal: int, ts: int | None
) -> tuple[Message, dict[str, Part], bool] | None:
    """Returns the message, its tool calls keyed by ``toolCallId``, and
    whether it carried real text (as opposed to being tool-calls-only)."""
    text = _str(payload.get("content")).strip()
    pending: dict[str, Part] = {}
    parts: list[Part] = []
    if text:
        parts.append(Part(kind="text", text=text))
    for request in payload.get("toolRequests") or []:
        parsed = _parse_tool_request(request)
        if parsed is None:
            continue
        call_id, part = parsed
        parts.append(part)
        pending[call_id] = part
    if not parts:
        return None
    message = Message(
        id=str(payload.get("messageId") or f"assistant_{ordinal}"),
        role="assistant",
        time_created=ts,
        seq=ordinal,
        parts=parts,
    )
    return message, pending, bool(text)


def _tool_output(payload: dict[str, Any]) -> str:
    result = payload.get("result")
    if isinstance(result, dict) and "content" in result:
        return _str(result["content"])
    return _str(result)


def parse_session(session_dir: Path) -> tuple[Session, list[Message]] | None:
    """Parse one session directory, or ``None`` if it isn't a Copilot session."""
    workspace = read_workspace_yaml(session_dir / "workspace.yaml")
    events_path = session_dir / "events.jsonl"
    try:
        handle = events_path.open(encoding="utf-8")
    except OSError:
        return None

    session_id = str(workspace.get("id") or session_dir.name)
    version: str | None = None
    model: str | None = None
    messages: list[Message] = []
    pending_tools: dict[str, Part] = {}
    ordinal = 0
    text_messages = 0
    time_updated: int | None = None

    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if not isinstance(entry, dict):
                continue
            kind = entry.get("type")
            payload = entry.get("data")
            payload = payload if isinstance(payload, dict) else {}
            ts = parse_timestamp(entry.get("timestamp"))
            if ts is not None:
                time_updated = ts
            ordinal += 1

            if kind == "session.start":
                version = payload.get("copilotVersion") or version
                continue

            if kind == "user.message":
                message = _parse_user_message(payload, ordinal, ts)
                if message is not None:
                    messages.append(message)
                    text_messages += 1
                continue

            if kind == "assistant.message":
                if payload.get("model"):
                    model = str(payload["model"])
                parsed = _parse_assistant_message(payload, ordinal, ts)
                if parsed is not None:
                    message, new_pending, had_text = parsed
                    messages.append(message)
                    pending_tools.update(new_pending)
                    if had_text:
                        text_messages += 1
                continue

            if kind == "tool.execution_complete":
                call_id = str(payload.get("toolCallId") or "")
                part = pending_tools.get(call_id)
                if part is not None:
                    part.tool_output = _tool_output(payload)
                    part.status = (
                        "completed" if payload.get("success", True) else "error"
                    )
                continue
            # system.message, session.*, model.*, permission.*, tool.execution_start,
            # assistant.turn_*: no content this importer reads on its own.

    if not events_path.exists():  # pragma: no cover - guarded by the open() above
        return None
    directory = str(workspace.get("cwd") or "")
    time_created = parse_timestamp(workspace.get("created_at"))
    session = Session(
        id=session_id,
        title=str(workspace.get("name") or ""),
        directory=directory,
        time_created=time_created,
        time_updated=parse_timestamp(workspace.get("updated_at"))
        or time_updated
        or time_created,
        model=str(model) if model else None,
        version=version,
        source=str(workspace.get("client_name"))
        if workspace.get("client_name")
        else None,
        message_count=text_messages,
    )
    if not session.title:
        session.title = derive_title(messages) or session.id
    return session, messages


def derive_title(messages: list[Message], limit: int = 80) -> str | None:
    """The first line of the first user message, as a fallback title."""
    for message in messages:
        if message.role != "user" or not message.parts:
            continue
        text = message.parts[0].text.strip()
        if not text:
            continue
        line = text.splitlines()[0].strip()
        if not line:
            continue
        return line[:limit].rstrip() + ("…" if len(line) > limit else "")
    return None
