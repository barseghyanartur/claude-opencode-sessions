import json
from pathlib import Path

import pytest

from claude_opencode_sessions.cli import main
from claude_opencode_sessions.cli_backend import (
    CliBackend,
    _extract_json,
    parse_version,
)
from claude_opencode_sessions.errors import BackendError
from claude_opencode_sessions.models import Message, Session
from claude_opencode_sessions.service import Context, open_context
from claude_opencode_sessions.tests.conftest import DbBuilder, text_of


def test_parse_version():
    assert parse_version("opencode 1.18.32") == (1, 18, 32)
    assert parse_version("2.0") == (2, 0)
    assert parse_version("dev") is None


def test_extract_json_skips_log_lines():
    assert _extract_json('INFO starting\n{"a": [1]}\n') == {"a": [1]}
    assert _extract_json("noise [1, 2]") == [1, 2]
    with pytest.raises(BackendError):
        _extract_json("no json {here")


def test_cli_backend_list_and_export(fake_opencode: Path):
    backend = CliBackend()
    assert backend.version == (1, 18, 32)
    [session] = backend.list_sessions()
    assert session.id == "ses_cli_1" and session.origin == "cli"
    info, messages = backend.export("ses_cli_1")
    assert info is not None and info.title == "From the CLI"
    assert [text_of(m) for m in messages] == ["hello from export", "hi back"]
    assert messages[1].model == "openai/gpt-x"
    with pytest.raises(BackendError, match="exited 1"):
        backend.export("ses_missing")


def test_cli_backend_rejects_old_version(fake_opencode: Path):
    data = json.loads(fake_opencode.read_text())
    data["version"] = "0.9.1"
    fake_opencode.write_text(json.dumps(data))
    with pytest.raises(BackendError, match="too old"):
        CliBackend()


def test_cli_backend_missing_executable(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(BackendError, match="not found on PATH"):
        CliBackend()


def test_auto_falls_back_to_cli(
    fake_opencode: Path, tmp_path: Path, capsys, monkeypatch
):
    project = tmp_path / "proj"
    project.mkdir()
    monkeypatch.setenv("OPENCODE_SESSIONS_DB", str(tmp_path / "missing.db"))
    code = main(["list", "--path", str(project)])
    out = capsys.readouterr().out
    assert code == 0
    assert "From the CLI" in out
    assert "backend: cli (opencode CLI 1.18.32)" in out
    assert "sqlite unavailable" in out
    target = tmp_path / "claude-project"
    code = main(["import", "--path", str(project), "--claude-project-dir", str(target)])
    out = capsys.readouterr().out
    assert code == 0 and "1 imported" in out
    [imported] = target.glob("*.jsonl")
    assert "hello from export" in imported.read_text()


def test_unparseable_sqlite_session_falls_back_to_export(
    fake_opencode: Path, db_1x: DbBuilder
):
    db_1x.session_1x(
        "ses_cli_1",
        "/w",
        messages=[({"role": "user"}, ["{bad"]), ({"role": "user"}, ["{bad"])],
    )
    db_1x.close()
    ctx = open_context("auto", str(db_1x.path))
    session = Session(id="ses_cli_1", title="t", directory="/w")
    messages = ctx.messages(session)
    assert text_of(messages[0]) == "hello from export"
    assert any("fell back" in note for note in ctx.notes)


def test_unparseable_sqlite_session_without_cli_keeps_partial(
    db_1x: DbBuilder, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    db_1x.session_1x("ses_a", "/w", messages=[({"role": "user"}, ["{bad"])])
    db_1x.close()
    monkeypatch.setenv("PATH", str(tmp_path))
    ctx = open_context("auto", str(db_1x.path))
    messages = ctx.messages(Session(id="ses_a", title="t", directory="/w"))
    assert len(messages) == 1 and isinstance(messages[0], Message)
    assert any("could not be parsed" in note for note in ctx.notes)
    assert any("cli unavailable" in note for note in ctx.notes)


def test_open_context_rejects_unknown_backend():
    with pytest.raises(ValueError):
        open_context("nope")


def test_context_describe_cli(fake_opencode: Path):
    ctx = Context(mode="cli", cli=CliBackend())
    assert ctx.describe().startswith("cli (opencode CLI")
