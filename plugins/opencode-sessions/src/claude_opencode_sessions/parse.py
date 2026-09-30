"""Parsers turning opencode's stored JSON into :mod:`models` objects.

Two shapes exist:

* opencode 1.x (SQLite era, >= 1.2) and ``opencode export``: a message
  ``info`` object plus a list of ``part`` objects.
* opencode 2.x: one ``session_message`` row per event, with the role in the
  ``type`` column and a JSON ``data`` payload.

Every accessor is defensive: unknown shapes degrade to generic parts
instead of raising.
"""

from __future__ import annotations

import json
from typing import Any

from .models import Message, Part, format_model

__all__ = [
    "as_dict",
    "as_list",
    "loads",
    "parse_v1_message",
    "parse_v1_part",
    "parse_v2_row",
]

_SKIP_V1_PARTS = {"step-start", "step-finish", "snapshot"}


def as_dict(value: Any) -> dict[str, Any]:
    """``value`` if it is a dict, else an empty dict."""
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> list[Any]:
    """``value`` if it is a list, else an empty list."""
    return value if isinstance(value, list) else []


def loads(raw: Any) -> Any:
    """``json.loads`` that returns ``None`` instead of raising."""
    if raw is None:
        return None
    if isinstance(raw, (dict, list)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return None


def _str(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except (TypeError, ValueError):
        return str(value)


def _error_text(error: Any) -> str | None:
    if not error:
        return None
    if isinstance(error, dict):
        name = error.get("name") or "Error"
        data = error.get("data")
        message = data.get("message") if isinstance(data, dict) else None
        message = message or error.get("message")
        return f"{name}: {message}" if message else str(name)
    return _str(error)


def parse_v1_part(part: Any) -> Part | None:
    """Parse one 1.x ``part`` object. Returns ``None`` for bookkeeping parts."""
    if not isinstance(part, dict):
        return Part(kind="other", text=_str(part))
    kind = part.get("type") or "other"
    if kind in _SKIP_V1_PARTS:
        return None
    if kind in ("text", "reasoning"):
        return Part(
            kind=kind,
            text=_str(part.get("text")),
            synthetic=bool(part.get("synthetic") or part.get("ignored")),
        )
    if kind == "tool":
        state = as_dict(part.get("state"))
        output = state.get("output")
        if output is None and state.get("error") is not None:
            output = state.get("error")
        return Part(
            kind="tool",
            tool=_str(part.get("tool")) or "tool",
            tool_input=state.get("input"),
            tool_output=None if output is None else _str(output),
            status=state.get("status"),
            title=state.get("title"),
        )
    if kind == "file":
        name = part.get("filename") or part.get("url") or ""
        return Part(kind="file", text=_str(name), files=[_str(name)] if name else [])
    if kind == "patch":
        files = as_list(part.get("files"))
        return Part(kind="patch", files=[_str(f) for f in files])
    if kind == "compaction":
        return Part(kind="compaction")
    if kind in ("agent", "subtask"):
        text = part.get("prompt") or part.get("description") or part.get("name")
        return Part(kind=kind, text=_str(text))
    return Part(kind=_str(kind), text=_str(part.get("text")))


def parse_v1_message(info: Any, parts: list[Any], seq: int | None = None) -> Message:
    """Parse a 1.x message ``info`` object together with its parts."""
    info = info if isinstance(info, dict) else {}
    model = format_model(info.get("model"))
    if model is None and info.get("modelID"):
        model = format_model(
            {"id": info.get("modelID"), "providerID": info.get("providerID")}
        )
    time = as_dict(info.get("time"))
    tokens = as_dict(info.get("tokens")) or None
    cost = info.get("cost")
    parsed = [p for p in (parse_v1_part(raw) for raw in parts) if p is not None]
    return Message(
        id=_str(info.get("id")),
        role=_str(info.get("role")) or "unknown",
        time_created=time.get("created"),
        parts=parsed,
        seq=seq,
        model=model,
        agent=info.get("agent") or info.get("mode"),
        error=_error_text(info.get("error")),
        tokens=tokens,
        cost=cost if isinstance(cost, (int, float)) else None,
    )


def _v2_content_part(item: Any) -> Part | None:
    if isinstance(item, str):
        return Part(kind="text", text=item)
    if not isinstance(item, dict):
        return None
    kind = item.get("type")
    if kind in ("text", "reasoning") or (kind is None and "text" in item):
        return Part(
            kind=kind or "text",
            text=_str(item.get("text")),
            synthetic=bool(item.get("synthetic")),
        )
    is_tool = "tool" in item or (isinstance(kind, str) and kind.startswith("tool"))
    if is_tool:
        state = as_dict(item.get("state")) or item
        output = state.get("output", state.get("result"))
        if output is None and state.get("error") is not None:
            output = state.get("error")
        return Part(
            kind="tool",
            tool=_str(item.get("tool") or item.get("name")) or "tool",
            tool_input=state.get("input", state.get("args")),
            tool_output=None if output is None else _str(output),
            status=state.get("status"),
            title=state.get("title"),
        )
    return parse_v1_part(item)


def parse_v2_row(
    row_id: str,
    row_type: str,
    data_raw: Any,
    seq: int | None,
    time_created: int | None,
) -> tuple[Message, bool]:
    """Parse one 2.x ``session_message`` row.

    Returns the message and whether its JSON payload parsed cleanly.
    """
    data = loads(data_raw)
    ok = isinstance(data, dict)
    data = data if isinstance(data, dict) else {}

    parts: list[Part] = []
    text = data.get("text")
    if isinstance(text, str) and text:
        parts.append(Part(kind="text", text=text, synthetic=row_type == "synthetic"))
    for key in ("content", "parts"):
        value = data.get(key)
        if isinstance(value, str) and value:
            parts.append(Part(kind="text", text=value))
        elif isinstance(value, list):
            parts.extend(p for p in map(_v2_content_part, value) if p is not None)
    if "tool" in data and not parts:
        tool_part = _v2_content_part(data)
        if tool_part is not None:
            parts.append(tool_part)
    if not ok:
        parts.append(Part(kind="other", text="[unparseable message payload]"))

    model = format_model(data.get("model"))
    if model is None and data.get("modelID"):
        model = format_model(
            {"id": data.get("modelID"), "providerID": data.get("providerID")}
        )
    tokens = as_dict(data.get("tokens")) or None
    cost = data.get("cost")
    message = Message(
        id=row_id,
        role=row_type or "unknown",
        time_created=time_created,
        parts=parts,
        seq=seq,
        model=model,
        agent=data.get("agent"),
        error=_error_text(data.get("error")),
        tokens=tokens,
        cost=cost if isinstance(cost, (int, float)) else None,
    )
    return message, ok
