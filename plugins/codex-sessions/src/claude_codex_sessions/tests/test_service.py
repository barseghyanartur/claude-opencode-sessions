from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_codex_sessions.errors import SessionsDirNotFoundError
from claude_codex_sessions.scope import resolve_scope
from claude_codex_sessions.service import Reader, open_reader

from .conftest import NOW, RolloutBuilder, rollout_path


def test_open_reader_missing_home_raises(tmp_path: Path):
    with pytest.raises(SessionsDirNotFoundError):
        open_reader(str(tmp_path / "missing"))


def test_open_reader_uses_env(codex_home: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    reader = open_reader()
    assert reader.home == codex_home


def test_title_prefers_session_index(codex_home: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.user("some question")
    builder.write(rollout_path(codex_home, "sid1"))
    (codex_home / "session_index.jsonl").write_text(
        json.dumps(
            {
                "id": "sid1",
                "thread_name": "A proper title",
                "updated_at": "2030-01-01T00:00:00Z",
            }
        )
        + "\n"
    )
    reader = Reader(codex_home)
    [session] = reader.all_sessions()
    assert session.title == "A proper title"
    assert session.time_updated is not None and session.time_updated > NOW


def test_title_falls_back_to_derived_and_then_id(codex_home: Path):
    with_text = RolloutBuilder("sid1", "/work")
    with_text.user("first message here")
    with_text.write(rollout_path(codex_home, "sid1"))

    without_text = RolloutBuilder("sid2", "/work")
    without_text.write(rollout_path(codex_home, "sid2", when=NOW - 1000))

    reader = Reader(codex_home)
    by_id = {s.id: s for s in reader.all_sessions()}
    assert by_id["sid1"].title == "first message here"
    assert by_id["sid2"].title == "sid2"


def test_unreadable_rollout_file_is_noted_not_raised(codex_home: Path):
    (codex_home / "sessions" / "2026" / "01" / "01").mkdir(parents=True)
    bad = (
        codex_home
        / "sessions"
        / "2026"
        / "01"
        / "01"
        / "rollout-2026-01-01T00-00-00-x.jsonl"
    )
    bad.write_text("not even json\n")
    reader = Reader(codex_home)
    assert reader.all_sessions() == []
    assert any("could not be parsed" in n for n in reader.notes)


def test_listing_applies_scope(codex_home: Path, git_repo):
    repo = git_repo["repo"]
    inside = RolloutBuilder("in", str(repo))
    inside.user("x")
    inside.write(rollout_path(codex_home, "in"))
    outside = RolloutBuilder("out", "/elsewhere")
    outside.user("y")
    outside.write(rollout_path(codex_home, "out", when=NOW - 1000))

    reader = Reader(codex_home)
    scope = resolve_scope(str(repo), "worktree")
    listing = reader.listing(scope)
    assert [s.id for s in listing.shown] == ["in"]


def test_messages_returns_empty_for_unknown_session(codex_home: Path):
    reader = Reader(codex_home)
    from claude_codex_sessions.models import Session

    assert reader.messages(Session(id="nope", title="x", directory="/x")) == []
