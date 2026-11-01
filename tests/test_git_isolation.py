# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests that git commands run by tests stay in the repositories they create.

A git hook inherits variables such as ``GIT_DIR`` and ``GIT_INDEX_FILE``,
which tie git to the repository being committed to; in a linked worktree
both are absolute paths. When the pre-commit hook ran the suite from a
linked worktree, ``tests/test_dco_check.py`` reinitialised that repository
as bare, moved the worktree's HEAD and staged files in its index.

These tests export those variables for a throwaway repository with a
linked worktree, as such a hook would, then run git as the DCO tests do.
"""

import os
import subprocess
from collections.abc import Iterator
from pathlib import Path

import pytest


def _git_alone(cwd: Path, *args: str) -> str:
    """Run git with no ``GIT_*`` variable at all, so it can only act on *cwd*."""
    env = {name: value for name, value in os.environ.items() if not name.startswith("GIT_")}
    env.update(GIT_CONFIG_GLOBAL=os.devnull, GIT_CONFIG_NOSYSTEM="1")
    result = subprocess.run(["git", *args], cwd=cwd, env=env, check=True, capture_output=True, text=True)
    return result.stdout.strip()


@pytest.fixture(scope="module")
def outer(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Path]:
    """Create a repository with a linked worktree ``wt``, and export that worktree's hook variables.

    Module scope sets them before any per-test fixture runs, as a hook sets
    them before pytest starts. Yields the repository's path.
    """
    root = tmp_path_factory.mktemp("outer")
    repo = root / "repo"
    _git_alone(root, "init", "-q", "-b", "main", str(repo))
    (repo / "seed.txt").write_text("seed\n")
    _git_alone(repo, "add", "seed.txt")
    _git_alone(repo, "-c", "user.name=Test", "-c", "user.email=test@example.org", "commit", "-q", "-m", "Seed")
    _git_alone(repo, "worktree", "add", "-q", str(root / "wt"))
    gitdir = repo / ".git" / "worktrees" / "wt"
    with pytest.MonkeyPatch.context() as hook:
        hook.setenv("GIT_DIR", str(gitdir))
        hook.setenv("GIT_INDEX_FILE", str(gitdir / "index"))
        yield repo


@pytest.mark.usefixtures("outer")
def test_hook_variables_are_cleared() -> None:
    """A test never sees the variables that tie git to the outer repository."""
    assert "GIT_DIR" not in os.environ
    assert "GIT_INDEX_FILE" not in os.environ


def test_git_leaves_outer_repository_alone(outer: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The DCO tests' git commands change only the repositories they create.

    These are the commands of the ``repo`` and ``solo`` fixtures in
    ``tests/test_dco_check.py``, run from their working directories.
    """
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_AUTHOR_NAME", "Test")
    monkeypatch.setenv("GIT_AUTHOR_EMAIL", "test@example.org")
    monkeypatch.setenv("GIT_COMMITTER_NAME", "Test")
    monkeypatch.setenv("GIT_COMMITTER_EMAIL", "test@example.org")
    origin, work, solo = tmp_path / "origin.git", tmp_path / "work", tmp_path / "solo"
    results: list[subprocess.CompletedProcess[str]] = []

    def git(cwd: Path, *args: str) -> None:
        results.append(subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True))

    git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    git(tmp_path, "clone", "-q", str(origin), str(work))
    git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    work.mkdir(exist_ok=True)
    (work / "first.txt").write_text("first\n")
    git(work, "add", "first.txt")
    git(work, "commit", "-q", "-s", "-m", "Add first.txt")
    git(tmp_path, "init", "-q", "-b", "main", str(solo))

    assert _git_alone(outer, "config", "--get", "core.bare") == "false"
    assert (outer / ".git" / "worktrees" / "wt" / "HEAD").read_text() == "ref: refs/heads/wt\n"
    assert _git_alone(outer.parent / "wt", "ls-files").splitlines() == ["seed.txt"]
    assert [result.returncode for result in results] == [0] * 6, [result.stderr for result in results]
    assert _git_alone(work, "log", "--format=%s") == "Add first.txt"
    assert (solo / ".git").is_dir()
