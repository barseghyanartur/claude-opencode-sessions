from __future__ import annotations

from pathlib import Path

from claude_copilot_sessions.parse import derive_title, parse_session, parse_timestamp

from .conftest import EventsBuilder, session_path


def test_parse_timestamp():
    assert parse_timestamp("2026-01-02T03:04:05.678Z") is not None
    assert parse_timestamp("not a timestamp") is None
    assert parse_timestamp(None) is None
    assert parse_timestamp(123) is None


def test_parse_missing_session_returns_none(tmp_path: Path):
    missing = tmp_path / "session-state" / "nope"
    assert parse_session(missing) is None


def test_parse_skips_malformed_lines(tmp_path: Path, copilot_home: Path):
    builder = EventsBuilder("sid1", "/work", title="Title")
    builder.user("hello")
    builder.assistant("hi")
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    with (path / "events.jsonl").open("a") as handle:
        handle.write("not json at all\n")
        handle.write("\n")  # blank line
        handle.write("[1, 2, 3]\n")  # valid json, not a dict
    result = parse_session(path)
    assert result is not None
    session, messages = result
    assert session.id == "sid1"
    assert len(messages) == 2


def test_parse_basic_session_fields(copilot_home: Path):
    builder = EventsBuilder(
        "sid1", "/Users/me/repos/demo", copilot_version="1.0.90", title="A Title"
    )
    builder.system()
    builder.user("Fix the bug")
    builder.assistant("On it", model="test-model")
    builder.shutdown()
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    result = parse_session(path)
    assert result is not None
    session, messages = result
    assert session.id == "sid1"
    assert session.title == "A Title"
    assert session.directory == "/Users/me/repos/demo"
    assert session.model == "test-model"
    assert session.version == "1.0.90"
    assert session.source == "github/cli"
    assert session.time_created is not None
    assert session.time_updated is not None
    assert session.time_updated >= session.time_created
    assert session.message_count == 2
    assert [m.role for m in messages] == ["user", "assistant"]


def test_system_message_is_dropped(copilot_home: Path):
    builder = EventsBuilder("sid1", "/work")
    builder.system("You are the system prompt.")
    builder.user("hello")
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    _, messages = parse_session(path)  # type: ignore[misc]
    assert [m.role for m in messages] == ["user"]


def test_raw_content_used_not_transformed_content(copilot_home: Path):
    # Copilot wraps the model-facing text in <current_datetime>...; the raw
    # `content` field (what the user actually typed) is used instead.
    builder = EventsBuilder("sid1", "/work")
    builder.user("What is this about?")
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    _, messages = parse_session(path)  # type: ignore[misc]
    assert messages[0].parts[0].text == "What is this about?"
    assert "current_datetime" not in messages[0].parts[0].text


def test_tool_request_and_completion_are_paired(copilot_home: Path):
    builder = EventsBuilder("sid1", "/work")
    builder.user("run ls")
    request, call_id = builder.tool_request("view", {"path": "/a.py"})
    builder.assistant("", tool_requests=[request])
    builder.tool_complete(call_id, "file contents")
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    _, messages = parse_session(path)  # type: ignore[misc]
    tool_messages = [m for m in messages if m.parts and m.parts[0].kind == "tool"]
    assert len(tool_messages) == 1
    part = tool_messages[0].parts[0]
    assert part.tool == "view"
    assert part.tool_input == {"path": "/a.py"}
    assert part.tool_output == "file contents"
    assert part.status == "completed"


def test_failed_tool_call_is_marked_error(copilot_home: Path):
    builder = EventsBuilder("sid1", "/work")
    request, call_id = builder.tool_request("bash", {"command": "false"})
    builder.assistant("", tool_requests=[request])
    builder.tool_complete(call_id, "command failed", success=False)
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    _, messages = parse_session(path)  # type: ignore[misc]
    part = next(m for m in messages if m.parts[0].kind == "tool").parts[0]
    assert part.status == "error"


def test_tool_completion_for_unknown_call_id_is_ignored(copilot_home: Path):
    builder = EventsBuilder("sid1", "/work")
    request, call_id = builder.tool_request("view", {"path": "/a.py"})
    builder.assistant("", tool_requests=[request])
    builder.tool_complete("some-other-call-id", "orphan output")
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    _, messages = parse_session(path)  # type: ignore[misc]
    part = next(m for m in messages if m.parts[0].kind == "tool").parts[0]
    assert part.tool_output is None
    assert part.status == "pending"
    assert call_id  # the real call never got its completion


def test_assistant_message_with_text_and_tools_in_one_step(copilot_home: Path):
    builder = EventsBuilder("sid1", "/work")
    request, call_id = builder.tool_request("view", {"path": "/a.py"})
    builder.assistant("Let me check that file.", tool_requests=[request])
    builder.tool_complete(call_id, "contents")
    path = session_path(copilot_home, "sid1")
    builder.write(path)
    _, messages = parse_session(path)  # type: ignore[misc]
    assert len(messages) == 1
    kinds = [p.kind for p in messages[0].parts]
    assert kinds == ["text", "tool"]


def test_title_falls_back_to_derived_then_id(copilot_home: Path):
    with_title = EventsBuilder("sid1", "/work", title="Explicit Title")
    with_title.user("hello")
    with_title.write(session_path(copilot_home, "sid1"))

    derived = EventsBuilder("sid2", "/work")  # no title
    derived.user("First line\nSecond line")
    derived.write(session_path(copilot_home, "sid2"))

    no_content = EventsBuilder("sid3", "/work")  # no title, no user message
    no_content.shutdown()
    no_content.write(session_path(copilot_home, "sid3"))

    s1, _ = parse_session(session_path(copilot_home, "sid1"))  # type: ignore[misc]
    s2, _ = parse_session(session_path(copilot_home, "sid2"))  # type: ignore[misc]
    s3, _ = parse_session(session_path(copilot_home, "sid3"))  # type: ignore[misc]
    assert s1.title == "Explicit Title"
    assert s2.title == "First line"
    assert s3.title == "sid3"


def test_derive_title_truncates_long_lines():
    from claude_copilot_sessions.models import Message, Part

    msg = Message(id="1", role="user", parts=[Part(kind="text", text="x" * 200)])
    title = derive_title([msg], limit=80)
    assert title is not None
    assert len(title) == 81
    assert title.endswith("…")


def test_derive_title_returns_none_without_user_text():
    assert derive_title([]) is None
