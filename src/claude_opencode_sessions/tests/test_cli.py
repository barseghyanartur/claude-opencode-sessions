import json
from pathlib import Path

import pytest

from claude_opencode_sessions.cli import main
from claude_opencode_sessions.tests.conftest import (
    HOUR,
    NOW,
    DbBuilder,
    assistant,
    text,
    tool,
    user,
)


@pytest.fixture
def populated(db_1x: DbBuilder, git_repo, monkeypatch: pytest.MonkeyPatch):
    repo, feature, other = git_repo["repo"], git_repo["feature"], git_repo["other"]
    db_1x.session_1x(
        "ses_newest",
        str(repo / "sub"),
        title="Newest in repo",
        updated=NOW,
        messages=[
            user("fix the parser"),
            assistant(text("on it"), tool("edit", {"filePath": "parser.py"})),
            assistant(text("done, the needle was misplaced")),
        ],
    )
    db_1x.session_1x(
        "ses_older",
        str(repo),
        title="Older in repo",
        updated=NOW - HOUR,
        messages=[user("older question")],
    )
    db_1x.session_1x("ses_archived", str(repo), updated=NOW - 2 * HOUR, archived=NOW)
    db_1x.session_1x(
        "ses_child", str(repo), updated=NOW - 3 * HOUR, parent_id="ses_newest"
    )
    db_1x.session_1x(
        "ses_feature", str(feature), title="Feature work", updated=NOW - 4 * HOUR
    )
    db_1x.session_1x(
        "ses_other",
        str(other),
        title="Elsewhere",
        updated=NOW - 5 * HOUR,
        project_id="proj2",
        messages=[user("unrelated")],
    )
    db_1x.close()
    monkeypatch.setenv("OPENCODE_SESSIONS_DB", str(db_1x.path))
    monkeypatch.chdir(repo / "sub")
    return git_repo


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_list_default_scope_is_current_worktree(populated, capsys):
    code, out, _ = run(capsys, "list")
    assert code == 0
    assert "Newest in repo" in out and "Older in repo" in out
    assert "Feature work" not in out and "Elsewhere" not in out
    assert "1 archived" in out and "1 sub-agent" in out
    assert out.index("Newest in repo") < out.index("Older in repo")


def test_list_worktrees_and_all(populated, capsys):
    _, out, _ = run(capsys, "list", "--worktrees")
    assert "Feature work" in out and "Elsewhere" not in out
    _, out, _ = run(
        capsys, "list", "--all", "--include-archived", "--include-subagents"
    )
    for title in (
        "Elsewhere",
        "Feature work",
        "Session ses_archived",
        "Session ses_child",
    ):
        assert title in out


def test_list_limit_and_json(populated, capsys):
    code, out, _ = run(capsys, "list", "--all", "-n", "1", "--format", "json")
    payload = json.loads(out)
    assert code == 0
    assert payload["total"] == 4
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["id"] == "ses_newest"
    assert payload["sessions"][0]["index"] == 1
    assert payload["backend"] == "sqlite"


def test_list_path_option(populated, capsys):
    _, out, _ = run(capsys, "list", "--path", str(populated["feature"]))
    assert "Feature work" in out and "Newest in repo" not in out


def test_doctor(populated, capsys):
    code, out, _ = run(capsys, "doctor")
    assert code == 0
    assert "layout: session · 1.x message/part" in out
    assert "sessions readable: 6" in out
    assert "scope worktree: git worktree" in out


def test_doctor_without_db(capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("OPENCODE_SESSIONS_DB", str(tmp_path / "missing.db"))
    code, out, _ = run(capsys, "doctor")
    assert code == 3 and "NOT USABLE" in out


def test_sqlite_backend_missing_db_errors(capsys, tmp_path: Path):
    code, _, err = run(
        capsys, "list", "--backend", "sqlite", "--db", str(tmp_path / "x.db")
    )
    assert code == 3 and "not found" in err


def test_auto_without_db_or_cli(
    capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("PATH", str(tmp_path))  # no opencode, no git
    code, _, err = run(capsys, "list", "--db", str(tmp_path / "x.db"))
    assert code == 4
    assert "sqlite unavailable" in err and "cli unavailable" in err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "claude-opencode-sessions" in capsys.readouterr().out
