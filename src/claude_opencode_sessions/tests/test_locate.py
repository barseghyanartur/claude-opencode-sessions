import json
from pathlib import Path

import pytest

from claude_opencode_sessions.errors import DatabaseNotFoundError
from claude_opencode_sessions.locate import candidate_paths, find_db, opencode_db_path


@pytest.fixture(autouse=True)
def isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.delenv("OPENCODE_SESSIONS_DB", raising=False)
    monkeypatch.delenv("XDG_DATA_HOME", raising=False)
    monkeypatch.delenv("LOCALAPPDATA", raising=False)
    monkeypatch.delenv("APPDATA", raising=False)
    monkeypatch.setenv("HOME", str(tmp_path / "home"))


def test_candidates_respect_xdg(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path / "xdg"))
    paths = candidate_paths()
    assert paths[0] == tmp_path / "xdg" / "opencode" / "opencode.db"
    assert (
        paths[1] == tmp_path / "home" / ".local" / "share" / "opencode" / "opencode.db"
    )


def test_find_db_default_location(tmp_path: Path):
    db = tmp_path / "home" / ".local" / "share" / "opencode" / "opencode.db"
    db.parent.mkdir(parents=True)
    db.write_bytes(b"")
    assert find_db(ask_cli=False) == db


def test_find_db_explicit_and_env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    db = tmp_path / "custom.db"
    db.write_bytes(b"")
    assert find_db(db) == db
    with pytest.raises(DatabaseNotFoundError):
        find_db(tmp_path / "missing.db")
    monkeypatch.setenv("OPENCODE_SESSIONS_DB", str(db))
    assert find_db() == db
    monkeypatch.setenv("OPENCODE_SESSIONS_DB", str(tmp_path / "nope.db"))
    with pytest.raises(DatabaseNotFoundError, match="OPENCODE_SESSIONS_DB"):
        find_db()


def test_find_db_asks_opencode(fake_opencode: Path, tmp_path: Path):
    db = tmp_path / "from-cli.db"
    db.write_bytes(b"")
    data = json.loads(fake_opencode.read_text())
    data["db_path"] = str(db)
    fake_opencode.write_text(json.dumps(data))
    assert opencode_db_path() == db
    assert find_db() == db


def test_find_db_gives_up(monkeypatch: pytest.MonkeyPatch, tmp_path: Path):
    monkeypatch.setenv("PATH", str(tmp_path))
    assert opencode_db_path() is None
    with pytest.raises(DatabaseNotFoundError, match="looked in"):
        find_db()
