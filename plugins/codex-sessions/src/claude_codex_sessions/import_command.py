"""``import`` command and the Claude Code ``UserPromptExpansion`` hook."""

from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from collections import Counter
from collections.abc import Sequence
from pathlib import Path
from typing import Any

from .errors import CodexSessionsError
from .importer import ImportResult, claude_project_dir, existing_imports, import_session
from .render import cell, tilde
from .scope import Scope, resolve_scope
from .service import Reader, open_reader

__all__ = ["add_import_arguments", "hook_main", "render_report", "run_import"]

COMMAND_NAMES = {"import", "codex-sessions:import"}


def add_import_arguments(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--path", help="project directory (default: current directory)")
    parser.add_argument(
        "--worktrees",
        action="store_true",
        help="include sessions from every worktree of the repository",
    )
    parser.add_argument(
        "--dry-run", action="store_true", help="show what would be imported"
    )
    parser.add_argument(
        "--with-tool-output",
        action="store_true",
        help="include (truncated) tool output in the imported conversation",
    )
    parser.add_argument(
        "--claude-project-dir",
        help="Claude Code transcript directory to import into "
        "(default: derived from the project path)",
    )
    parser.add_argument(
        "--codex-home",
        help="path to the Codex home directory (default: $CODEX_HOME or ~/.codex)",
    )


def run_import(
    reader: Reader,
    scope: Scope,
    *,
    project_dir: Path,
    cwd: str,
    dry_run: bool = False,
    with_tool_output: bool = False,
) -> list[ImportResult]:
    listing = reader.listing(scope)
    existing = existing_imports(project_dir)
    results = []
    for session in reversed(listing.shown):  # oldest first
        messages = reader.messages(session)
        results.append(
            import_session(
                session,
                messages,
                project_dir=project_dir,
                cwd=cwd,
                existing=existing,
                with_tool_output=with_tool_output,
                dry_run=dry_run,
            )
        )
    return results


def render_report(
    results: list[ImportResult],
    scope: Scope,
    project_dir: Path,
    notes: Sequence[str] = (),
) -> str:
    lines = [
        f"Codex → Claude Code import · {scope.describe()}",
        f"into {tilde(str(project_dir))}",
        "",
    ]
    if not results:
        lines.append("No Codex sessions found for this project.")
    for result in reversed(results):  # newest first, like /resume
        label = result.title or f"[codex] {result.session.title}"
        if result.status == "empty":
            label += " (no conversation text)"
        lines.append(f"  {result.status:<12} {cell(label, 80)}")
    counts = Counter(r.status for r in results)
    order = ("imported", "would-import", "unchanged", "empty")
    summary = ", ".join(f"{counts[k]} {k}" for k in order if counts.get(k))
    lines.append("")
    if summary:
        lines.append(summary)
    lines.extend(f"note: {note}" for note in notes)
    if counts.get("imported"):
        lines.append('Open them with /resume — titles start with "[codex]".')
    elif counts.get("would-import"):
        lines.append("Dry run: nothing was written.")
    return "\n".join(lines) + "\n"


def cmd_import(args: argparse.Namespace) -> int:
    reader = open_reader(args.codex_home)
    scope = resolve_scope(args.path, "repo" if args.worktrees else "worktree")
    cwd = scope.cwd
    project_dir = claude_project_dir(cwd, explicit=args.claude_project_dir)
    results = run_import(
        reader,
        scope,
        project_dir=project_dir,
        cwd=cwd,
        dry_run=args.dry_run,
        with_tool_output=args.with_tool_output,
    )
    sys.stdout.write(render_report(results, scope, project_dir, reader.notes))
    return 0


def _hook_argv(data: dict[str, Any]) -> list[str]:
    raw: Any = data.get("command_args")
    if raw is None:
        raw = data.get("command_input")
    if isinstance(raw, dict):
        raw = " ".join(str(v) for v in raw.values() if isinstance(v, (str, int)))
    if not isinstance(raw, str):
        return []
    try:
        return shlex.split(raw)
    except ValueError:
        return raw.split()


def hook_main(stdin: str) -> str | None:
    """Handle a ``UserPromptExpansion`` event; return the JSON to print.

    Returns ``None`` for commands that aren't ours (the hook then stays
    silent and Claude Code proceeds normally).
    """
    try:
        data = json.loads(stdin)
    except ValueError:
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("command_name", "")) not in COMMAND_NAMES:
        return None
    parser = argparse.ArgumentParser(prog="/codex-sessions:import", add_help=False)
    add_import_arguments(parser)
    try:
        args = parser.parse_args(_hook_argv(data))
    except SystemExit:
        reason = "Usage: " + parser.format_usage().replace("usage: ", "")
        return json.dumps({"decision": "block", "reason": reason})
    cwd = (
        args.path
        or os.environ.get("CLAUDE_PROJECT_DIR")
        or str(data.get("cwd") or "")
        or os.getcwd()
    )
    try:
        reader = open_reader(args.codex_home)
        scope = resolve_scope(cwd, "repo" if args.worktrees else "worktree")
        project_dir = claude_project_dir(
            cwd,
            transcript_path=None
            if args.claude_project_dir
            else data.get("transcript_path"),
            explicit=args.claude_project_dir,
        )
        results = run_import(
            reader,
            scope,
            project_dir=project_dir,
            cwd=cwd,
            dry_run=args.dry_run,
            with_tool_output=args.with_tool_output,
        )
        reason = render_report(results, scope, project_dir, reader.notes)
    except (CodexSessionsError, OSError) as exc:
        reason = f"Codex import failed: {exc}"
    return json.dumps({"decision": "block", "reason": reason.rstrip()})


def cmd_hook(_args: argparse.Namespace) -> int:
    output = hook_main(sys.stdin.read())
    if output is not None:
        sys.stdout.write(output + "\n")
    return 0
