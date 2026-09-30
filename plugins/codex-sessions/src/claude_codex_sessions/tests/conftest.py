from __future__ import annotations

import json
import os
import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pytest

NOW = 1_790_000_000_000  # ms
HOUR = 3_600_000


def iso(ms: int) -> str:
    moment = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


class RolloutBuilder:
    """Build a Codex rollout JSONL file line by line, like a real one."""

    def __init__(
        self,
        session_id: str,
        cwd: str,
        *,
        started: int = NOW,
        cli_version: str = "0.150.0",
        source: str = "cli",
        originator: str = "codex-tui",
    ) -> None:
        self.session_id = session_id
        self.lines: list[dict[str, Any]] = []
        self._ordinal = 0
        self._ts = started
        self._raw(
            "session_meta",
            {
                "session_id": session_id,
                "id": session_id,
                "timestamp": iso(started),
                "cwd": cwd,
                "originator": originator,
                "cli_version": cli_version,
                "source": source,
                "thread_source": "user",
                "model_provider": "openai",
                "base_instructions": {"text": ""},
            },
        )

    def _raw(
        self, kind: str, payload: dict[str, Any], *, advance_ms: int = 1000
    ) -> None:
        self._ts += advance_ms
        self.lines.append(
            {
                "timestamp": iso(self._ts),
                "ordinal": self._ordinal,
                "type": kind,
                "payload": payload,
            }
        )
        self._ordinal += 1

    def turn_context(
        self, model: str = "gpt-5.5", turn_id: str = "turn1"
    ) -> RolloutBuilder:
        self._raw("turn_context", {"turn_id": turn_id, "model": model})
        return self

    def task_started(
        self, mode: str = "default", turn_id: str = "turn1"
    ) -> RolloutBuilder:
        self._raw(
            "event_msg",
            {
                "type": "task_started",
                "turn_id": turn_id,
                "collaboration_mode_kind": mode,
            },
        )
        return self

    def user(self, text: str, *, msg_id: str | None = None) -> RolloutBuilder:
        self._raw(
            "response_item",
            {
                "type": "message",
                "id": msg_id or f"msg_{self._ordinal}",
                "role": "user",
                "content": [{"type": "input_text", "text": text}],
            },
        )
        return self

    def developer(self, text: str) -> RolloutBuilder:
        self._raw(
            "response_item",
            {
                "type": "message",
                "id": f"dev_{self._ordinal}",
                "role": "developer",
                "content": [{"type": "input_text", "text": text}],
            },
        )
        return self

    def assistant(self, text: str, *, msg_id: str | None = None) -> RolloutBuilder:
        self._raw(
            "response_item",
            {
                "type": "message",
                "id": msg_id or f"msg_{self._ordinal}",
                "role": "assistant",
                "content": [{"type": "output_text", "text": text}],
            },
        )
        return self

    def reasoning(self, text: str) -> RolloutBuilder:
        self._raw(
            "response_item",
            {
                "type": "reasoning",
                "id": f"rs_{self._ordinal}",
                "summary": [{"type": "summary_text", "text": text}],
            },
        )
        return self

    def tool_call(
        self,
        name: str,
        args: Any,
        *,
        call_id: str | None = None,
        item_type: str = "function_call",
    ) -> str:
        call_id = call_id or f"call_{self._ordinal}"
        arguments = json.dumps(args) if not isinstance(args, str) else args
        self._raw(
            "response_item",
            {
                "type": item_type,
                "id": f"fc_{self._ordinal}",
                "name": name,
                "arguments": arguments,
                "call_id": call_id,
            },
        )
        return call_id

    def tool_output(
        self, call_id: str, output: Any, *, item_type: str = "function_call_output"
    ) -> RolloutBuilder:
        self._raw(
            "response_item",
            {
                "type": item_type,
                "id": f"fco_{self._ordinal}",
                "call_id": call_id,
                "output": output,
            },
        )
        return self

    def write(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as handle:
            for line in self.lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        return path


def rollout_path(home: Path, session_id: str, when: int = NOW) -> Path:
    moment = datetime.fromtimestamp(when / 1000, tz=timezone.utc)
    return (
        home
        / "sessions"
        / f"{moment:%Y}"
        / f"{moment:%m}"
        / f"{moment:%d}"
        / f"rollout-{moment:%Y-%m-%dT%H-%M-%S}-{session_id}.jsonl"
    )


@pytest.fixture
def codex_home(tmp_path: Path) -> Path:
    home = tmp_path / "codex_home"
    (home / "sessions").mkdir(parents=True)
    return home


needs_git = pytest.mark.skipif(shutil.which("git") is None, reason="git not installed")


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(
        ["git", *args],
        cwd=cwd,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@example.com",
            "PATH": os.environ.get("PATH", ""),
            "HOME": str(cwd),
        },
    )


@pytest.fixture
def git_repo(tmp_path: Path) -> dict[str, Path]:
    """A repo with one extra worktree and a subdirectory, plus a non-git dir."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    repo = tmp_path / "repo"
    (repo / "sub" / "deep").mkdir(parents=True)
    _git("init", "-q", "-b", "main", cwd=repo)
    (repo / "README").write_text("x")
    _git("add", ".", cwd=repo)
    _git("commit", "-q", "-m", "init", cwd=repo)
    feature = tmp_path / "repo-feature"
    _git("worktree", "add", "-q", "-b", "feature", str(feature), cwd=repo)
    plain = tmp_path / "plain"
    (plain / "inner").mkdir(parents=True)
    return {
        "repo": repo.resolve(),
        "feature": feature.resolve(),
        "plain": plain.resolve(),
        "other": (tmp_path / "elsewhere").resolve(),
    }
