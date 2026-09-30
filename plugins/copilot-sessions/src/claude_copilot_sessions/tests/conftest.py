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


class EventsBuilder:
    """Build a Copilot CLI session (``workspace.yaml`` + ``events.jsonl``)."""

    def __init__(
        self,
        session_id: str,
        cwd: str,
        *,
        started: int = NOW,
        copilot_version: str = "1.0.90",
        client_name: str = "github/cli",
        title: str | None = None,
    ) -> None:
        self.session_id = session_id
        self.cwd = cwd
        self.started = started
        self.copilot_version = copilot_version
        self.client_name = client_name
        self.title = title
        self.lines: list[dict[str, Any]] = []
        self._ts = started
        self._updated = started
        self._raw(
            "session.start",
            {
                "sessionId": session_id,
                "copilotVersion": copilot_version,
                "startTime": iso(started),
            },
        )

    def _raw(self, kind: str, data: dict[str, Any], *, advance_ms: int = 1000) -> None:
        self._ts += advance_ms
        self._updated = self._ts
        self.lines.append(
            {
                "type": kind,
                "data": data,
                "id": f"evt_{len(self.lines)}",
                "timestamp": iso(self._ts),
                "parentId": None,
            }
        )

    def system(self, text: str = "You are the GitHub Copilot CLI.") -> EventsBuilder:
        self._raw("system.message", {"role": "system", "content": text})
        return self

    def user(self, text: str, *, message_id: str | None = None) -> EventsBuilder:
        message_id = message_id or f"user_{len(self.lines)}"
        self._raw(
            "user.message",
            {
                "content": text,
                "transformedContent": f"<current_datetime>2026-01-01</current_datetime>\n\n{text}",
                "messageId": message_id,
            },
        )
        return self

    def assistant(
        self,
        text: str = "",
        *,
        tool_requests: list[dict[str, Any]] | None = None,
        model: str = "test-model",
        message_id: str | None = None,
    ) -> EventsBuilder:
        message_id = message_id or f"asst_{len(self.lines)}"
        self._raw(
            "assistant.message",
            {
                "content": text,
                "toolRequests": tool_requests or [],
                "messageId": message_id,
                "model": model,
            },
        )
        return self

    def tool_request(
        self, name: str, args: Any, *, call_id: str | None = None
    ) -> tuple[dict[str, Any], str]:
        call_id = call_id or f"call_{len(self.lines)}"
        return {"toolCallId": call_id, "name": name, "arguments": args}, call_id

    def tool_complete(
        self, call_id: str, output: Any, *, success: bool = True
    ) -> EventsBuilder:
        self._raw(
            "tool.execution_complete",
            {"toolCallId": call_id, "result": {"content": output}, "success": success},
        )
        return self

    def shutdown(self) -> EventsBuilder:
        self._raw("session.shutdown", {"shutdownType": "routine"})
        return self

    def write(self, session_dir: Path) -> Path:
        session_dir.mkdir(parents=True, exist_ok=True)
        workspace = {
            "id": self.session_id,
            "cwd": self.cwd,
            "client_name": self.client_name,
            "created_at": iso(self.started),
            "updated_at": iso(self._updated),
        }
        if self.title:
            workspace["name"] = self.title
        (session_dir / "workspace.yaml").write_text(
            "\n".join(f"{k}: {v}" for k, v in workspace.items()) + "\n"
        )
        with (session_dir / "events.jsonl").open("w", encoding="utf-8") as handle:
            for line in self.lines:
                handle.write(json.dumps(line, ensure_ascii=False) + "\n")
        return session_dir


def session_path(home: Path, session_id: str) -> Path:
    return home / "session-state" / session_id


@pytest.fixture
def copilot_home(tmp_path: Path) -> Path:
    home = tmp_path / "copilot_home"
    (home / "session-state").mkdir(parents=True)
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
