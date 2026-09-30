"""Locate Codex CLI's session files.

Codex (https://developers.openai.com/codex) keeps one JSONL "rollout" file
per session under ``$CODEX_HOME/sessions/<year>/<month>/<day>/``, plus a
best-effort ``session_index.jsonl`` with titles for some of them. There is no
database and no CLI export command to fall back on: the rollout files
themselves are the only source of truth, and they are read strictly
read-only.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .errors import SessionsDirNotFoundError

__all__ = [
    "ENV_VAR",
    "codex_home",
    "find_sessions_dir",
    "rollout_files",
    "session_index",
]

ENV_VAR = "CODEX_HOME"


def codex_home(explicit: str | os.PathLike[str] | None = None) -> Path:
    """``$CODEX_HOME``, an explicit override, or ``~/.codex``."""
    if explicit:
        return Path(explicit).expanduser()
    env = os.environ.get(ENV_VAR)
    if env:
        return Path(env).expanduser()
    return Path.home() / ".codex"


def find_sessions_dir(explicit: str | os.PathLike[str] | None = None) -> Path:
    """Return ``<codex home>/sessions`` or raise :class:`SessionsDirNotFoundError`."""
    home = codex_home(explicit)
    sessions = home / "sessions"
    if sessions.is_dir():
        return sessions
    raise SessionsDirNotFoundError(
        f"Codex sessions directory not found: {sessions}. "
        f"Is Codex CLI installed and has it been run at least once? "
        f"Set ${ENV_VAR} if Codex uses a non-default home."
    )


def rollout_files(sessions_dir: Path) -> list[Path]:
    """Every rollout JSONL file under ``sessions_dir``, in no particular order."""
    return sorted(sessions_dir.glob("**/rollout-*.jsonl"))


def session_index(home: Path) -> dict[str, dict[str, Any]]:
    """Best-effort ``session_id -> {"thread_name", "updated_at"}`` map.

    ``session_index.jsonl`` is an index Codex keeps for its own ``resume``
    picker; not every session is guaranteed to be listed there (e.g. very
    old or non-interactive ones), so this is used only to improve titles,
    never as the source of truth for which sessions exist.
    """
    path = home / "session_index.jsonl"
    index: dict[str, dict[str, Any]] = {}
    try:
        handle = path.open(encoding="utf-8")
    except OSError:
        return index
    with handle:
        for line in handle:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except ValueError:
                continue
            if isinstance(entry, dict) and entry.get("id"):
                index[str(entry["id"])] = entry
    return index
