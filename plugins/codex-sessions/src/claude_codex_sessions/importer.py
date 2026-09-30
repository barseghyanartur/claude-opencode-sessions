"""Import Codex sessions as Claude Code conversations.

Each imported session becomes a Claude Code transcript
(``<claude config>/projects/<project>/<uuid>.jsonl``), so it shows up in
``/resume`` / ``claude --resume`` and can be continued like any Claude
session. Nothing is ever overwritten:

* The Claude session id is derived from the Codex session id **and** a
  hash of its content (``uuid5``). Importing an unchanged session again
  maps to the same file, which already exists, so it is skipped.
* A session whose content changed since the last import gets a new file,
  titled with the next free suffix: ``Title``, ``Title (1)``, ``Title (2)``…
* Files are written to a temporary name and then hard-linked into place,
  which fails instead of replacing an existing file.

Claude Code's transcript format is internal; this module writes the minimal
subset it needs (a ``custom-title`` entry plus a chain of ``user`` /
``assistant`` messages). Tool calls are summarised as text.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import subprocess
import uuid
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .errors import CodexSessionsError
from .models import Message, Session
from .render import tool_summary, truncate

__all__ = [
    "MARKER_KEY",
    "TITLE_PREFIX",
    "ImportResult",
    "build_conversation",
    "claude_project_dir",
    "content_hash",
    "existing_imports",
    "import_session",
    "project_dir_name",
]

MARKER_KEY = "codexImport"
TITLE_PREFIX = "[codex] "
FORMAT_VERSION = 1
_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "claude-codex-sessions")
_SYNTHETIC_MODEL = "<synthetic>"
_MAX_DIR_NAME = 200
_TOOL_OUTPUT_LIMIT = 2000


class ImportFailedError(CodexSessionsError):
    """Import-specific failure (e.g. the Claude project dir can't be found)."""


# -- locating Claude's project directory ------------------------------------


def claude_config_dir() -> Path:
    env = os.environ.get("CLAUDE_CONFIG_DIR")
    return Path(env).expanduser() if env else Path.home() / ".claude"


def project_dir_name(project_root: str) -> str:
    """Claude Code's directory name for a project path (non-alnum → ``-``)."""
    return re.sub(r"[^a-zA-Z0-9]", "-", project_root)


def claude_project_dir(
    project_root: str,
    *,
    transcript_path: str | None = None,
    explicit: str | None = None,
) -> Path:
    """Where Claude Code keeps transcripts for ``project_root``.

    Preference: explicit path; the directory of the running session's
    transcript (exact, handles every Claude Code setting); the derived name.
    """
    if explicit:
        return Path(explicit).expanduser()
    if transcript_path:
        return Path(transcript_path).expanduser().parent
    projects = claude_config_dir() / "projects"
    name = project_dir_name(project_root)
    if len(name) <= _MAX_DIR_NAME:
        return projects / name
    # Long paths get a hash suffix we can't reproduce; reuse an existing dir.
    candidates = sorted(projects.glob(name[:_MAX_DIR_NAME] + "-*"))
    if len(candidates) == 1:
        return candidates[0]
    raise ImportFailedError(
        f"can't determine Claude's project directory for {project_root} "
        "(path too long); pass --claude-project-dir"
    )


# -- conversation ------------------------------------------------------------


@dataclass
class Turn:
    role: str
    text: str
    time_ms: int | None = None


def _user_text(message: Message) -> str:
    chunks = [
        p.text.strip() for p in message.parts if p.kind == "text" and p.text.strip()
    ]
    return "\n\n".join(chunks)


def _assistant_text(message: Message, with_tool_output: bool) -> str:
    chunks: list[str] = []
    for part in message.parts:
        if part.kind == "text" and part.text.strip():
            chunks.append(part.text.strip())
        elif part.kind == "tool":
            line = tool_summary(part)
            if with_tool_output and part.tool_output:
                output = truncate(part.tool_output.strip(), _TOOL_OUTPUT_LIMIT)
                line += "\n" + "\n".join("    " + x for x in output.splitlines())
            chunks.append(line)
        # "reasoning" parts are dropped, like Claude Code's own thinking blocks.
    return "\n\n".join(chunks)


def build_conversation(
    messages: Iterable[Message], *, with_tool_output: bool = False
) -> list[Turn]:
    """Alternating user/assistant turns with plain-text content."""
    turns: list[Turn] = []
    for message in messages:
        if message.role == "user":
            role, text = "user", _user_text(message)
        elif message.role == "assistant":
            role, text = "assistant", _assistant_text(message, with_tool_output)
        else:
            continue
        if not text:
            continue
        if turns and turns[-1].role == role:
            turns[-1].text += "\n\n" + text
        else:
            turns.append(Turn(role, text, message.time_created))
    return turns


def content_hash(turns: list[Turn]) -> str:
    payload = json.dumps(
        [[t.role, t.text] for t in turns], ensure_ascii=False, separators=(",", ":")
    )
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def claude_session_id(codex_id: str, digest: str) -> str:
    return str(uuid.uuid5(_NAMESPACE, f"{codex_id}:{digest}"))


# -- existing imports -----------------------------------------------------------


@dataclass
class ExistingImport:
    path: Path
    codex_id: str
    content_hash: str
    suffix: int


def _read_marker(path: Path) -> dict[str, Any] | None:
    try:
        with path.open(encoding="utf-8") as handle:
            first = handle.readline()
    except OSError:
        return None
    if MARKER_KEY not in first:
        return None
    try:
        entry = json.loads(first)
    except ValueError:
        return None
    marker = entry.get(MARKER_KEY) if isinstance(entry, dict) else None
    return marker if isinstance(marker, dict) else None


def existing_imports(project_dir: Path) -> dict[str, list[ExistingImport]]:
    """Map Codex session id → imports already present in ``project_dir``."""
    found: dict[str, list[ExistingImport]] = {}
    if not project_dir.is_dir():
        return found
    for path in project_dir.glob("*.jsonl"):
        marker = _read_marker(path)
        if not marker or not marker.get("sessionId"):
            continue
        item = ExistingImport(
            path=path,
            codex_id=str(marker["sessionId"]),
            content_hash=str(marker.get("contentHash", "")),
            suffix=int(marker.get("suffix", 0) or 0),
        )
        found.setdefault(item.codex_id, []).append(item)
    return found


# -- writing -----------------------------------------------------------------


def _iso(ms: int | None) -> str:
    moment = (
        dt.datetime.fromtimestamp(ms / 1000, tz=dt.timezone.utc)
        if ms
        else dt.datetime.now(tz=dt.timezone.utc)
    )
    return moment.strftime("%Y-%m-%dT%H:%M:%S.") + f"{moment.microsecond // 1000:03d}Z"


def _git_branch(path: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", path, "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return ""
    return result.stdout.strip() if result.returncode == 0 else ""


def _header(session: Session) -> str:
    when = _iso(session.time_updated)[:16].replace("T", " ")
    return (
        f"[Imported from Codex session {session.id} — “{session.title}”, "
        f"{session.directory}, last updated {when} UTC. Tool calls are summarised "
        "as “→ tool: `args`” lines; their output is not included.]"
    )


def transcript_entries(
    session: Session,
    turns: list[Turn],
    *,
    claude_id: str,
    title: str,
    digest: str,
    suffix: int,
    cwd: str,
    git_branch: str = "",
) -> list[dict[str, Any]]:
    marker = {
        "sessionId": session.id,
        "contentHash": digest,
        "suffix": suffix,
        "directory": session.directory,
        "importedAt": _iso(None),
        "formatVersion": FORMAT_VERSION,
    }
    entries: list[dict[str, Any]] = [
        {
            "type": "custom-title",
            "customTitle": title,
            "sessionId": claude_id,
            MARKER_KEY: marker,
        }
    ]
    turns = list(turns)
    if turns and turns[0].role != "user":
        turns.insert(0, Turn("user", "(conversation started by the assistant)"))
    if turns and turns[-1].role == "user":
        turns.append(Turn("assistant", "[The Codex session ended here.]"))
    parent: str | None = None
    base = uuid.UUID(claude_id)
    for index, turn in enumerate(turns):
        entry_uuid = str(uuid.uuid5(base, str(index)))
        text = turn.text
        if index == 0:
            text = _header(session) + "\n\n" + text
        entry: dict[str, Any] = {
            "parentUuid": parent,
            "isSidechain": False,
            "userType": "external",
            "cwd": cwd,
            "sessionId": claude_id,
            "gitBranch": git_branch,
            "type": turn.role,
            "uuid": entry_uuid,
            "timestamp": _iso(turn.time_ms),
        }
        if turn.role == "user":
            entry["message"] = {"role": "user", "content": text}
        else:
            entry["message"] = {
                "id": f"msg_codex_{entry_uuid.replace('-', '')}",
                "type": "message",
                "role": "assistant",
                "model": _SYNTHETIC_MODEL,
                "content": [{"type": "text", "text": text}],
                "stop_reason": "end_turn",
                "stop_sequence": None,
                "usage": {
                    "input_tokens": 0,
                    "output_tokens": 0,
                    "cache_creation_input_tokens": 0,
                    "cache_read_input_tokens": 0,
                },
            }
        entries.append(entry)
        parent = entry_uuid
    return entries


def _write_new(path: Path, entries: list[dict[str, Any]]) -> bool:
    """Write ``path`` atomically; return False if it already exists."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    data = "".join(json.dumps(e, ensure_ascii=False) + "\n" for e in entries)
    with tmp.open("x", encoding="utf-8") as handle:
        handle.write(data)
        handle.flush()
        os.fsync(handle.fileno())
    try:
        os.link(tmp, path)
    except FileExistsError:
        return False
    finally:
        tmp.unlink()
    return True


# -- orchestration -------------------------------------------------------------


@dataclass
class ImportResult:
    session: Session
    status: str  # imported | unchanged | empty | would-import
    title: str = ""
    claude_id: str | None = None
    path: Path | None = None
    turns: int = 0
    notes: list[str] = field(default_factory=list)


def _title(session: Session, suffix: int) -> str:
    title = TITLE_PREFIX + (session.title or session.id)
    return f"{title} ({suffix})" if suffix else title


def import_session(
    session: Session,
    messages: list[Message],
    *,
    project_dir: Path,
    cwd: str,
    existing: dict[str, list[ExistingImport]],
    with_tool_output: bool = False,
    dry_run: bool = False,
    git_branch: str | None = None,
) -> ImportResult:
    turns = build_conversation(messages, with_tool_output=with_tool_output)
    if not turns:
        return ImportResult(session, "empty")
    digest = content_hash(turns)
    claude_id = claude_session_id(session.id, digest)
    path = project_dir / f"{claude_id}.jsonl"
    previous = existing.get(session.id, [])
    same = [p for p in previous if p.content_hash == digest]
    if path.exists() or same:
        found = path if path.exists() else same[0].path
        return ImportResult(
            session, "unchanged", claude_id=found.stem, path=found, turns=len(turns)
        )
    suffix = max((p.suffix for p in previous), default=-1) + 1
    title = _title(session, suffix)
    if dry_run:
        return ImportResult(
            session, "would-import", title, claude_id, path, turns=len(turns)
        )
    branch = _git_branch(cwd) if git_branch is None else git_branch
    entries = transcript_entries(
        session,
        turns,
        claude_id=claude_id,
        title=title,
        digest=digest,
        suffix=suffix,
        cwd=cwd,
        git_branch=branch,
    )
    if not _write_new(path, entries):
        return ImportResult(
            session, "unchanged", claude_id=claude_id, path=path, turns=len(turns)
        )
    record = ExistingImport(path, session.id, digest, suffix)
    existing.setdefault(session.id, []).append(record)
    return ImportResult(session, "imported", title, claude_id, path, len(turns))
