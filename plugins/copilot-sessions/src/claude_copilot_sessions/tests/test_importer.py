import io
import json
from pathlib import Path

import pytest

from claude_copilot_sessions.cli import main
from claude_copilot_sessions.import_command import hook_main
from claude_copilot_sessions.importer import (
    MARKER_KEY,
    ImportFailedError,
    build_conversation,
    claude_project_dir,
    content_hash,
    existing_imports,
    import_session,
    project_dir_name,
)
from claude_copilot_sessions.models import Message, Part, Session

from .conftest import NOW, EventsBuilder, session_path


def read_jsonl(path: Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text().splitlines()]


def msg(role, *parts, **kw):
    return Message(
        id=kw.pop("id", role), role=role, parts=list(parts), time_created=NOW, **kw
    )


def t(value, **kw):
    return Part(kind="text", text=value, **kw)


# -- conversation ---------------------------------------------------------------


def test_build_conversation_merges_and_drops_reasoning():
    turns = build_conversation(
        [
            msg("user", t("fix it")),
            msg(
                "assistant",
                Part("reasoning", text="hmm"),
                t("looking"),
                Part(
                    "tool", tool="view", tool_input={"path": "/a.py"}, tool_output="x"
                ),
            ),
            msg("assistant", t("done")),
            msg("idle"),
            msg("user", t("")),  # empty -> dropped
        ]
    )
    assert [x.role for x in turns] == ["user", "assistant"]
    assert turns[0].text == "fix it"
    assert "hmm" not in turns[1].text
    assert "→ view: `/a.py`" in turns[1].text
    assert "\n    x" not in turns[1].text
    assert turns[1].text.endswith("done")


def test_build_conversation_with_tool_output():
    turns = build_conversation(
        [
            msg(
                "assistant",
                Part(
                    "tool",
                    tool="view",
                    tool_input={"path": "/a.py"},
                    tool_output="line1\nline2",
                ),
            )
        ],
        with_tool_output=True,
    )
    assert "→ view: `/a.py`\n    line1\n    line2" in turns[0].text


def test_content_hash_depends_only_on_content():
    a = build_conversation([msg("user", t("q")), msg("assistant", t("a"))])
    b = build_conversation([msg("user", t("q"), id="other"), msg("assistant", t("a"))])
    c = build_conversation([msg("user", t("q")), msg("assistant", t("a!"))])
    assert content_hash(a) == content_hash(b) != content_hash(c)


# -- project dir -----------------------------------------------------------------


def test_project_dir_name_matches_claude_code():
    assert project_dir_name("/Users/me/repos/my_app.v2") == "-Users-me-repos-my-app-v2"


def test_claude_project_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    assert claude_project_dir("/a/b") == tmp_path / "cfg" / "projects" / "-a-b"
    assert claude_project_dir("/a/b", transcript_path="/x/y/s.jsonl") == Path("/x/y")
    assert claude_project_dir("/a/b", explicit="/z") == Path("/z")
    long_root = "/" + "d" * 250
    with pytest.raises(ImportFailedError):
        claude_project_dir(long_root)
    existing = (
        tmp_path / "cfg" / "projects" / (project_dir_name(long_root)[:200] + "-abc")
    )
    existing.mkdir(parents=True)
    assert claude_project_dir(long_root) == existing


# -- import_session ----------------------------------------------------------------


def session(**kw) -> Session:
    base = {
        "id": "ses_1",
        "title": "Fix parser",
        "directory": "/repo",
        "time_updated": NOW,
    }
    base.update(kw)
    return Session(**base)


CONVO = [msg("user", t("fix the parser")), msg("assistant", t("fixed"))]


def test_import_writes_resumable_transcript(tmp_path: Path):
    existing = existing_imports(tmp_path)
    result = import_session(
        session(),
        CONVO,
        project_dir=tmp_path,
        cwd="/repo",
        existing=existing,
        git_branch="main",
    )
    assert result.status == "imported"
    assert result.title == "[copilot] Fix parser"
    assert result.path is not None and result.path.name == f"{result.claude_id}.jsonl"
    entries = read_jsonl(result.path)
    head, first, second = entries
    assert head["type"] == "custom-title"
    assert head["customTitle"] == "[copilot] Fix parser"
    assert head["sessionId"] == result.claude_id
    assert head[MARKER_KEY]["sessionId"] == "ses_1"
    assert head[MARKER_KEY]["suffix"] == 0
    assert first["type"] == "user" and first["parentUuid"] is None
    assert first["message"]["content"].startswith(
        "[Imported from Copilot CLI session ses_1"
    )
    assert first["message"]["content"].endswith("fix the parser")
    assert first["cwd"] == "/repo" and first["gitBranch"] == "main"
    assert second["type"] == "assistant"
    assert second["parentUuid"] == first["uuid"]
    assert second["message"]["model"] == "<synthetic>"
    assert second["message"]["content"] == [{"type": "text", "text": "fixed"}]
    assert not list(tmp_path.glob(".*.tmp"))


