"""Command line interface: ``claude-copilot-sessions``."""

from __future__ import annotations

import argparse
import json
import os
import platform
import sys
from collections.abc import Sequence

from . import __version__
from .errors import CopilotSessionsError
from .import_command import add_import_arguments, cmd_hook, cmd_import
from .locate import copilot_home, find_sessions_dir, session_dirs
from .render import render_list
from .scope import Scope, resolve_scope
from .service import Reader, open_reader

__all__ = ["build_parser", "main"]

PROG = "claude-copilot-sessions"


def _add_common(parser: argparse.ArgumentParser) -> None:
    parser.add_argument(
        "--path",
        help="directory to scope to (default: current directory)",
    )
    group = parser.add_mutually_exclusive_group()
    group.add_argument(
        "--worktrees",
        dest="scope",
        action="store_const",
        const="repo",
        help="include every worktree of the current git repository",
    )
    group.add_argument(
        "--all",
        dest="scope",
        action="store_const",
        const="all",
        help="include sessions from every directory",
    )
    parser.set_defaults(scope="worktree")
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument(
        "--copilot-home",
        help="path to the Copilot CLI home directory "
        "(default: $COPILOT_HOME or ~/.copilot)",
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Import GitHub Copilot CLI sessions for the current repository into "
            "Claude Code (so they open with /resume), or list them. Scoping "
            "mirrors Claude Code's /resume: current worktree by default, "
            "--worktrees for all worktrees."
        ),
    )
    parser.add_argument(
        "--version", action="version", version=f"%(prog)s {__version__}"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="list sessions in scope, newest first")
    _add_common(p_list)
    p_list.add_argument(
        "-n", "--limit", type=int, default=20, help="max rows (0 = all)"
    )

    p_import = sub.add_parser(
        "import",
        help="import sessions into Claude Code (they then show up in /resume)",
    )
    add_import_arguments(p_import)

    sub.add_parser(
        "hook",
        help="Claude Code UserPromptExpansion hook (reads the event from stdin)",
    )

    p_doctor = sub.add_parser("doctor", help="diagnose environment and sessions")
    p_doctor.add_argument("--path")
    p_doctor.add_argument("--copilot-home")
    return parser


def _emit(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _scope(args: argparse.Namespace) -> Scope:
    return resolve_scope(args.path, args.scope)


def cmd_list(args: argparse.Namespace, reader: Reader) -> int:
    scope = _scope(args)
    listing = reader.listing(scope)
    shown = listing.shown[: args.limit] if args.limit > 0 else listing.shown
    if args.format == "json":
        payload = {
            "scope": {"mode": scope.mode, "roots": scope.roots, "cwd": scope.cwd},
            "total": len(listing.shown),
            "sessions": [
                {"index": i, **s.to_dict()} for i, s in enumerate(shown, start=1)
            ],
            "notes": reader.notes,
        }
        _emit(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    _emit(
        render_list(
            shown,
            scope,
            total=len(listing.shown),
            backend=reader.describe(),
            notes=reader.notes,
        )
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    lines = [
        f"{PROG} {__version__}",
        f"python: {sys.version.split()[0]} ({sys.executable})",
        f"platform: {platform.platform()}",
    ]
    home = copilot_home(args.copilot_home)
    lines.append(f"copilot home: {home}")
    status = 0
    try:
        sessions_dir = find_sessions_dir(args.copilot_home)
        dirs = session_dirs(sessions_dir)
        lines.append(f"sessions dir: {sessions_dir} ({len(dirs)} session(s))")
        reader = Reader(home)
        sessions = reader.all_sessions()
        lines.append(f"sessions readable: {len(sessions)}")
        for note in reader.notes:
            lines.append(f"  note: {note}")
    except CopilotSessionsError as exc:
        lines.append(f"sessions dir: NOT USABLE — {exc}")
        status = 3
    try:
        for mode in ("worktree", "repo"):
            scope = resolve_scope(args.path, mode)
            lines.append(f"scope {mode}: {scope.describe()} roots={scope.roots}")
    except OSError as exc:  # pragma: no cover
        lines.append(f"scope: error — {exc}")
    lines.append(f"cwd: {os.getcwd()}")
    _emit("\n".join(lines) + "\n")
    return status


def main(argv: Sequence[str] | None = None) -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(errors="replace")
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        if args.command == "doctor":
            return cmd_doctor(args)
        if args.command == "hook":
            return cmd_hook(args)
        if args.command == "import":
            return cmd_import(args)
        reader = open_reader(args.copilot_home)
        return cmd_list(args, reader)
    except CopilotSessionsError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:  # pragma: no cover
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
