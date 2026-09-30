from claude_opencode_sessions.models import format_model
from claude_opencode_sessions.parse import (
    loads,
    parse_v1_message,
    parse_v1_part,
    parse_v2_row,
)
from claude_opencode_sessions.tests.conftest import text_of


def test_format_model_variants():
    assert format_model('{"id": "m", "providerID": "p"}') == "p/m"
    assert format_model({"modelID": "m"}) == "m"
    assert format_model("plain-model") == "plain-model"
    assert format_model("{broken") == "{broken"
    assert format_model(None) is None
    assert format_model({"x": 1}) is None


def test_loads_is_forgiving():
    assert loads('{"a": 1}') == {"a": 1}
    assert loads("not json") is None
    assert loads(None) is None
    assert loads({"a": 1}) == {"a": 1}


def test_v1_parts():
    assert parse_v1_part({"type": "step-start"}) is None
    assert parse_v1_part({"type": "step-finish"}) is None
    text = parse_v1_part({"type": "text", "text": "hi", "synthetic": True})
    assert text is not None
    assert (text.kind, text.text, text.synthetic) == ("text", "hi", True)
    tool = parse_v1_part(
        {
            "type": "tool",
            "tool": "bash",
            "state": {"status": "error", "input": {"command": "ls"}, "error": "boom"},
        }
    )
    assert tool is not None
    assert (tool.tool, tool.status, tool.tool_output) == ("bash", "error", "boom")
    assert tool.tool_input == {"command": "ls"}
    patch = parse_v1_part({"type": "patch", "files": ["a.py", "b.py"]})
    assert patch is not None and patch.files == ["a.py", "b.py"]
    file_part = parse_v1_part({"type": "file", "filename": "x.png"})
    assert file_part is not None and file_part.text == "x.png"
    compaction = parse_v1_part({"type": "compaction"})
    assert compaction is not None and compaction.kind == "compaction"
    other = parse_v1_part({"type": "weird", "text": "?"})
    assert other is not None and other.kind == "weird"
    assert parse_v1_part("raw").kind == "other"  # type: ignore[union-attr]


def test_v1_message_model_and_error():
    message = parse_v1_message(
        {
            "id": "m1",
            "role": "assistant",
            "modelID": "gpt",
            "providerID": "openai",
            "error": {"name": "APIError", "data": {"message": "rate limited"}},
            "time": {"created": 5},
            "cost": 0.5,
        },
        [{"type": "text", "text": "a"}, {"type": "step-finish"}],
        seq=3,
    )
    assert message.model == "openai/gpt"
    assert message.error == "APIError: rate limited"
    assert message.seq == 3
    assert message.time_created == 5
    assert message.cost == 0.5
    assert [p.kind for p in message.parts] == ["text"]


def test_v1_message_user_model_object():
    message = parse_v1_message(
        {"role": "user", "model": {"providerID": "p", "modelID": "m"}}, []
    )
    assert message.model == "p/m"
    assert message.role == "user"


def test_v2_user_row():
    message, ok = parse_v2_row("r1", "user", '{"text": "hello"}', 1, 10)
    assert ok
    assert message.role == "user"
    assert text_of(message) == "hello"


def test_v2_assistant_row_with_content_list():
    data = {
        "model": {"id": "m", "providerID": "p"},
        "tokens": {"input": 1, "output": 2},
        "cost": 0.1,
        "content": [
            {"type": "text", "text": "answer"},
            {"type": "reasoning", "text": "hmm"},
            {"type": "tool", "tool": "read", "state": {"input": {"filePath": "a"}}},
            {"type": "tool-call", "name": "bash", "args": {"command": "ls"}},
            "loose string",
        ],
    }
    message, ok = parse_v2_row("r2", "assistant", data, 2, 11)
    assert ok
    assert message.model == "p/m"
    kinds = [p.kind for p in message.parts]
    assert kinds == ["text", "reasoning", "tool", "tool", "text"]
    assert message.parts[3].tool == "bash"
    assert message.parts[3].tool_input == {"command": "ls"}


def test_v2_tool_row_and_bad_json():
    message, ok = parse_v2_row("r3", "tool", {"tool": "grep", "input": {}}, 3, 12)
    assert ok and message.parts[0].tool == "grep"
    broken, ok = parse_v2_row("r4", "assistant", "{nope", 4, 13)
    assert not ok
    assert broken.parts[-1].text == "[unparseable message payload]"
    idle, ok = parse_v2_row("r5", "idle", "{}", 5, 14)
    assert ok and idle.role == "idle" and idle.parts == []
