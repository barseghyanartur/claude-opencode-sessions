"""Command line interface: ``claude-opencode-sessions``."""

from __future__ import annotations

import argparse
import json
import os
import platform
import shutil
import sqlite3
import sys
from collections.abc import Sequence

from . import __version__
from .errors import OpencodeSessionsError
from .import_command import add_import_arguments, cmd_hook, cmd_import
from .locate import candidate_paths, find_db
from .render import render_list
from .scope import Scope, resolve_scope
from .service import BACKENDS, Context, open_context

__all__ = ["build_parser", "main"]

PROG = "claude-opencode-sessions"


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
    parser.add_argument(
        "--include-archived", action="store_true", help="show archived sessions"
    )
    parser.add_argument(
        "--include-subagents", action="store_true", help="show sub-agent sessions"
    )
    parser.add_argument("--format", choices=("md", "json"), default="md")
    parser.add_argument("--backend", choices=BACKENDS, default="auto")
    parser.add_argument("--db", help="path to opencode.db (default: auto-detect)")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog=PROG,
        description=(
            "Import opencode sessions for the current repository into Claude "
            "Code (so they open with /resume), or list them. Scoping mirrors "
            "Claude Code's /resume: current worktree by default, --worktrees "
            "for all worktrees."
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

    p_doctor = sub.add_parser("doctor", help="diagnose environment and database")
    p_doctor.add_argument("--path")
    p_doctor.add_argument("--db")
    return parser


def _emit(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()


def _scope(args: argparse.Namespace) -> Scope:
    return resolve_scope(args.path, args.scope)


def cmd_list(args: argparse.Namespace, ctx: Context) -> int:
    scope = _scope(args)
    listing = ctx.listing(scope, args.include_archived, args.include_subagents)
    shown = listing.shown[: args.limit] if args.limit > 0 else listing.shown
    if args.format == "json":
        payload = {
            "scope": {"mode": scope.mode, "roots": scope.roots, "cwd": scope.cwd},
            "backend": ctx.backend_name,
            "total": len(listing.shown),
            "hidden_archived": listing.hidden_archived,
            "hidden_subagents": listing.hidden_subagents,
            "sessions": [
                {"index": i, **s.to_dict()} for i, s in enumerate(shown, start=1)
            ],
            "notes": ctx.notes,
        }
        _emit(json.dumps(payload, indent=2, ensure_ascii=False) + "\n")
        return 0
    _emit(
        render_list(
            shown,
            scope,
            hidden_archived=listing.hidden_archived,
            hidden_subagents=listing.hidden_subagents,
            total=len(listing.shown),
            backend=ctx.describe(),
            notes=ctx.notes,
        )
    )
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    lines = [
        f"{PROG} {__version__}",
        f"python: {sys.version.split()[0]} ({sys.executable})",
        f"platform: {platform.platform()}",
    ]
    opencode = shutil.which("opencode")
    lines.append(f"opencode on PATH: {opencode or 'no'}")
    lines.append("db candidates: " + ", ".join(str(p) for p in candidate_paths()))
    status = 0
    try:
        db = find_db(args.db)
        lines.append(f"db: {db} ({db.stat().st_size:,} bytes)")
        from .sqlite_backend import SqliteBackend

        backend = SqliteBackend(db)
        lines.append(f"layout: {backend.describe()}")
        for table, count in backend.table_report().items():
            lines.append(f"  {table}: {count:,} rows")
        sessions = backend.list_sessions()
        lines.append(f"sessions readable: {len(sessions)}")
        backend.close()
    except (OpencodeSessionsError, sqlite3.Error) as exc:
        lines.append(f"db: NOT USABLE — {exc}")
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
        ctx = open_context(args.backend, args.db)
        return cmd_list(args, ctx)
    except OpencodeSessionsError as exc:
        print(f"{PROG}: {exc}", file=sys.stderr)
        return exc.exit_code
    except BrokenPipeError:  # pragma: no cover
        return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
