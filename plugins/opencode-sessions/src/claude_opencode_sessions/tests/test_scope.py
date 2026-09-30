import os
import sys
from pathlib import Path

import pytest

from claude_opencode_sessions.models import Session
from claude_opencode_sessions.scope import (
    Scope,
    git_toplevel,
    git_worktrees,
    is_within,
    normalize,
    path_key,
    resolve_scope,
)


def s(sid: str, directory: str, project: str = "p") -> Session:
    return Session(id=sid, title=sid, directory=directory, project_id=project)


def test_normalize_repairs_missing_leading_slash(tmp_path: Path):
    assert normalize("Users/me/repo/") == os.path.realpath("/Users/me/repo")
    assert normalize("") == ""
    assert normalize(str(tmp_path) + "/") == str(tmp_path.resolve())
    assert normalize("/") == "/"


def test_normalize_resolves_symlinks(tmp_path: Path):
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    link.symlink_to(target)
    assert normalize(str(link)) == str(target.resolve())


def test_is_within():
    assert is_within("/a/b", "/a/b")
    assert is_within("/a/b/c", "/a/b")
    assert not is_within("/a/bc", "/a/b")
    assert is_within("/anything", "/")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS is case-insensitive")
def test_path_key_casefolds_on_macos():  # pragma: no cover - platform specific
    assert path_key("/Users/Me") == path_key("/users/me")


def test_invalid_mode():
    with pytest.raises(ValueError):
        resolve_scope("/", "nope")


def test_non_git_directory_scope(git_repo):
    plain = git_repo["plain"]
    scope = resolve_scope(str(plain / "inner"))
    assert not scope.in_git
    assert scope.roots == [str(plain / "inner")]
    sessions = [
        s("in", str(plain / "inner")),
        s("below", str(plain / "inner" / "x")),
        s("parent", str(plain)),
    ]
    assert [x.id for x in scope.filter(sessions)] == ["in", "below"]
    assert "directory" in scope.describe()


def test_worktree_scope_uses_git_toplevel(git_repo):
    repo, feature = git_repo["repo"], git_repo["feature"]
    scope = resolve_scope(str(repo / "sub" / "deep"))
    assert scope.in_git
    assert scope.root == str(repo)
    sessions = [
        s("root", str(repo)),
        s("sub", str(repo / "sub")),
        s("feature", str(feature)),
        s("other", "/somewhere/else"),
    ]
    assert [x.id for x in scope.filter(sessions)] == ["root", "sub"]
    assert "git worktree" in scope.describe()


def test_repo_scope_includes_all_worktrees(git_repo):
    repo, feature = git_repo["repo"], git_repo["feature"]
    assert git_toplevel(str(feature)) == str(feature)
    assert set(git_worktrees(str(repo))) == {str(repo), str(feature)}
    scope = resolve_scope(str(feature), "repo")
    assert scope.root == str(feature)  # current worktree first
    assert set(scope.roots) == {str(repo), str(feature)}
    sessions = [
        s("root", str(repo)),
        s("feature", str(feature / "x")),
        s("gone", str(repo.parent / "deleted-worktree")),  # same project, missing
        s("gone-other-project", str(repo.parent / "deleted2"), project="q"),
        s("global", str(repo.parent / "deleted3"), project="global"),
    ]
    assert [x.id for x in scope.filter(sessions)] == ["root", "feature", "gone"]
    assert "worktree(s)" in scope.describe()


def test_repo_scope_outside_git_behaves_like_worktree(git_repo):
    scope = resolve_scope(str(git_repo["plain"]), "repo")
    assert scope.roots == [str(git_repo["plain"])]


def test_all_scope_matches_everything(git_repo):
    scope = resolve_scope(str(git_repo["repo"]), "all")
    assert scope.matches("/whatever")
    assert len(scope.filter([s("a", "/x"), s("b", "/y")])) == 2
    assert scope.describe() == "all sessions on this machine"


def test_git_helpers_outside_repo(tmp_path: Path):
    assert git_toplevel(str(tmp_path / "missing")) is None
    assert git_worktrees(str(tmp_path / "missing")) == []


def test_scope_root_defaults_to_cwd():
    scope = Scope("worktree", "/x")
    assert scope.root == "/x"
