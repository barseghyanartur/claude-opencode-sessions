"""Parse Codex CLI rollout JSONL files into :mod:`models` objects.

Each file is a sequence of JSON lines shaped like
``{"timestamp": ..., "ordinal": ..., "type": ..., "payload": {...}}``. The
top-level ``type`` values read here: ``session_meta`` (once, the first
line), ``turn_context`` (model per turn) and ``response_item`` (the actual
conversation — ``message``, ``reasoning``, ``function_call`` /
``function_call_output``, and their ``local_shell_call`` / ``tool_search_*``
variants). ``event_msg`` and ``world_state`` lines carry no conversation
content on their own; only ``event_msg.task_started`` is read, for its
``collaboration_mode_kind`` (Codex's "default"/"plan" mode, stored as
``Session.agent``).

This is reverse-engineered from real rollout files (Codex CLI and Codex
Desktop, ``cli_version`` 0.141-0.159) rather than from a published schema,
so every accessor is defensive: an unparseable line, or a shape this module
doesn't recognise, is skipped instead of raising.

Known gap: Codex injects some context as plain, untagged user text (an
``# AGENTS.md instructions for ...`` header, IDE "Active file" context,
"Files mentioned by the user" lists). Only content wrapped in a recognised
``<tag>...`` block (``_SYNTHETIC_USER_TAGS``) is filtered out; the rest is
imported verbatim, same as a real user message.
"""

from __future__ import annotations

import contextlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import Message, Part, Session

__all__ = ["derive_title", "parse_rollout", "parse_timestamp"]

_SYNTHETIC_USER_TAGS = {
    "environment_context",
    "user_instructions",
    "recommended_plugins",
    "apps_instructions",
    "skills_instructions",
    "plugins_instructions",
    "collaboration_mode",
    "app-context",
    "turn_aborted",
    "skill",
}
_CALL_TYPES = {"function_call", "local_shell_call", "tool_search_call"}
_CALL_OUTPUT_TYPES = {
    "function_call_output",
    "local_shell_call_output",
    "tool_search_output",
}


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


def _leading_tag(text: str) -> str | None:
    """The tag name of a string starting with ``<tag>`` or ``<tag ...>``."""
    text = text.strip()
    if not text.startswith("<"):
        return None
    end = min((i for i in (text.find(">"), text.find(" ")) if i != -1), default=-1)
    return text[1:end] if end > 1 else None


def _content_text(content: Any, role: str) -> str:
    if not isinstance(content, list):
        return ""
    chunks: list[str] = []
    for item in content:
        text: Any
        if isinstance(item, str):
            text = item
        elif isinstance(item, dict):
            text = item.get("text")
        else:
            continue
        if not isinstance(text, str) or not text.strip():
            continue
        text = text.strip()
        if role == "user" and _leading_tag(text) in _SYNTHETIC_USER_TAGS:
            continue
        chunks.append(text)
    return "\n\n".join(chunks)


def _parse_message(
    payload: dict[str, Any], ordinal: int, ts: int | None
) -> Message | None:
    role = payload.get("role")
    if role not in ("user", "assistant"):
        return None  # "developer" (and anything else) carries no user content
    text = _content_text(payload.get("content"), role)
    if not text:
        return None
    return Message(
        id=str(payload.get("id") or f"{role}_{ordinal}"),
        role=role,
        time_created=ts,
        seq=ordinal,
        parts=[Part(kind="text", text=text)],
    )


def _reasoning_text(payload: dict[str, Any]) -> str:
    chunks = []
    for item in payload.get("summary") or []:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            chunks.append(item["text"])
    return "\n".join(chunks)


def _parse_call(payload: dict[str, Any], item_type: str) -> Part:
    name = payload.get("name") or (
        "shell" if item_type == "local_shell_call" else "tool_search"
    )
    args: Any = payload.get("arguments", payload.get("action"))
    if isinstance(args, str):
        with contextlib.suppress(ValueError):
            args = json.loads(args)  # falls back to the raw string on failure
    return Part(kind="tool", tool=str(name), tool_input=args, status="pending")


def parse_rollout(path: Path) -> tuple[Session, list[Message]] | None:
    """Parse one rollout file, or ``None`` if it isn't a Codex rollout."""
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return None

    session_id: str | None = None
    directory = ""
    time_created: int | None = None
    time_updated: int | None = None
    cli_version: Any = None
    source: Any = None
    agent: str | None = None
    model: str | None = None
    messages: list[Message] = []
    pending_tools: dict[str, Part] = {}
    ordinal = 0
    text_messages = 0

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
            payload = entry.get("payload")
            payload = payload if isinstance(payload, dict) else {}
            ts = parse_timestamp(entry.get("timestamp"))
            if ts is not None:
                time_updated = ts

            if kind == "session_meta":
                session_id = str(payload.get("session_id") or payload.get("id") or "")
                directory = str(payload.get("cwd") or "")
                cli_version = payload.get("cli_version")
                source = payload.get("source")
                time_created = parse_timestamp(payload.get("timestamp")) or ts
                continue

            if kind == "turn_context":
                if payload.get("model"):
                    model = str(payload["model"])
                continue

            if kind == "event_msg":
                if payload.get("type") == "task_started" and payload.get(
                    "collaboration_mode_kind"
                ):
                    agent = str(payload["collaboration_mode_kind"])
                continue

            if kind != "response_item":
                continue
            item_type = payload.get("type")
            ordinal += 1

            if item_type == "message":
                message = _parse_message(payload, ordinal, ts)
                if message is not None:
                    messages.append(message)
                    text_messages += 1
                continue

            if item_type == "reasoning":
                text = _reasoning_text(payload)
                if text:
                    messages.append(
                        Message(
                            id=str(payload.get("id") or f"reasoning_{ordinal}"),
                            role="assistant",
                            time_created=ts,
                            seq=ordinal,
                            parts=[Part(kind="reasoning", text=text)],
                        )
                    )
                continue

            if item_type in _CALL_TYPES:
                call_id = str(payload.get("call_id") or payload.get("id") or ordinal)
                part = _parse_call(payload, item_type)
                pending_tools[call_id] = part
                messages.append(
                    Message(
                        id=str(payload.get("id") or call_id),
                        role="assistant",
                        time_created=ts,
                        seq=ordinal,
                        parts=[part],
                    )
                )
                continue

            if item_type in _CALL_OUTPUT_TYPES:
                call_id = str(payload.get("call_id") or payload.get("id") or "")
                pending = pending_tools.get(call_id)
                if pending is not None:
                    pending.tool_output = _str(payload.get("output"))
                    pending.status = "completed"
                continue
            # An unrecognised response_item type carries no known content.

    if session_id is None:
        return None
    session = Session(
        id=session_id,
        title=session_id,
        directory=directory,
        time_created=time_created,
        time_updated=time_updated or time_created,
        agent=agent,
        model=model,
        version=str(cli_version) if cli_version else None,
        source=str(source) if source else None,
        message_count=text_messages,
    )
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
