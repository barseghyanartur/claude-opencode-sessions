from __future__ import annotations

from pathlib import Path

import pytest

from claude_copilot_sessions.errors import SessionsDirNotFoundError
from claude_copilot_sessions.scope import resolve_scope
from claude_copilot_sessions.service import Reader, open_reader

from .conftest import NOW, EventsBuilder, session_path


def test_open_reader_missing_home_raises(tmp_path: Path):
    with pytest.raises(SessionsDirNotFoundError):
        open_reader(str(tmp_path / "missing"))


def test_open_reader_uses_env(copilot_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
    reader = open_reader()
    assert reader.home == copilot_home


def test_title_comes_from_workspace_yaml(copilot_home: Path):
    builder = EventsBuilder("sid1", "/work", title="A proper title")
    builder.user("some question")
    builder.write(session_path(copilot_home, "sid1"))
    reader = Reader(copilot_home)
    [session] = reader.all_sessions()
    assert session.title == "A proper title"


def test_title_falls_back_to_derived_and_then_id(copilot_home: Path):
    with_text = EventsBuilder("sid1", "/work")
    with_text.user("first message here")
    with_text.write(session_path(copilot_home, "sid1"))

    without_text = EventsBuilder("sid2", "/work", started=NOW - 1000)
    without_text.shutdown()
    without_text.write(session_path(copilot_home, "sid2"))

    reader = Reader(copilot_home)
    by_id = {s.id: s for s in reader.all_sessions()}
    assert by_id["sid1"].title == "first message here"
    assert by_id["sid2"].title == "sid2"


def test_unreadable_session_is_noted_not_raised(copilot_home: Path):
    bad = copilot_home / "session-state" / "bad"
    bad.mkdir(parents=True)
    (bad / "events.jsonl").write_text("not even json\n")
    reader = Reader(copilot_home)
    sessions = reader.all_sessions()
    # A session with only unparseable lines still yields a (title-less,
    # empty) Session — the file itself opened fine, so this isn't "unreadable".
    assert [s.id for s in sessions] == ["bad"]
    assert sessions[0].message_count == 0


def test_listing_applies_scope(copilot_home: Path, git_repo):
    repo = git_repo["repo"]
    inside = EventsBuilder("in", str(repo))
    inside.user("x")
    inside.write(session_path(copilot_home, "in"))
    outside = EventsBuilder("out", "/elsewhere", started=NOW - 1000)
    outside.user("y")
    outside.write(session_path(copilot_home, "out"))

    reader = Reader(copilot_home)
    scope = resolve_scope(str(repo), "worktree")
    listing = reader.listing(scope)
    assert [s.id for s in listing.shown] == ["in"]


def test_messages_returns_empty_for_unknown_session(copilot_home: Path):
    reader = Reader(copilot_home)
    from claude_copilot_sessions.models import Session

    assert reader.messages(Session(id="nope", title="x", directory="/x")) == []
