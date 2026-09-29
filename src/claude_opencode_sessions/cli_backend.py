"""Fallback backend that shells out to the ``opencode`` CLI.

Used when the database can't be read directly (missing, locked, or a schema
this package doesn't recognise):

* ``opencode session list --format json`` for listing,
* ``opencode export <id>`` for transcripts.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from typing import Any

from .errors import BackendError, NotFoundError
from .models import Message, Session, format_model
from .parse import as_dict, as_list, parse_v1_message

__all__ = ["MIN_VERSION", "CliBackend", "parse_version"]

MIN_VERSION = (1, 2)


def parse_version(text: str) -> tuple[int, ...] | None:
    match = re.search(r"(\d+)\.(\d+)(?:\.(\d+))?", text)
    if not match:
        return None
    return tuple(int(g) for g in match.groups() if g is not None)


def _extract_json(text: str) -> Any:
    """Parse the first JSON document in ``text`` (skipping log lines)."""
    decoder = json.JSONDecoder()
    for index, char in enumerate(text):
        if char in "[{":
            try:
                value, _ = decoder.raw_decode(text[index:])
            except ValueError:
                continue
            return value
    raise BackendError("opencode CLI did not return JSON")


def _get(obj: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def session_from_info(info: dict[str, Any]) -> Session:
    time = as_dict(info.get("time"))
    return Session(
        id=str(info.get("id", "")),
        title=str(info.get("title") or "(untitled)"),
        directory=str(_get(info, "directory", "cwd", "path") or ""),
        project_id=_get(info, "projectID", "project_id"),
        parent_id=_get(info, "parentID", "parent_id"),
        time_created=_get(time, "created") or _get(info, "time_created", "created"),
        time_updated=_get(time, "updated") or _get(info, "time_updated", "updated"),
        time_archived=_get(time, "archived") or _get(info, "time_archived"),
        agent=info.get("agent"),
        model=format_model(info.get("model")),
        version=info.get("version"),
        origin="cli",
    )


class CliBackend:
    name = "cli"

    def __init__(self, executable: str = "opencode", timeout: float = 120) -> None:
        exe = shutil.which(executable)
        if not exe:
            raise BackendError(f"`{executable}` not found on PATH")
        self.exe = exe
        self.timeout = timeout
        version_text = self._run(["--version"]).strip()
        self.version = parse_version(version_text)
        if self.version is None or self.version[:2] < MIN_VERSION:
            raise BackendError(
                f"opencode {version_text or '?'} is too old; "
                f"need >= {'.'.join(map(str, MIN_VERSION))}"
            )

    def _run(self, args: list[str], cwd: str | None = None) -> str:
        try:
            result = subprocess.run(
                [self.exe, *args],
                capture_output=True,
                text=True,
                timeout=self.timeout,
                cwd=cwd,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise BackendError(f"opencode {' '.join(args)} failed: {exc}") from exc
        if result.returncode != 0:
            detail = (result.stderr or result.stdout).strip().splitlines()
            raise BackendError(
                f"opencode {' '.join(args)} exited {result.returncode}: "
                f"{detail[-1] if detail else ''}"
            )
        return result.stdout

    def describe(self) -> str:
        return f"opencode CLI {'.'.join(map(str, self.version or ()))}"

    def list_sessions(self, cwd: str | None = None) -> list[Session]:
        workdir = cwd if cwd and os.path.isdir(cwd) else None
        data = _extract_json(
            self._run(["session", "list", "--format", "json"], cwd=workdir)
        )
        if isinstance(data, dict):
            data = data.get("sessions") or data.get("data") or []
        if not isinstance(data, list):
            raise BackendError("unexpected `opencode session list` output")
        return [session_from_info(item) for item in data if isinstance(item, dict)]

    def export(self, session_id: str) -> tuple[Session | None, list[Message]]:
        data = _extract_json(self._run(["export", session_id]))
        if not isinstance(data, dict):
            raise NotFoundError(f"opencode export {session_id}: unexpected output")
        info = data.get("info")
        session = session_from_info(info) if isinstance(info, dict) else None
        messages: list[Message] = []
        for index, item in enumerate(data.get("messages") or [], start=1):
            if not isinstance(item, dict):
                continue
            parts = as_list(item.get("parts"))
            messages.append(parse_v1_message(item.get("info"), parts, index))
        return session, messages

    def load_messages(self, session_id: str) -> tuple[list[Message], int]:
        _, messages = self.export(session_id)
        return messages, 0