def test_unchanged_session_is_never_imported_twice(tmp_path: Path):
    first = import_session(
        session(),
        CONVO,
        project_dir=tmp_path,
        cwd="/repo",
        existing=existing_imports(tmp_path),
        git_branch="",
    )
    again = import_session(
        session(title="Renamed in Copilot"),
        CONVO,
        project_dir=tmp_path,
        cwd="/repo",
        existing=existing_imports(tmp_path),
        git_branch="",
    )
    assert again.status == "unchanged"
    assert again.path == first.path
    assert len(list(tmp_path.glob("*.jsonl"))) == 1


def test_changed_session_gets_next_suffix(tmp_path: Path):
    kwargs = {"project_dir": tmp_path, "cwd": "/repo", "git_branch": ""}
    import_session(session(), CONVO, existing=existing_imports(tmp_path), **kwargs)
    grown = [*CONVO, msg("user", t("one more thing")), msg("assistant", t("ok"))]
    second = import_session(
        session(), grown, existing=existing_imports(tmp_path), **kwargs
    )
    assert second.status == "imported"
    assert second.title == "[copilot] Fix parser (1)"
    for convo in (CONVO, grown):
        again = import_session(
            session(), convo, existing=existing_imports(tmp_path), **kwargs
        )
        assert again.status == "unchanged"
    assert len(list(tmp_path.glob("*.jsonl"))) == 2


def test_empty_and_dry_run(tmp_path: Path):
    empty = import_session(
        session(),
        [msg("idle")],
        project_dir=tmp_path,
        cwd="/r",
        existing={},
        git_branch="",
    )
    assert empty.status == "empty"
    dry = import_session(
        session(),
        CONVO,
        project_dir=tmp_path,
        cwd="/r",
        existing={},
        dry_run=True,
        git_branch="",
    )
    assert dry.status == "would-import"
    assert not list(tmp_path.iterdir())


def test_conversation_is_padded_to_valid_alternation(tmp_path: Path):
    result = import_session(
        session(),
        [msg("assistant", t("hello?"))],
        project_dir=tmp_path,
        cwd="/r",
        existing={},
        git_branch="",
    )
    roles = [e["type"] for e in read_jsonl(result.path)[1:]]
    assert roles == ["user", "assistant"]
    result = import_session(
        session(id="ses_2"),
        [msg("user", t("unanswered"))],
        project_dir=tmp_path,
        cwd="/r",
        existing={},
        git_branch="",
    )
    entries = read_jsonl(result.path)[1:]
    assert [e["type"] for e in entries] == ["user", "assistant"]
    assert "ended here" in entries[-1]["message"]["content"][0]["text"]


def test_existing_imports_ignores_foreign_files(tmp_path: Path):
    (tmp_path / "claude-own.jsonl").write_text('{"type":"user","message":{}}\n')
    (tmp_path / "broken.jsonl").write_text('{"copilotImport": not json\n')
    (tmp_path / "empty.jsonl").write_text("")
    assert existing_imports(tmp_path) == {}
    assert existing_imports(tmp_path / "missing") == {}


def test_never_overwrites_a_file_that_appears_meanwhile(tmp_path: Path, monkeypatch):
    from claude_copilot_sessions import importer

    result = import_session(
        session(),
        CONVO,
        project_dir=tmp_path,
        cwd="/r",
        existing={},
        dry_run=True,
        git_branch="",
    )
    result.path.write_text("precious\n")
    monkeypatch.setattr(importer.Path, "exists", lambda self: False)
    again = import_session(
        session(), CONVO, project_dir=tmp_path, cwd="/r", existing={}, git_branch=""
    )
    monkeypatch.undo()
    assert again.status == "unchanged"
    assert result.path.read_text() == "precious\n"
    assert not list(tmp_path.glob(".*.tmp"))


# -- CLI + hook --------------------------------------------------------------------


@pytest.fixture
def repo_copilot(copilot_home: Path, git_repo, monkeypatch: pytest.MonkeyPatch):
    repo, feature = git_repo["repo"], git_repo["feature"]

    a = EventsBuilder("ses_a", str(repo), started=NOW, title="Parser work")
    a.user("fix parser")
    request, call_id = a.tool_request("bash", {"command": "pytest"})
    a.assistant("", tool_requests=[request])
    a.tool_complete(call_id, "ok")
    a.assistant("done")
    a.write(session_path(copilot_home, "ses_a"))

    b = EventsBuilder("ses_b", str(repo / "sub"), started=NOW - 3_600_000, title="Docs")
    b.user("write docs")
    b.assistant("ok")
    b.write(session_path(copilot_home, "ses_b"))

    empty = EventsBuilder("ses_empty", str(repo), started=NOW - 7_200_000)
    empty.shutdown()
    empty.write(session_path(copilot_home, "ses_empty"))

    feat = EventsBuilder("ses_feat", str(feature), started=NOW, title="Feature")
    feat.user("feat")
    feat.write(session_path(copilot_home, "ses_feat"))

    other = EventsBuilder("ses_other", "/elsewhere", started=NOW, title="Other")
    other.user("x")
    other.write(session_path(copilot_home, "ses_other"))

    monkeypatch.setenv("COPILOT_HOME", str(copilot_home))
    return git_repo


