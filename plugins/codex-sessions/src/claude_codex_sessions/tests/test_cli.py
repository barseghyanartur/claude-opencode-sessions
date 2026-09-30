import json
from pathlib import Path

import pytest

from claude_codex_sessions.cli import main

from .conftest import HOUR, NOW, RolloutBuilder, rollout_path


@pytest.fixture
def populated(codex_home: Path, git_repo, monkeypatch: pytest.MonkeyPatch):
    repo, feature, other = git_repo["repo"], git_repo["feature"], git_repo["other"]

    newest = RolloutBuilder("ses_newest", str(repo / "sub"), started=NOW)
    newest.user("fix the parser")
    newest.assistant("on it")
    newest.assistant("done, the needle was misplaced")
    newest.write(rollout_path(codex_home, "ses_newest", when=NOW))

    older = RolloutBuilder("ses_older", str(repo), started=NOW - HOUR)
    older.user("older question")
    older.write(rollout_path(codex_home, "ses_older", when=NOW - HOUR))

    feat = RolloutBuilder("ses_feature", str(feature), started=NOW - 4 * HOUR)
    feat.user("feature work")
    feat.write(rollout_path(codex_home, "ses_feature", when=NOW - 4 * HOUR))

    elsewhere = RolloutBuilder("ses_other", str(other), started=NOW - 5 * HOUR)
    elsewhere.user("unrelated")
    elsewhere.write(rollout_path(codex_home, "ses_other", when=NOW - 5 * HOUR))

    monkeypatch.setenv("CODEX_HOME", str(codex_home))
    monkeypatch.chdir(repo / "sub")
    return git_repo


def run(capsys, *argv: str) -> tuple[int, str, str]:
    code = main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_list_default_scope_is_current_worktree(populated, capsys):
    code, out, _ = run(capsys, "list")
    assert code == 0
    assert "fix the parser" in out and "older question" in out
    assert "feature work" not in out and "unrelated" not in out
    assert out.index("fix the parser") < out.index("older question")


def test_list_worktrees_and_all(populated, capsys):
    _, out, _ = run(capsys, "list", "--worktrees")
    assert "feature work" in out and "unrelated" not in out
    _, out, _ = run(capsys, "list", "--all")
    assert "feature work" in out and "unrelated" in out


def test_list_limit_and_json(populated, capsys):
    code, out, _ = run(capsys, "list", "--all", "-n", "1", "--format", "json")
    payload = json.loads(out)
    assert code == 0
    assert payload["total"] == 4
    assert len(payload["sessions"]) == 1
    assert payload["sessions"][0]["id"] == "ses_newest"
    assert payload["sessions"][0]["index"] == 1


def test_list_path_option(populated, capsys):
    _, out, _ = run(capsys, "list", "--path", str(populated["feature"]))
    assert "feature work" in out and "fix the parser" not in out


def test_doctor(populated, capsys):
    code, out, _ = run(capsys, "doctor")
    assert code == 0
    assert "sessions dir:" in out
    assert "sessions readable: 4" in out
    assert "scope worktree: git worktree" in out


def test_doctor_without_sessions_dir(
    capsys, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setenv("CODEX_HOME", str(tmp_path / "missing-home"))
    code, out, _ = run(capsys, "doctor")
    assert code == 3 and "NOT USABLE" in out


def test_list_missing_sessions_dir_errors(capsys, tmp_path: Path):
    code, _, err = run(capsys, "list", "--codex-home", str(tmp_path / "missing-home"))
    assert code == 3 and "not found" in err


def test_version(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert "claude-codex-sessions" in capsys.readouterr().out
