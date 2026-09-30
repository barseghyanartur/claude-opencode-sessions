"""Locate GitHub Copilot CLI's session files.

Copilot CLI (https://github.com/github/copilot-cli) keeps one directory per
session under ``$COPILOT_HOME/session-state/<uuid>/``: a ``workspace.yaml``
with the session's directory, title and timestamps, and an
``events.jsonl`` with the conversation itself. There's also a
``session-store.db`` SQLite index, but every field this importer needs is
already in the two per-session files, so the database is never opened —
read-only, no database, no CLI call.
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .errors import SessionsDirNotFoundError

__all__ = [
    "ENV_VAR",
    "copilot_home",
    "find_sessions_dir",
    "read_workspace_yaml",
    "session_dirs",
]

ENV_VAR = "COPILOT_HOME"


def copilot_home(explicit: str | os.PathLike[str] | None = None) -> Path:
    """``$COPILOT_HOME``, an explicit override, or ``~/.copilot``."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".copilot"


def find_sessions_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Return ``<copilot home>/session-state`` or raise."""
    home = copilot_home(explicit)
    sessions = home / "session-state"
    if sessions.is_dir():
        return sessions
    raise SessionsDirNotFoundError(
        f"Copilot CLI session-state directory not found: {sessions}. "
        f"Is the Copilot CLI (`copilot`) installed and has it been run at "
        f"least once? Set ${ENV_VAR} if it uses a non-default home."
    )


def session_dirs(sessions_dir: Path) -> list[Path]:
    """Every session directory under ``sessions_dir`` that has an events log."""
    if not sessions_dir.is_dir():
        return []
    return sorted(
        p
        for p in sessions_dir.iterdir()
        if p.is_dir() and (p / "events.jsonl").is_file()
    )


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
        return value[1:-1]
    return value


def read_workspace_yaml(path: Path) -> dict[str, Any]:
    """Best-effort flat-scalar reader for ``workspace.yaml``.

    Every field this importer reads (``id``, ``cwd``, ``name``,
    ``client_name``, ``created_at``, ``updated_at``) is a plain
    ``key: value`` scalar line, so a minimal line parser is used instead of
    adding a YAML dependency. A line this doesn't understand (a list, a
    nested map) is skipped rather than raised on.
    """
    data: dict[str, Any] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return data
    for line in text.splitlines():
        stripped = line.strip()
        if (
            not stripped
            or stripped.startswith("#")
            or line.startswith((" ", "\t", "-"))
        ):
            continue  # nested/indented value or list item: not a field we read
        key, sep, value = stripped.partition(":")
        if not sep:
            continue
        key = key.strip()
        value = _unquote(value)
        if value == "":
            continue
        if value in ("true", "false"):
            data[key] = value == "true"
        else:
            data[key] = value
    return data