def test_cli_import_is_idempotent(repo_copilot, tmp_path: Path, capsys):
    target = tmp_path / "claude-project"
    argv = [
        "import",
        "--path",
        str(repo_copilot["repo"]),
        "--claude-project-dir",
        str(target),
    ]
    assert main([*argv, "--dry-run"]) == 0
    out = capsys.readouterr().out
    assert out.count("would-import") == 3  # a, b + the summary line
    assert not target.exists()
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "2 imported, 1 empty" in out
    assert "/resume" in out
    assert len(list(target.glob("*.jsonl"))) == 2
    assert main(argv) == 0
    out = capsys.readouterr().out
    assert "2 unchanged, 1 empty" in out
    assert len(list(target.glob("*.jsonl"))) == 2
    assert main([*argv, "--worktrees"]) == 0
    assert "[copilot] Feature" in capsys.readouterr().out
    assert len(list(target.glob("*.jsonl"))) == 3


def test_cli_import_default_project_dir(repo_copilot, tmp_path: Path, monkeypatch):
    monkeypatch.setenv("CLAUDE_CONFIG_DIR", str(tmp_path / "cfg"))
    monkeypatch.chdir(repo_copilot["repo"])
    assert main(["import"]) == 0
    expected = (
        tmp_path / "cfg" / "projects" / project_dir_name(str(repo_copilot["repo"]))
    )
    assert len(list(expected.glob("*.jsonl"))) == 2


def hook_event(
    repo: Path, transcript_dir: Path, name="copilot-sessions:import", args=""
):
    return json.dumps(
        {
            "session_id": "s",
            "transcript_path": str(transcript_dir / "current.jsonl"),
            "cwd": str(repo),
            "hook_event_name": "UserPromptExpansion",
            "expansion_type": "slash_command",
            "command_name": name,
            "command_args": args,
            "prompt": "…",
        }
    )


def test_hook_imports_and_blocks_the_prompt(repo_copilot, tmp_path: Path, monkeypatch):
    monkeypatch.delenv("CLAUDE_PROJECT_DIR", raising=False)
    target = tmp_path / "proj"
    output = json.loads(hook_main(hook_event(repo_copilot["repo"], target)))
    assert output["decision"] == "block"
    assert "2 imported" in output["reason"]
    assert len(list(target.glob("*.jsonl"))) == 2
    output = json.loads(
        hook_main(hook_event(repo_copilot["repo"], target, args="--dry-run"))
    )
    assert "2 unchanged" in output["reason"]


def test_hook_uses_command_input_and_project_dir_env(
    repo_copilot, tmp_path, monkeypatch
):
    monkeypatch.setenv("CLAUDE_PROJECT_DIR", str(repo_copilot["repo"]))
    event = json.loads(
        hook_event(Path("/somewhere/else"), tmp_path / "p", name="import")
    )
    del event["command_args"]
    event["command_input"] = {"args": "--worktrees --dry-run"}
    output = json.loads(hook_main(json.dumps(event)))
    assert "[copilot] Feature" in output["reason"]
    assert "Dry run" in output["reason"]


def test_hook_ignores_other_commands_and_garbage():
    assert hook_main("not json") is None
    assert hook_main("[]") is None
    assert hook_main(json.dumps({"command_name": "commit"})) is None


def test_hook_reports_bad_arguments_and_errors(tmp_path, monkeypatch):
    output = json.loads(hook_main(hook_event(tmp_path, tmp_path, args="--nope")))
    assert output["decision"] == "block" and "Usage:" in output["reason"]
    monkeypatch.setenv("COPILOT_HOME", str(tmp_path / "missing-home"))
    output = json.loads(hook_main(hook_event(tmp_path, tmp_path)))
    assert output["reason"].startswith("Copilot CLI import failed:")


def test_hook_via_cli_entrypoint(repo_copilot, tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        "sys.stdin", io.StringIO(hook_event(repo_copilot["repo"], tmp_path / "p"))
    )
    assert main(["hook"]) == 0
    assert json.loads(capsys.readouterr().out)["decision"] == "block"
    monkeypatch.setattr("sys.stdin", io.StringIO("{}"))
    assert main(["hook"]) == 0
    assert capsys.readouterr().out == ""


def test_imported_transcript_is_valid_jsonl_with_unique_uuids(repo_copilot, tmp_path):
    target = tmp_path / "p"
    main(
        [
            "import",
            "--path",
            str(repo_copilot["repo"]),
            "--claude-project-dir",
            str(target),
        ]
    )
    for path in target.glob("*.jsonl"):
        entries = read_jsonl(path)
        uuids = [e["uuid"] for e in entries if "uuid" in e]
        assert len(uuids) == len(set(uuids))
        parents = [e.get("parentUuid") for e in entries if "uuid" in e]
        assert parents[0] is None and parents[1:] == uuids[:-1]
        assert {e["sessionId"] for e in entries} == {path.stem}
