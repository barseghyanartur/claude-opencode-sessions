import sqlite3
from pathlib import Path

import pytest

from claude_opencode_sessions.errors import SchemaError
from claude_opencode_sessions.sqlite_backend import SqliteBackend
from claude_opencode_sessions.tests.conftest import (
    NOW,
    DbBuilder,
    assistant,
    text,
    text_of,
    tool,
    user,
)


def test_lists_1x_sessions(db_1x: DbBuilder):
    db_1x.session_1x(
        "ses_a",
        "/work/repo",
        title="First",
        messages=[user("hi"), assistant(text("hello"))],
    )
    db_1x.session_1x("ses_b", "/work/repo/sub", updated=NOW - 10, parent_id="ses_a")
    db_1x.close()
    backend = SqliteBackend(db_1x.path)
    sessions = {s.id: s for s in backend.list_sessions()}
    assert set(sessions) == {"ses_a", "ses_b"}
    first = sessions["ses_a"]
    assert first.title == "First"
    assert first.message_count == 2
    assert first.model == "openai/gpt-x"
    assert first.agent == "build"
    assert first.version == "1.18.32"
    assert first.origin == "session"
    assert sessions["ses_b"].is_subagent
    assert "1.x message/part" in backend.describe()
    assert backend.table_report()["message"] == 2


def test_loads_1x_messages_in_order(db_1x: DbBuilder):
    db_1x.session_1x(
        "ses_a",
        "/w",
        messages=[
            user("question"),
            assistant(text("thinking out loud"), tool("bash", {"command": "ls"})),
            assistant(text("done")),
        ],
    )
    db_1x.close()
    messages, errors = SqliteBackend(db_1x.path).load_messages("ses_a")
    assert errors == 0
    assert [m.role for m in messages] == ["user", "assistant", "assistant"]
    assert [m.seq for m in messages] == [1, 2, 3]
    assert text_of(messages[0]) == "question"
    assert [p.kind for p in messages[1].parts] == ["text", "tool"]
    assert messages[1].model == "openai/gpt-x"


def test_counts_parse_errors(db_1x: DbBuilder):
    db_1x.session_1x("ses_a", "/w", messages=[({"role": "user"}, ["{broken"])])
    db_1x.close()
    messages, errors = SqliteBackend(db_1x.path).load_messages("ses_a")
    assert errors == 1
    assert len(messages) == 1


def test_2x_sessions_and_messages(db_2x: DbBuilder):
    db_2x.session_2x(
        "ses_v2",
        "/w",
        rows=[
            ("user", {"text": "hi"}),
            ("assistant", {"content": [{"type": "text", "text": "yo"}]}),
            ("idle", {}),
        ],
    )
    db_2x.close()
    backend = SqliteBackend(db_2x.path)
    [session] = backend.list_sessions()
    assert session.origin == "session_v2"
    assert session.message_count == 2  # only user/assistant rows count
    assert session.version is None  # column missing in 2.x fixture
    messages, errors = backend.load_messages("ses_v2")
    assert errors == 0
    assert [m.role for m in messages] == ["user", "assistant", "idle"]
    assert "2.x session_message" in backend.describe()


def test_mixed_database_prefers_2x_and_falls_back_per_session(tmp_path: Path):
    builder = DbBuilder(tmp_path / "mixed.db", "schema_1x.sql")
    builder.conn.executescript(
        (Path(__file__).parent / "fixtures" / "schema_2x.sql")
        .read_text()
        .replace("CREATE TABLE `project`", "CREATE TABLE `project_unused`")
        .replace(
            "CREATE TABLE `session_message`", "CREATE TABLE `session_message_unused`"
        )
        .replace("ON `session_message`", "ON `session_message_unused`")
        .replace("session_message_session_seq_idx", "unused_idx")
    )
    # Migrated session: exists in both tables, 2.x metadata wins.
    builder.session_1x("ses_same", "/w", title="old title", messages=[user("legacy")])
    builder.session_2x("ses_same", "/w", title="new title")
    # Session only in the frozen 1.x table.
    builder.session_1x("ses_old", "/w", title="only legacy")
    # Session with 2.x messages.
    builder.session_2x("ses_new", "/w", rows=[("user", {"text": "fresh"})])
    builder.close()
    backend = SqliteBackend(builder.path)
    sessions = {s.id: s for s in backend.list_sessions()}
    assert set(sessions) == {"ses_same", "ses_old", "ses_new"}
    assert sessions["ses_same"].title == "new title"
    assert sessions["ses_same"].origin == "session_v2"
    assert sessions["ses_old"].origin == "session"
    # No 2.x rows for ses_same -> falls back to 1.x messages.
    messages, _ = backend.load_messages("ses_same")
    assert text_of(messages[0]) == "legacy"
    messages, _ = backend.load_messages("ses_new")
    assert text_of(messages[0]) == "fresh"


def test_rejects_unrelated_database(tmp_path: Path):
    path = tmp_path / "other.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE foo (id)")
    conn.close()
    with pytest.raises(SchemaError, match="no opencode session table"):
        SqliteBackend(path)


def test_rejects_session_table_without_messages(tmp_path: Path):
    path = tmp_path / "half.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE session (id, directory, time_updated)")
    conn.close()
    with pytest.raises(SchemaError, match="no opencode message tables"):
        SqliteBackend(path)


def test_rejects_non_sqlite_file(tmp_path: Path):
    path = tmp_path / "garbage.db"
    path.write_bytes(b"this is not a database" * 100)
    with pytest.raises(SchemaError):
        SqliteBackend(path)


def test_never_writes(db_1x: DbBuilder):
    db_1x.session_1x("ses_a", "/w")
    db_1x.close()
    backend = SqliteBackend(db_1x.path)
    with pytest.raises(sqlite3.OperationalError):
        backend.conn.execute("DELETE FROM session")
    backend.close()
