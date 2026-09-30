"""Plain-text / Markdown rendering helpers."""

from __future__ import annotations

import json
import os
import time
from datetime import datetime

from .models import Part, Session
from .scope import Scope, normalize

__all__ = [
    "absolute_time",
    "cell",
    "display_dir",
    "relative_time",
    "render_list",
    "tilde",
    "tool_summary",
    "truncate",
]


def _now_ms() -> int:
    return int(time.time() * 1000)


def relative_time(ms: int | None, now_ms: int | None = None) -> str:
    if not ms:
        return "?"
    now_ms = now_ms if now_ms is not None else _now_ms()
    delta = max(0, (now_ms - ms) // 1000)
    if delta < 60:
        return "just now"
    for size, unit in ((86400, "d"), (3600, "h"), (60, "m")):
        if delta >= size:
            if unit == "d" and delta >= 30 * 86400:
                return absolute_time(ms, date_only=True)
            return f"{delta // size}{unit} ago"
    return "just now"  # pragma: no cover


def absolute_time(ms: int | None, date_only: bool = False) -> str:
    if not ms:
        return "?"
    moment = datetime.fromtimestamp(ms / 1000)
    return moment.strftime("%Y-%m-%d" if date_only else "%Y-%m-%d %H:%M")


def truncate(text: str, limit: int) -> str:
    if limit <= 0 or len(text) <= limit:
        return text
    return text[:limit].rstrip() + f"\n… [{len(text) - limit} more chars]"


def cell(text: str, limit: int = 70) -> str:
    text = " ".join(str(text).split())
    if len(text) > limit:
        text = text[: limit - 1] + "…"
    return text.replace("|", "\\|")


def tilde(path: str) -> str:
    home = os.path.expanduser("~")
    if path == home or path.startswith(home + os.sep):
        return "~" + path[len(home) :]
    return path


def display_dir(directory: str, scope: Scope) -> str:
    if not directory:
        return "?"
    path = normalize(directory)
    if scope.mode != "all":
        for root in scope.roots:
            if path == root:
                return "." if root == scope.root else tilde(root)
            if path.startswith(root + os.sep):
                rel = os.path.relpath(path, root)
                return rel if root == scope.root else tilde(path)
    return tilde(path)


_INPUT_KEYS = (
    "filePath",
    "file_path",
    "path",
    "cmd",
    "command",
    "pattern",
    "url",
    "query",
    "description",
    "prompt",
)


def _first_line(value: str) -> str:
    lines = value.strip().splitlines()
    return (lines[0] + (" …" if len(lines) > 1 else "")) if lines else ""


def tool_summary(part: Part) -> str:
    """One-line description of a tool call."""
    name = part.tool or "tool"
    args = part.tool_input
    detail = ""
    if isinstance(args, dict):
        for key in _INPUT_KEYS:
            value = args.get(key)
            if isinstance(value, str) and value.strip():
                detail = _first_line(value)
                break
            # Codex's ``apply_patch`` shape: {"command": ["apply_patch", "<patch>"]}
            if (
                isinstance(value, list)
                and value
                and all(isinstance(v, str) for v in value)
            ):
                detail = _first_line(" ".join(value))
                break
        if not detail and args:
            detail = json.dumps(args, ensure_ascii=False)
    elif isinstance(args, str):
        detail = args.strip().splitlines()[0] if args.strip() else ""
    detail = cell(detail, 120).replace("\\|", "|")
    status = f" ({part.status})" if part.status and part.status != "completed" else ""
    return f"→ {name}: `{detail}`{status}" if detail else f"→ {name}{status}"


def render_list(
    sessions: list[Session],
    scope: Scope,
    *,
    total: int | None = None,
    backend: str = "",
    notes: list[str] | None = None,
    now_ms: int | None = None,
) -> str:
    lines = [f"Codex sessions — {scope.describe()}", ""]
    if not sessions:
        lines.append("No Codex sessions found in this scope.")
        if scope.mode == "worktree":
            lines.append("Try `--worktrees` (all worktrees) or `--all` (everything).")
    else:
        lines.append("| # | Title | Updated | Msgs | Agent · Model | Dir | ID |")
        lines.append("|---|---|---|---|---|---|---|")
        for index, s in enumerate(sessions, start=1):
            title = cell(s.title)
            agent = " · ".join(x for x in (s.agent, s.model) if x) or "?"
            msgs = "?" if s.message_count is None else str(s.message_count)
            where = cell(display_dir(s.directory, scope), 50)
            lines.append(
                f"| {index} | {title} | {relative_time(s.time_updated, now_ms)} | "
                f"{msgs} | {cell(agent, 50)} | {where} | `{s.id}` |"
            )
    footer = []
    if total is not None and total > len(sessions):
        footer.append(f"showing {len(sessions)} of {total} (use -n to show more)")
    if backend:
        footer.append(f"source: {backend}")
    lines.append("")
    lines.extend(f"_{line}_" for line in footer)
    lines.extend(f"_note: {note}_" for note in notes or [])
    return "\n".join(lines).rstrip() + "\n"
