from __future__ import annotations

from pathlib import Path

from claude_codex_sessions.parse import derive_title, parse_rollout, parse_timestamp

from .conftest import RolloutBuilder


def test_parse_timestamp():
    assert parse_timestamp("2026-01-02T03:04:05.678Z") is not None
    assert parse_timestamp("not a timestamp") is None
    assert parse_timestamp(None) is None
    assert parse_timestamp(123) is None


def test_parse_missing_session_meta_returns_none(tmp_path: Path):
    path = tmp_path / "rollout.jsonl"
    path.write_text('{"type": "event_msg", "payload": {}}\n')
    assert parse_rollout(path) is None


def test_parse_missing_file_returns_none(tmp_path: Path):
    assert parse_rollout(tmp_path / "does-not-exist.jsonl") is None


def test_parse_skips_malformed_lines(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.user("hello")
    builder.assistant("hi")
    path = builder.write(tmp_path / "rollout.jsonl")
    with path.open("a") as handle:
        handle.write("not json at all\n")
        handle.write("\n")  # blank line
        handle.write("[1, 2, 3]\n")  # valid json, not a dict
    result = parse_rollout(path)
    assert result is not None
    session, messages = result
    assert session.id == "sid1"
    assert len(messages) == 2


def test_parse_basic_session_fields(tmp_path: Path):
    builder = RolloutBuilder(
        "sid1", "/Users/me/repos/demo", cli_version="0.150.0", source="cli"
    )
    builder.turn_context(model="gpt-5.5")
    builder.task_started(mode="plan")
    builder.user("Fix the bug")
    builder.assistant("On it")
    path = builder.write(tmp_path / "rollout.jsonl")
    result = parse_rollout(path)
    assert result is not None
    session, messages = result
    assert session.id == "sid1"
    assert session.directory == "/Users/me/repos/demo"
    assert session.model == "gpt-5.5"
    assert session.agent == "plan"
    assert session.version == "0.150.0"
    assert session.source == "cli"
    assert session.time_created is not None
    assert session.time_updated is not None
    assert session.time_updated >= session.time_created
    assert session.message_count == 2
    assert [m.role for m in messages] == ["user", "assistant"]


def test_developer_messages_are_dropped(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.developer("<permissions instructions> you may read files")
    builder.user("hello")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    assert [m.role for m in messages] == ["user"]


def test_synthetic_tagged_user_content_is_filtered(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.user("<environment_context>   <cwd>/work</cwd> </environment_context>")
    builder.user("the real question")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    assert len(messages) == 1
    assert messages[0].parts[0].text == "the real question"


def test_untagged_injected_context_is_kept_as_is(tmp_path: Path):
    # Known gap, documented in parse.py and the README: plain-text injected
    # context has no structural marker, so it is imported like real content.
    builder = RolloutBuilder("sid1", "/work")
    builder.user("# AGENTS.md instructions for /work\nBe nice.")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    assert len(messages) == 1
    assert "AGENTS.md" in messages[0].parts[0].text


def test_tool_call_and_output_are_paired(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.user("run ls")
    call_id = builder.tool_call("exec_command", {"cmd": "ls -la"})
    builder.tool_output(call_id, "file1\nfile2\n")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    tool_messages = [m for m in messages if m.parts[0].kind == "tool"]
    assert len(tool_messages) == 1
    part = tool_messages[0].parts[0]
    assert part.tool == "exec_command"
    assert part.tool_input == {"cmd": "ls -la"}
    assert part.tool_output == "file1\nfile2\n"
    assert part.status == "completed"


def test_tool_output_for_unknown_call_id_is_ignored(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    call_id = builder.tool_call("exec_command", {"cmd": "ls"})
    builder.tool_output("some-other-call-id", "orphan output")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    tool_part = next(m for m in messages if m.parts[0].kind == "tool").parts[0]
    assert tool_part.tool_output is None
    assert tool_part.status == "pending"
    assert call_id  # the real call never got its output


def test_tool_call_with_non_json_string_arguments_falls_back_to_raw(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.tool_call("web_search", "not actually json", item_type="function_call")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    part = messages[0].parts[0]
    assert part.tool_input == "not actually json"


def test_reasoning_is_parsed_but_not_a_text_message(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.reasoning("**Planning the fix**")
    path = builder.write(tmp_path / "rollout.jsonl")
    session, messages = parse_rollout(path)  # type: ignore[misc]
    assert len(messages) == 1
    assert messages[0].parts[0].kind == "reasoning"
    assert session.message_count == 0  # only real text messages are counted


def test_derive_title_from_messages(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.assistant("I can't answer yet")
    builder.user("First line\nSecond line")
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    assert derive_title(messages) == "First line"


def test_derive_title_truncates_long_lines(tmp_path: Path):
    builder = RolloutBuilder("sid1", "/work")
    builder.user("x" * 200)
    path = builder.write(tmp_path / "rollout.jsonl")
    _, messages = parse_rollout(path)  # type: ignore[misc]
    title = derive_title(messages, limit=80)
    assert title is not None
    assert len(title) == 81  # 80 chars + the ellipsis
    assert title.endswith("…")


def test_derive_title_returns_none_without_user_text():
    assert derive_title([]) is None
