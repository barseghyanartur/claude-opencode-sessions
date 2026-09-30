from __future__ import annotations

import json
from pathlib import Path

import pytest

from claude_codex_sessions.errors import SessionsDirNotFoundError
from claude_codex_sessions.locate import (
    codex_home,
    find_sessions_dir,
    rollout_files,
    session_index,
)


def test_codex_home_defaults_to_dot_codex(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("CODEX_HOME", raising=False)
    assert codex_home() == Path.home() / ".codex"


def test_codex_home_respects_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path))
    assert codex_home() == tmp_path


def test_codex_home_explicit_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "env"))
    assert codex_home(str(tmp_path / "explicit")) == tmp_path / "explicit"


def test_find_sessions_dir_missing_raises(tmp_path: Path):
    with pytest.raises(SessionsDirNotFoundError):
        find_sessions_dir(str(tmp_path / "nonexistent"))


def test_find_sessions_dir_found(codex_home: Path):
    assert find_sessions_dir(str(codex_home)) == codex_home / "sessions"


def test_rollout_files_recursive(codex_home: Path):
    sessions = codex_home / "sessions"
    (sessions / "2026" / "04" / "10").mkdir(parents=True)
    a = sessions / "2026" / "04" / "10" / "rollout-2026-04-10T00-00-00-a.jsonl"
    a.write_text("{}\n")
    (sessions / "2026" / "05").mkdir(parents=True)
    b = sessions / "2026" / "05" / "rollout-2026-05-01T00-00-00-b.jsonl"
    b.write_text("{}\n")
    (sessions / "not-a-rollout.jsonl").write_text("{}\n")
    found = rollout_files(sessions)
    assert set(found) == {a, b}


def test_session_index_missing_file_returns_empty(codex_home: Path):
    assert session_index(codex_home) == {}


def test_session_index_parses_entries(codex_home: Path):
    path = codex_home / "session_index.jsonl"
    path.write_text(
        json.dumps(
            {"id": "abc", "thread_name": "Title", "updated_at": "2026-01-01T00:00:00Z"}
        )
        + "\n"
        + "not json\n"
        + json.dumps({"no": "id"})
        + "\n"
    )
    index = session_index(codex_home)
    assert index == {
        "abc": {
            "id": "abc",
            "thread_name": "Title",
            "updated_at": "2026-01-01T00:00:00Z",
        }
    }
