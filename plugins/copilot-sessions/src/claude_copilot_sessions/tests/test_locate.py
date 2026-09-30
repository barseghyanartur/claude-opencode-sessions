from __future__ import annotations

from pathlib import Path

import pytest

from claude_copilot_sessions.errors import SessionsDirNotFoundError
from claude_copilot_sessions.locate import (
    copilot_home,
    find_sessions_dir,
    read_workspace_yaml,
    session_dirs,
)


def test_copilot_home_defaults_to_dot_copilot(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.delenv("COPILOT_HOME", raising=False)
    assert copilot_home() == Path.home() / ".copilot"


def test_copilot_home_respects_env_var(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path))
    assert copilot_home() == tmp_path


def test_copilot_home_explicit_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "env"))
    assert copilot_home(str(tmp_path / "explicit")) == tmp_path / "explicit"


def test_find_sessions_dir_missing_raises(tmp_path: Path):
    with pytest.raises(SessionsDirNotFoundError):
        find_sessions_dir(str(tmp_path / "nonexistent"))


def test_find_sessions_dir_found(copilot_home: Path):
    assert find_sessions_dir(str(copilot_home)) == copilot_home / "session-state"


def test_session_dirs_only_lists_dirs_with_events(copilot_home: Path):
    sessions = copilot_home / "session-state"
    a = sessions / "a"
    a.mkdir()
    (a / "events.jsonl").write_text("{}\n")
    b = sessions / "b"
    b.mkdir()
    (b / "workspace.yaml").write_text("id: b\n")  # no events.jsonl: not a session
    (sessions / "not-a-dir.txt").write_text("x")
    assert session_dirs(sessions) == [a]


def test_session_dirs_missing_returns_empty(tmp_path: Path):
    assert session_dirs(tmp_path / "missing") == []


def test_read_workspace_yaml_missing_file_returns_empty(tmp_path: Path):
    assert read_workspace_yaml(tmp_path / "missing.yaml") == {}


def test_read_workspace_yaml_parses_flat_scalars(tmp_path: Path):
    path = tmp_path / "workspace.yaml"
    path.write_text(
        "id: abc-123\n"
        "cwd: /Users/me/repo\n"
        "name: My Session Title\n"
        "user_named: false\n"
        "created_at: 2026-01-01T00:00:00.000Z\n"
        "# a comment\n"
        "\n"
        "nested:\n"
        "  - list item, indented, skipped\n"
    )
    data = read_workspace_yaml(path)
    assert data["id"] == "abc-123"
    assert data["cwd"] == "/Users/me/repo"
    assert data["name"] == "My Session Title"
    assert data["user_named"] is False
    assert data["created_at"] == "2026-01-01T00:00:00.000Z"
    assert "nested" not in data or data.get("nested") in (None, "")


def test_read_workspace_yaml_unquotes_values(tmp_path: Path):
    path = tmp_path / "workspace.yaml"
    path.write_text('name: "Quoted Title"\n')
    assert read_workspace_yaml(path)["name"] == "Quoted Title"
