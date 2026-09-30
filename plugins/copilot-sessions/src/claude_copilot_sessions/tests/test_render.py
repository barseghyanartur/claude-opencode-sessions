from claude_copilot_sessions.models import Part, Session
from claude_copilot_sessions.render import (
    absolute_time,
    cell,
    relative_time,
    render_list,
    tilde,
    tool_summary,
    truncate,
)
from claude_copilot_sessions.scope import Scope

from .conftest import HOUR, NOW

SCOPE = Scope("worktree", "/repo", ["/repo"], in_git=True)


def session(**kw) -> Session:
    base = {
        "id": "ses_1",
        "title": "Fix | the bug",
        "directory": "/repo/sub",
        "time_created": NOW - 2 * HOUR,
        "time_updated": NOW - HOUR,
        "model": "test-model",
        "message_count": 4,
    }
    base.update(kw)
    return Session(**base)


def test_relative_and_absolute_time():
    assert relative_time(None) == "?"
    assert relative_time(NOW - 10_000, NOW) == "just now"
    assert relative_time(NOW - 5 * 60_000, NOW) == "5m ago"
    assert relative_time(NOW - 3 * HOUR, NOW) == "3h ago"
    assert relative_time(NOW - 50 * HOUR, NOW) == "2d ago"
    assert relative_time(NOW - 40 * 24 * HOUR, NOW).count("-") == 2
    assert absolute_time(None) == "?"
    assert len(absolute_time(NOW)) == len("2026-09-21 20:51")


def test_truncate_cell_and_tilde(monkeypatch):
    assert truncate("abc", 10) == "abc"
    assert truncate("abcdef", 3).startswith("abc\n… [3 more chars]")
    assert truncate("abcdef", 0) == "abcdef"
    assert cell("a |  b\nc") == "a \\| b c"
    assert cell("x" * 100, 10) == "x" * 9 + "…"
    monkeypatch.setenv("HOME", "/home/me")
    assert tilde("/home/me/repo") == "~/repo"
    assert tilde("/other") == "/other"


def test_tool_summary():
    assert tool_summary(Part("tool", tool="view", tool_input={"path": "/a.py"})) == (
        "→ view: `/a.py`"
    )
    assert tool_summary(Part("tool", tool="bash", tool_input={"command": "a\nb"})) == (
        "→ bash: `a …`"
    )
    failed = Part("tool", tool="bash", tool_input={"command": "x"}, status="error")
    assert tool_summary(failed).endswith("(error)")
    assert tool_summary(Part("tool", tool="glob", tool_input={"k": 1})).startswith(
        '→ glob: `{"k": 1}'
    )
    assert tool_summary(Part("tool", tool="bare")) == "→ bare"
    assert tool_summary(Part("tool", tool="s", tool_input="raw\nmore")) == "→ s: `raw`"


def test_render_list_table_and_footer():
    out = render_list(
        [session(), session(id="ses_2", directory="/repo", model="other-model")],
        SCOPE,
        total=5,
        backend="session directories",
        notes=["hello"],
        now_ms=NOW,
    )
    assert "| 1 | Fix \\| the bug | 1h ago | 4 | test-model | sub | `ses_1` |" in out
    assert "| . |" in out
    assert "showing 2 of 5" in out
    assert "source: session directories" in out
    assert "_note: hello_" in out


def test_render_list_empty_suggests_wider_scope():
    out = render_list([], SCOPE)
    assert "No Copilot sessions found" in out
    assert "--worktrees" in out


def test_render_list_other_worktree_and_all_scope():
    repo_scope = Scope("repo", "/repo", ["/repo", "/repo-feature"], in_git=True)
    out = render_list([session(directory="/repo-feature/x")], repo_scope, now_ms=NOW)
    assert "/repo-feature/x" in out
    out = render_list([session()], Scope("all", "/repo", ["/repo"]), now_ms=NOW)
    assert "/repo/sub" in out
