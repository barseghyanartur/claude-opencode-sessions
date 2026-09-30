"""Locate opencode's SQLite database."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from .errors import DatabaseNotFoundError

__all__ = ["candidate_paths", "find_db", "opencode_db_path"]

ENV_VAR = "OPENCODE_SESSIONS_DB"
DB_NAME = "opencode.db"


def candidate_paths() -> list[Path]:
    """Default locations, most specific first (opencode uses XDG dirs)."""
    paths: list[Path] = []
    xdg = os.environ.get("XDG_DATA_HOME")
    if xdg:
        paths.append(Path(xdg) / "opencode" / DB_NAME)
    paths.append(Path.home() / ".local" / "share" / "opencode" / DB_NAME)
    for var in ("LOCALAPPDATA", "APPDATA"):
        base = os.environ.get(var)
        if base:
            paths.append(Path(base) / "opencode" / DB_NAME)
    unique: list[Path] = []
    for path in paths:
        if path not in unique:
            unique.append(path)
    return unique


def opencode_db_path(executable: str = "opencode", timeout: float = 15) -> Path | None:
    """Ask ``opencode db path`` (available in recent opencode versions)."""
    exe = shutil.which(executable)
    if not exe:
        return None
    try:
        result = subprocess.run(
            [exe, "db", "path"],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if result.returncode != 0:
        return None
    for line in reversed(result.stdout.strip().splitlines()):
        line = line.strip()
        if line.endswith(".db") and Path(line).is_file():
            return Path(line)
    return None


def find_db(
    explicit: str | os.PathLike[str] | None = None, ask_cli: bool = True
) -> Path:
    """Return the database path or raise :class:`DatabaseNotFoundError`.

    Order: explicit argument, ``$OPENCODE_SESSIONS_DB``, XDG/default paths,
    then ``opencode db path``.
    """
    if explicit:
        path = Path(explicit).expanduser()
        if path.is_file():
            return path
        raise DatabaseNotFoundError(f"opencode database not found: {path}")
    env = os.environ.get(ENV_VAR)
    if env:
        path = Path(env).expanduser()
        if path.is_file():
            return path
        raise DatabaseNotFoundError(f"{ENV_VAR} points to a missing file: {path}")
    for path in candidate_paths():
        if path.is_file():
            return path
    if ask_cli:
        path_from_cli = opencode_db_path()
        if path_from_cli:
            return path_from_cli
    searched = ", ".join(str(p) for p in candidate_paths())
    raise DatabaseNotFoundError(
        f"opencode database not found (looked in: {searched}). "
        "Is opencode >= 1.2 installed and has it been run at least once?"
    )
