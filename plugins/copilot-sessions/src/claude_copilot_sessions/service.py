"""Read Copilot CLI sessions from disk and apply scoping.

Like Codex, Copilot CLI keeps no database this importer needs to open:
every session directory under ``<copilot home>/session-state/`` is
self-contained (``workspace.yaml`` + ``events.jsonl``). Reading is a
straight filesystem walk, read-only, with a small cache so ``list`` and
``import`` in the same process don't reparse a session twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .locate import find_sessions_dir, session_dirs
from .models import Message, Session
from .parse import parse_session
from .scope import Scope

__all__ = ["Listing", "Reader", "open_reader"]


@dataclass
class Listing:
    shown: list[Session]


@dataclass
class Reader:
    """Sessions under one Copilot home directory (``<home>/session-state``)."""

    home: Path
    notes: list[str] = field(default_factory=list)
    _cache: dict[str, tuple[Session, list[Message]]] = field(
        default_factory=dict, repr=False
    )

    @property
    def sessions_dir(self) -> Path:
        return self.home / "session-state"

    def describe(self) -> str:
        return f"session directories · {_tilde(self.sessions_dir)}"

    def _load(self) -> dict[str, tuple[Session, list[Message]]]:
        if self._cache:
            return self._cache
        unreadable = 0
        for path in session_dirs(self.sessions_dir):
            parsed = parse_session(path)
            if parsed is None:
                unreadable += 1
                continue
            session, messages = parsed
            self._cache[session.id] = (session, messages)
        if unreadable:
            self.notes.append(f"{unreadable} session(s) could not be parsed")
        return self._cache

    def all_sessions(self) -> list[Session]:
        sessions = [s for s, _ in self._load().values()]
        sessions.sort(key=lambda s: s.time_updated or 0, reverse=True)
        return sessions

    def listing(self, scope: Scope) -> Listing:
        return Listing(shown=scope.filter(self.all_sessions()))

    def messages(self, session: Session) -> list[Message]:
        cached = self._load().get(session.id)
        return cached[1] if cached else []


def _tilde(path: Path) -> str:
    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)


def open_reader(copilot_home: str | None = None) -> Reader:
    """Open the Copilot CLI sessions directory (raises if it doesn't exist)."""
    sessions_dir = find_sessions_dir(copilot_home)
    return Reader(sessions_dir.parent)
