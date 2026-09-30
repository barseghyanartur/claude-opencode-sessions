"""Decide which sessions belong to "this repository".

Mirrors Claude Code's ``/resume`` picker:

* ``worktree`` (default): the current git worktree, i.e. its top-level
  directory and everything below it. Outside git: the directory and below.
* ``repo``: every worktree of the current repository (``Ctrl+W`` in
  ``/resume``), plus sessions of the same project whose worktree directory
  no longer exists (only reachable when ``Session.project_id`` is set).
* ``all``: every session on this machine (``Ctrl+A`` in ``/resume``).
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from collections.abc import Iterable
from dataclasses import dataclass, field

from .models import Session

__all__ = [
    "MODES",
    "Scope",
    "git_toplevel",
    "git_worktrees",
    "is_within",
    "normalize",
    "path_key",
    "resolve_scope",
]

MODES = ("worktree", "repo", "all")
_CASE_INSENSITIVE = sys.platform in ("darwin", "win32")


def normalize(path: str) -> str:
    """Absolute, symlink-resolved path without a trailing separator."""
    if not path:
        return ""
    path = os.path.expanduser(path)
    if not os.path.isabs(path) and os.sep == "/" and not path.startswith("."):
        path = "/" + path
    resolved = os.path.realpath(path)
    if len(resolved) > 1:
        resolved = resolved.rstrip(os.sep)
    return resolved


def path_key(path: str) -> str:
    """Comparison key for a normalised path (case-folded on macOS/Windows)."""
    return path.casefold() if _CASE_INSENSITIVE else path


def is_within(child: str, parent: str) -> bool:
    """True when ``child`` equals ``parent`` or lives below it (keys)."""
    if child == parent:
        return True
    prefix = parent if parent.endswith(os.sep) else parent + os.sep
    return child.startswith(prefix)


def _git(args: list[str], cwd: str) -> str | None:
    git = shutil.which("git")
    if not git or not os.path.isdir(cwd):
        return None
    try:
        result = subprocess.run(
            [git, "-C", cwd, *args],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return result.stdout if result.returncode == 0 else None


def git_toplevel(path: str) -> str | None:
    out = _git(["rev-parse", "--show-toplevel"], path)
    return normalize(out.strip()) if out and out.strip() else None


def git_worktrees(path: str) -> list[str]:
    out = _git(["worktree", "list", "--porcelain"], path)
    if not out:
        return []
    return [
        normalize(line[len("worktree ") :])
        for line in out.splitlines()
        if line.startswith("worktree ")
    ]


@dataclass
class Scope:
    mode: str
    cwd: str
    roots: list[str] = field(default_factory=list)
    in_git: bool = False

    @property
    def root(self) -> str:
        return self.roots[0] if self.roots else self.cwd

    def describe(self) -> str:
        if self.mode == "all":
            return "all sessions on this machine"
        if self.mode == "repo":
            count = len(self.roots)
            return f"all worktrees of {self.root} ({count} worktree(s))"
        kind = "git worktree" if self.in_git else "directory"
        return f"{kind} {self.root}"

    def matches(self, directory: str) -> bool:
        if self.mode == "all":
            return True
        key = path_key(normalize(directory))
        return any(is_within(key, path_key(root)) for root in self.roots)

    def filter(self, sessions: Iterable[Session]) -> list[Session]:
        sessions = list(sessions)
        if self.mode == "all":
            return sessions
        selected = [s for s in sessions if self.matches(s.directory)]
        if self.mode == "repo":
            projects = {s.project_id for s in selected if s.project_id} - {"global"}
            chosen = {s.id for s in selected}
            selected.extend(
                s
                for s in sessions
                if s.id not in chosen
                and s.project_id in projects
                and not os.path.isdir(normalize(s.directory))
            )
        return selected


def resolve_scope(path: str | None = None, mode: str = "worktree") -> Scope:
    if mode not in MODES:
        raise ValueError(f"unknown scope {mode!r}; expected one of {MODES}")
    cwd = normalize(path or os.getcwd())
    top = git_toplevel(cwd)
    if mode == "all":
        return Scope(mode, cwd, [top or cwd], in_git=bool(top))
    if top is None:
        return Scope(mode, cwd, [cwd], in_git=False)
    if mode == "repo":
        roots = git_worktrees(top) or [top]
        if top in roots:
            roots.remove(top)
        return Scope(mode, cwd, [top, *roots], in_git=True)
    return Scope(mode, cwd, [top], in_git=True)
