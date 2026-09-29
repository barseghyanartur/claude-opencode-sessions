from __future__ import annotations

import json
import shutil
import sqlite3
import subprocess
import sys
import textwrap
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest

FIXTURES = Path(__file__).parent / "fixtures"
NOW = 1_790_000_000_000  # ms
HOUR = 3_600_000


class DbBuilder:
    """Create opencode-like databases from the fixture schemas."""

    def __init__(self, path: Path, schema: str) -> None:
        self.path = path
        self.conn = sqlite3.connect(path)
        self.conn.executescript((FIXTURES / schema).read_text())
        self._part = 0

    def close(self) -> None:
        if self.conn is not None:
            self.conn.commit()
            self.conn.close()
            self.conn = None  # type: ignore[assignment]

    # -- 1.x --------------------------------------------------------------

    def session_1x(
        self,
        sid: str,
        directory: str,
        *,
        title: str = "",
        updated: int = NOW,
        project_id: str = "proj1",
        parent_id: str | None = None,
        archived: int | None = None,
        messages: list[tuple[dict[str, Any], list[dict[str, Any]]]] | None = None,
        table: str = "session",
    ) -> None:
        self.conn.execute(
            f"INSERT INTO {table} (id, project_id, parent_id, slug, directory, title,"
            " version, time_created, time_updated, time_archived, agent, model)"
            " VALUES (?, ?, ?, 'slug', ?, ?, '1.18.32', ?, ?, ?, 'build', ?)",
            (
                sid,
                project_id,
                parent_id,
                directory,
                title or f"Session {sid}",
                updated - HOUR,
                updated,
                archived,
                json.dumps({"id": "gpt-x", "providerID": "openai"}),
            ),
        )
        for index, (info, parts) in enumerate(messages or [], start=1):
            mid = f"{sid}_msg_{index:03d}"
            info = {"id": mid, "sessionID": sid, **info}
            info.setdefault("time", {"created": updated - HOUR + index * 1000})
            self.conn.execute(
                "INSERT INTO message (id, session_id, time_created, time_updated, data)"
                " VALUES (?, ?, ?, ?, ?)",
                (mid, sid, info["time"]["created"], updated, json.dumps(info)),
            )
            for part in parts:
                self._part += 1
                raw = part if isinstance(part, str) else json.dumps(part)
                self.conn.execute(
                    "INSERT INTO part (id, message_id, session_id, time_created,"
                    " time_updated, data) VALUES (?, ?, ?, ?, ?, ?)",
                    (f"prt_{self._part:06d}", mid, sid, updated, updated, raw),
                )

    # -- 2.x --------------------------------------------------------------

    def session_2x(
        self,
        sid: str,
        directory: str,
        *,
        title: str = "",
        updated: int = NOW,
        project_id: str = "proj1",
        parent_id: str | None = None,
        archived: int | None = None,
        rows: list[tuple[str, Any]] | None = None,
    ) -> None:
        self.conn.execute(
            "INSERT INTO session_v2 (id, project_id, parent_id, directory, title,"
            " agent, model, time_created, time_updated, time_archived)"
            " VALUES (?, ?, ?, ?, ?, 'build', ?, ?, ?, ?)",
            (
                sid,
                project_id,
                parent_id,
                directory,
                title or f"Session {sid}",
                json.dumps({"id": "gpt-x", "providerID": "openai"}),
                updated - HOUR,
                updated,
                archived,
            ),
        )
        for seq, (kind, data) in enumerate(rows or [], start=1):
            raw = data if isinstance(data, str) else json.dumps(data)
            self.conn.execute(
                "INSERT INTO session_message (id, session_id, type, time_created,"
                " time_updated, data, seq) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (
                    f"{sid}_sm_{seq:03d}",
                    sid,
                    kind,
                    updated - HOUR + seq,
                    updated,
                    raw,
                    seq,
                ),
            )


