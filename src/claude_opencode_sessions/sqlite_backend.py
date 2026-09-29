"""Read-only access to opencode's SQLite database.

Supported layouts (detected per database, and per session for messages):

* opencode 1.x (>= 1.2): ``session`` + ``message`` + ``part``.
* opencode 2.x: ``session_v2`` (or ``session`` on early 2.x builds) +
  ``session_message``. Legacy 1.x rows that still live in the same file are
  merged in, de-duplicated by session id (2.x wins).

The database is opened with ``mode=ro``: this module never writes.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from .errors import SchemaError
from .models import Message, Session, format_model
from .parse import loads, parse_v1_message, parse_v2_row

__all__ = ["SqliteBackend"]

_SESSION_COLUMNS = (
    "id",
    "title",
    "directory",
    "project_id",
    "parent_id",
    "time_created",
    "time_updated",
    "time_archived",
    "agent",
    "model",
    "version",
    "cost",
    "tokens_input",
    "tokens_output",
)
_REQUIRED_SESSION_COLUMNS = {"id", "directory", "time_updated"}
_REQUIRED_V2_MESSAGE_COLUMNS = {"id", "session_id", "type", "data", "seq"}
_REQUIRED_V1_MESSAGE_COLUMNS = {"id", "session_id", "data"}
_CONVERSATION_TYPES = ("user", "assistant")


def _placeholders(count: int) -> str:
    return ",".join("?" * count)


class SqliteBackend:
    name = "sqlite"

    def __init__(self, path: str | Path, timeout: float = 2.0) -> None:
        self.path = Path(path)
        uri = f"{self.path.resolve().as_uri()}?mode=ro"
        try:
            self.conn = sqlite3.connect(uri, uri=True, timeout=timeout)
        except sqlite3.Error as exc:
            raise SchemaError(f"cannot open {self.path}: {exc}") from exc
        self.conn.row_factory = sqlite3.Row
        try:
            self._detect()
        except sqlite3.DatabaseError as exc:
            self.conn.close()
            raise SchemaError(f"cannot read {self.path}: {exc}") from exc
        except SchemaError:
            self.conn.close()
            raise

    # -- schema detection -------------------------------------------------

    def _tables(self) -> set[str]:
        rows = self.conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
        return {row[0] for row in rows}

    def _columns(self, table: str) -> set[str]:
        rows = self.conn.execute(f'PRAGMA table_info("{table}")').fetchall()
        return {row[1] for row in rows}

    def _detect(self) -> None:
        tables = self._tables()
        self.session_tables: list[str] = [
            t
            for t in ("session_v2", "session")
            if t in tables and _REQUIRED_SESSION_COLUMNS <= self._columns(t)
        ]
        if not self.session_tables:
            raise SchemaError(
                f"{self.path} has no opencode session table "
                "(needs opencode >= 1.2; JSON storage of older versions is "
                "not supported)"
            )
        self.has_v2_messages = (
            "session_message" in tables
            and _REQUIRED_V2_MESSAGE_COLUMNS <= self._columns("session_message")
        )
        self.has_v1_messages = (
            "message" in tables
            and "part" in tables
            and _REQUIRED_V1_MESSAGE_COLUMNS <= self._columns("message")
            and {"message_id", "data"} <= self._columns("part")
        )
        if not (self.has_v2_messages or self.has_v1_messages):
            raise SchemaError(f"{self.path} has no opencode message tables")

    def describe(self) -> str:
        """Human-readable description of the detected layout."""
        layouts = []
        if self.has_v2_messages and self._count("session_message"):
            layouts.append("2.x session_message")
        if self.has_v1_messages and self._count("message"):
            layouts.append("1.x message/part")
        if not layouts:
            layouts.append("empty")
        return f"{'+'.join(self.session_tables)} · {', '.join(layouts)}"

    def _count(self, table: str) -> int:
        row = self.conn.execute(f'SELECT count(*) FROM "{table}"').fetchone()
        return int(row[0])

    def table_report(self) -> dict[str, int]:
        """Row counts of the tables this backend reads (for ``doctor``)."""
        report: dict[str, int] = {}
        tables = self._tables()
        for table in ("session_v2", "session", "session_message", "message", "part"):
            if table in tables:
                report[table] = self._count(table)
        return report

    # -- sessions ---------------------------------------------------------

    def _message_counts(self) -> dict[str, int]:
        counts: dict[str, int] = {}
        if self.has_v1_messages:
            for row in self.conn.execute(
                "SELECT session_id, count(*) FROM message GROUP BY session_id"
            ):
                counts[row[0]] = int(row[1])
        if self.has_v2_messages:
            sql = (
                "SELECT session_id, count(*) FROM session_message "
                f"WHERE type IN ({_placeholders(len(_CONVERSATION_TYPES))}) "
                "GROUP BY session_id"
            )
            for row in self.conn.execute(sql, _CONVERSATION_TYPES):
                counts[row[0]] = int(row[1])
        return counts

    def _select_sessions(self, table: str) -> Iterable[sqlite3.Row]:
        available = self._columns(table)
        exprs = [
            f'"{col}" AS {col}' if col in available else f"NULL AS {col}"
            for col in _SESSION_COLUMNS
        ]
        sql = f'SELECT {", ".join(exprs)} FROM "{table}"'
        return self.conn.execute(sql)

    def list_sessions(self) -> list[Session]:
        counts = self._message_counts()
        seen: dict[str, Session] = {}
        for table in self.session_tables:
            for row in self._select_sessions(table):
                if row["id"] in seen:
                    continue
                seen[row["id"]] = Session(
                    id=row["id"],
                    title=row["title"] or "(untitled)",
                    directory=row["directory"] or "",
                    project_id=row["project_id"],
                    parent_id=row["parent_id"],
                    time_created=row["time_created"],
                    time_updated=row["time_updated"],
                    time_archived=row["time_archived"],
                    agent=row["agent"],
                    model=format_model(row["model"]),
                    version=row["version"],
                    message_count=counts.get(row["id"], 0),
                    cost=row["cost"],
                    tokens_input=row["tokens_input"],
                    tokens_output=row["tokens_output"],
                    origin=table,
                )
        return list(seen.values())

    # -- messages ---------------------------------------------------------

    def _load_v2(self, session_id: str) -> tuple[list[Message], int]:
        rows = self.conn.execute(
            "SELECT id, type, seq, time_created, data FROM session_message "
            "WHERE session_id = ? ORDER BY seq",
            (session_id,),
        ).fetchall()
        messages: list[Message] = []
        errors = 0
        for row in rows:
            message, ok = parse_v2_row(
                row["id"], row["type"], row["data"], row["seq"], row["time_created"]
            )
            errors += 0 if ok else 1
            messages.append(message)
        return messages, errors

    def _load_v1(self, session_id: str) -> tuple[list[Message], int]:
        msg_rows = self.conn.execute(
            "SELECT id, time_created, data FROM message "
            "WHERE session_id = ? ORDER BY time_created, id",
            (session_id,),
        ).fetchall()
        parts_by_message: dict[str, list[Any]] = {}
        for row in self.conn.execute(
            "SELECT message_id, data FROM part WHERE session_id = ? "
            "ORDER BY message_id, id",
            (session_id,),
        ):
            parts_by_message.setdefault(row["message_id"], []).append(
                loads(row["data"])
            )
        messages: list[Message] = []
        errors = 0
        for index, row in enumerate(msg_rows, start=1):
            info = loads(row["data"])
            if not isinstance(info, dict):
                errors += 1
                info = {}
            info.setdefault("id", row["id"])
            info.setdefault("time", {"created": row["time_created"]})
            parts = parts_by_message.get(row["id"], [])
            errors += sum(1 for p in parts if p is None)
            messages.append(
                parse_v1_message(info, [p for p in parts if p is not None], index)
            )
        return messages, errors

    def load_messages(self, session_id: str) -> tuple[list[Message], int]:
        """Return ``(messages, parse_errors)`` for one session."""
        if self.has_v2_messages:
            messages, errors = self._load_v2(session_id)
            if messages:
                return messages, errors
        if self.has_v1_messages:
            return self._load_v1(session_id)
        return [], 0

    def close(self) -> None:
        self.conn.close()
