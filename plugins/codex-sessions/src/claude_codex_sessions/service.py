"""Read Codex sessions from disk and apply scoping.

Unlike opencode, Codex keeps no database: every rollout file under
``<codex home>/sessions/`` is a complete, self-contained session. Reading
is a straight filesystem walk, read-only, with a small cache so ``list``
and ``import`` in the same process don't reparse a file twice.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .locate import find_sessions_dir, rollout_files, session_index
from .models import Message, Session
from .parse import derive_title, parse_rollout, parse_timestamp
from .scope import Scope

__all__ = ["Listing", "Reader", "open_reader"]


@dataclass
class Listing:
    shown: list[Session]


@dataclass
class Reader:
    """Sessions under one Codex home directory (``<home>/sessions``)."""

    home: Path
    notes: list[str] = field(default_factory=list)
    _cache: dict[str, tuple[Session, list[Message]]] = field(
        default_factory=dict, repr=False
    )

    @property
    def sessions_dir(self) -> Path:
        return self.home / "sessions"

    def describe(self) -> str:
        return f"rollout files · {_tilde(self.sessions_dir)}"

    def _load(self) -> dict[str, tuple[Session, list[Message]]]:
        if self._cache:
            return self._cache
        titles = session_index(self.home)
        unreadable = 0
        for path in rollout_files(self.sessions_dir):
            parsed = parse_rollout(path)
            if parsed is None:
                unreadable += 1
                continue
            session, messages = parsed
            entry = titles.get(session.id)
            title = (entry or {}).get("thread_name") or derive_title(messages)
            session.title = str(title) if title else session.id
            updated = parse_timestamp((entry or {}).get("updated_at"))
            if updated is not None:
                session.time_updated = updated
            self._cache[session.id] = (session, messages)
        if unreadable:
            self.notes.append(f"{unreadable} rollout file(s) could not be parsed")
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


def open_reader(codex_home: str | None = None) -> Reader:
    """Open the Codex sessions directory (raises if it doesn't exist)."""
    sessions_dir = find_sessions_dir(codex_home)
    return Reader(sessions_dir.parent)