def text_of(message: Any) -> str:
    """Concatenated non-synthetic text parts of a parsed message."""
    return "\n\n".join(
        p.text for p in message.parts if p.kind == "text" and not p.synthetic
    ).strip()


def user(text: str, **extra: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    return {"role": "user", **extra}, [{"type": "text", "text": text}]


def assistant(
    *parts: dict[str, Any], **extra: Any
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    info = {
        "role": "assistant",
        "agent": "build",
        "modelID": "gpt-x",
        "providerID": "openai",
        "tokens": {"input": 100, "output": 20},
        "cost": 0.01,
        **extra,
    }
    return info, [{"type": "step-start"}, *parts, {"type": "step-finish"}]


def text(value: str) -> dict[str, Any]:
    return {"type": "text", "text": value}


def tool(
    name: str, args: dict[str, Any], output: str = "ok", status: str = "completed"
) -> dict[str, Any]:
    return {
        "type": "tool",
        "tool": name,
        "callID": "c1",
        "state": {"status": status, "input": args, "output": output, "title": name},
    }


@pytest.fixture
def db_1x(tmp_path: Path) -> Iterator[DbBuilder]:
    builder = DbBuilder(tmp_path / "opencode.db", "schema_1x.sql")
    yield builder
    builder.close()


@pytest.fixture
def db_2x(tmp_path: Path) -> Iterator[DbBuilder]:
    builder = DbBuilder(tmp_path / "opencode.db", "schema_2x.sql")
    yield builder
    builder.close()


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
            "PATH": __import__("os").environ.get("PATH", ""),
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


@pytest.fixture
def fake_opencode(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Install a fake ``opencode`` executable on PATH that serves fixture JSON."""
    bindir = tmp_path / "fakebin"
    bindir.mkdir()
    data = tmp_path / "fake-data.json"
    data.write_text(
        json.dumps(
            {
                "version": "1.18.32",
                "sessions": [
                    {
                        "id": "ses_cli_1",
                        "title": "From the CLI",
                        "directory": str(tmp_path / "proj"),
                        "projectID": "p",
                        "time": {"created": NOW - HOUR, "updated": NOW},
                    }
                ],
                "exports": {
                    "ses_cli_1": {
                        "info": {
                            "id": "ses_cli_1",
                            "title": "From the CLI",
                            "directory": str(tmp_path / "proj"),
                            "time": {"created": NOW - HOUR, "updated": NOW},
                        },
                        "messages": [
                            {
                                "info": {
                                    "id": "m1",
                                    "role": "user",
                                    "time": {"created": NOW - 10},
                                },
                                "parts": [
                                    {"type": "text", "text": "hello from export"}
                                ],
                            },
                            {
                                "info": {
                                    "id": "m2",
                                    "role": "assistant",
                                    "modelID": "gpt-x",
                                    "providerID": "openai",
                                    "time": {"created": NOW - 5},
                                },
                                "parts": [{"type": "text", "text": "hi back"}],
                            },
                        ],
                    }
                },
            }
        )
    )
    script = bindir / "opencode"
    script.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, sys
            data = json.load(open({str(data)!r}))
            args = sys.argv[1:]
            if args == ["--version"]:
                print(data["version"])
            elif args[:2] == ["session", "list"]:
                print("INFO some log line")
                print(json.dumps(data["sessions"]))
            elif args[:1] == ["export"]:
                sid = args[1]
                if sid not in data["exports"]:
                    print("Session not found", file=sys.stderr)
                    sys.exit(1)
                print("Exporting session: " + sid)
                print(json.dumps(data["exports"][sid]))
            elif args == ["db", "path"]:
                print(data.get("db_path", "/nonexistent/opencode.db"))
            else:
                sys.exit(2)
            """
        )
    )
    script.chmod(0o755)
    monkeypatch.setenv(
        "PATH", f"{bindir}{__import__('os').pathsep}{__import__('os').environ['PATH']}"
    )
    return data
