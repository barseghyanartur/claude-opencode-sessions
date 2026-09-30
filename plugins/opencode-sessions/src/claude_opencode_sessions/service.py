"""Glue between backends, scoping and the CLI."""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from .cli_backend import CliBackend
from .errors import (
    BackendError,
    OpencodeSessionsError,
)
from .locate import find_db
from .models import Message, Session
from .scope import Scope
from .sqlite_backend import SqliteBackend

__all__ = [
    "BACKENDS",
    "PARSE_ERROR_THRESHOLD",
    "Context",
    "Listing",
    "open_context",
]

BACKENDS = ("auto", "sqlite", "cli")
PARSE_ERROR_THRESHOLD = 0.2


@dataclass
class Listing:
    shown: list[Session]
    hidden_archived: int = 0
    hidden_subagents: int = 0


@dataclass
class Context:
    """An opened data source plus notes about how it was chosen."""

    mode: str
    sqlite: SqliteBackend | None = None
    cli: CliBackend | None = None
    notes: list[str] = field(default_factory=list)
    _cli_tried: bool = False

    @property
    def backend_name(self) -> str:
        return "sqlite" if self.sqlite else "cli"

    def describe(self) -> str:
        if self.sqlite:
            return f"sqlite ({self.sqlite.describe()}) · db: {_tilde(self.sqlite.path)}"
        assert self.cli is not None
        return f"cli ({self.cli.describe()})"

    def get_cli(self) -> CliBackend | None:
        if self.cli is None and not self._cli_tried and self.mode != "sqlite":
            self._cli_tried = True
            try:
                self.cli = CliBackend()
            except OpencodeSessionsError as exc:
                self.notes.append(f"cli unavailable: {exc}")
        return self.cli

    # -- sessions ---------------------------------------------------------

    def all_sessions(self, cwd: str | None = None) -> list[Session]:
        if self.sqlite:
            sessions = self.sqlite.list_sessions()
        else:
            assert self.cli is not None
            sessions = self.cli.list_sessions(cwd=cwd)
        sessions.sort(key=lambda s: s.time_updated or 0, reverse=True)
        return sessions

    def listing(
        self,
        scope: Scope,
        include_archived: bool = False,
        include_subagents: bool = False,
    ) -> Listing:
        scoped = scope.filter(self.all_sessions(cwd=scope.cwd))
        result = Listing(shown=[])
        for session in scoped:
            if session.is_archived and not include_archived:
                result.hidden_archived += 1
            elif session.is_subagent and not include_subagents:
                result.hidden_subagents += 1
            else:
                result.shown.append(session)
        return result

    # -- messages ---------------------------------------------------------

    def messages(self, session: Session) -> list[Message]:
        if self.sqlite:
            try:
                messages, errors = self.sqlite.load_messages(session.id)
            except sqlite3.Error as exc:
                messages, errors = [], -1
                self.notes.append(f"sqlite read failed: {exc}")
            broken = errors < 0 or (
                messages and errors / max(len(messages), 1) > PARSE_ERROR_THRESHOLD
            )
            if not broken:
                return messages
            cli = self.get_cli()
            if cli is None:
                if errors < 0:
                    raise BackendError("could not read messages; no fallback")
                self.notes.append(f"{errors} message(s) could not be parsed")
                return messages
            self.notes.append("fell back to `opencode export` for this session")
            return cli.load_messages(session.id)[0]
        assert self.cli is not None
        return self.cli.load_messages(session.id)[0]


def _tilde(path: Path) -> str:
    try:
        return "~/" + str(path.resolve().relative_to(Path.home().resolve()))
    except ValueError:
        return str(path)


def open_context(backend: str = "auto", db: str | None = None) -> Context:
    """Open the requested backend (``auto`` = sqlite, falling back to cli)."""
    if backend not in BACKENDS:
        raise ValueError(f"unknown backend {backend!r}")
    ctx = Context(mode=backend)
    if backend in ("auto", "sqlite"):
        try:
            ctx.sqlite = SqliteBackend(find_db(db))
            return ctx
        except (OpencodeSessionsError, sqlite3.Error) as exc:
            if backend == "sqlite":
                raise
            ctx.notes.append(f"sqlite unavailable: {exc}")
    try:
        ctx.cli = CliBackend()
    except OpencodeSessionsError as exc:
        ctx.notes.append(f"cli unavailable: {exc}")
        raise BackendError("; ".join(ctx.notes)) from exc
    ctx._cli_tried = True
    if backend == "auto":
        ctx.notes.append("using the opencode CLI fallback")
    return ctx
