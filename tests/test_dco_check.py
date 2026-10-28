# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``dco check`` and ``dco match`` against real git repositories.

``check`` must examine the commits reachable from ``HEAD`` as well as
those on remote-tracking branches, and must not crash in a repository
without a remote. ``match`` must report only commits whose sign-off
email differs from the author's. Both must accept a relative path and
leave the caller's working directory unchanged.

Each repository lives under ``tmp_path``. Its remote is a local bare
repository, so no test reaches the network, and git runs without the
user's or the system's configuration.
"""

import os
import subprocess
from collections.abc import Callable
from pathlib import Path
from typing import Protocol

import pytest
from click.testing import CliRunner as ClickRunner
from typer.testing import CliRunner as TyperRunner

from lftools_uv.cli import cli
from lftools_uv.typer_apps.dco import dco_app

AUTHOR_NAME = "Scratch Author"
AUTHOR_EMAIL = "scratch@example.org"
OTHER_SIGNOFF = "Signed-off-by: Someone <other@example.org>"


class Result(Protocol):
    """The parts of a Click or Typer test result these tests read."""

    @property
    def exit_code(self) -> int: ...

    @property
    def output(self) -> str: ...


Runner = Callable[[str, str], Result]


def _run_click(cmd: str, repo: str) -> Result:
    result: Result = ClickRunner().invoke(cli, ["dco", cmd, repo], obj={})
    return result


def _run_typer(cmd: str, repo: str) -> Result:
    result: Result = TyperRunner().invoke(dco_app, [cmd, repo])
    return result


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _git(cwd: Path, *args: str) -> str:
    return subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True).stdout.strip()


def _commit(repo: Path, name: str, *, signoff: str | None = "-s") -> str:
    """Commit a new file and return the commit hash.

    ``signoff`` is ``"-s"`` for a sign-off matching the author, a trailer
    line to append to the message by hand, or ``None`` for no sign-off.
    """
    (repo / name).write_text(f"{name}\n")
    _git(repo, "add", name)
    message = f"Add {name}"
    args = ["commit", "-q"]
    if signoff == "-s":
        args.append("-s")
    elif signoff:
        message = f"{message}\n\n{signoff}"
    _git(repo, *args, "-m", message)
    return _git(repo, "rev-parse", "HEAD")


def _push(repo: Path) -> None:
    _git(repo, "push", "-q", "origin", "HEAD:main")
    _git(repo, "fetch", "-q", "origin")


def _exempt(repo: Path, *lines: str) -> None:
    signoffs = repo / "dco_signoffs"
    signoffs.mkdir()
    (signoffs / "exemption.txt").write_text("\n".join(lines) + "\n")


@pytest.fixture(autouse=True)
def _isolated(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", AUTHOR_NAME)
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", AUTHOR_EMAIL)
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.chdir(tmp_path)


@pytest.fixture
def repo(tmp_path: Path) -> tuple[Path, str]:
    """Build a clone of a bare origin holding one signed-off commit.

    Returns the clone's path and the hash of that commit.
    """
    origin = tmp_path / "origin.git"
    work = tmp_path / "work"
    _git(tmp_path, "init", "-q", "--bare", "-b", "main", str(origin))
    _git(tmp_path, "clone", "-q", str(origin), str(work))
    _git(work, "symbolic-ref", "HEAD", "refs/heads/main")
    first = _commit(work, "first.txt")
    _push(work)
    return work, first


@pytest.fixture
def solo(tmp_path: Path) -> Path:
    """Initialise a repository with no remote."""
    path = tmp_path / "solo"
    _git(tmp_path, "init", "-q", "-b", "main", str(path))
    return path


@FRONT_ENDS
class TestCheckHead:
    """``check`` examines commits that are not on a remote branch."""

    def test_unsigned_on_detached_head(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        _git(work, "checkout", "-q", "--detach")
        unsigned = _commit(work, "second.txt", signoff=None)
        result = run("check", str(work))
        assert result.exit_code == 1
        assert unsigned in result.output

    def test_unsigned_on_local_branch(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        _git(work, "checkout", "-q", "-b", "topic")
        unsigned = _commit(work, "second.txt", signoff=None)
        result = run("check", str(work))
        assert result.exit_code == 1
        assert unsigned in result.output

    def test_unsigned_without_remote(self, run: Runner, solo: Path) -> None:
        unsigned = _commit(solo, "only.txt", signoff=None)
        result = run("check", str(solo))
        assert result.exit_code == 1
        assert unsigned in result.output

    def test_signed_without_remote(self, run: Runner, solo: Path) -> None:
        _commit(solo, "only.txt")
        result = run("check", str(solo))
        assert result.exit_code == 0

    def test_match_mismatch_on_detached_head(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        _git(work, "checkout", "-q", "--detach")
        mismatched = _commit(work, "second.txt", signoff=OTHER_SIGNOFF)
        result = run("match", str(work))
        assert result.exit_code == 1
        assert mismatched in result.output


@FRONT_ENDS
class TestMatchMismatches:
    """``match`` reports only sign-offs that differ from the author."""

    def test_matching_signoff_passes(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        result = run("match", str(work))
        assert result.exit_code == 0

    def test_reports_only_mismatch(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, first = repo
        mismatched = _commit(work, "second.txt", signoff=OTHER_SIGNOFF)
        _push(work)
        result = run("match", str(work))
        assert result.exit_code == 1
        assert mismatched in result.output
        assert first not in result.output

    def test_exempted_mismatch_passes(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        mismatched = _commit(work, "second.txt", signoff=OTHER_SIGNOFF)
        _push(work)
        _exempt(work, AUTHOR_EMAIL, mismatched)
        result = run("match", str(work))
        assert result.exit_code == 0


@FRONT_ENDS
class TestWorkingDirectory:
    """``check`` and ``match`` keep the caller's working directory."""

    @pytest.mark.parametrize("cmd", ["check", "match"])
    def test_cwd_unchanged(self, run: Runner, cmd: str, repo: tuple[Path, str], tmp_path: Path) -> None:
        work, _ = repo
        run(cmd, str(work))
        assert os.getcwd() == str(tmp_path)

    def test_relative_path(self, run: Runner, repo: tuple[Path, str]) -> None:
        result = run("check", repo[0].name)
        assert result.exit_code == 0


@FRONT_ENDS
class TestCheckRemote:
    """``check`` behaviour on remote branches, unchanged by the fixes."""

    def test_signed_clone_passes(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        result = run("check", str(work))
        assert result.exit_code == 0

    def test_unsigned_pushed_commit_fails(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        unsigned = _commit(work, "second.txt", signoff=None)
        _push(work)
        result = run("check", str(work))
        assert result.exit_code == 1
        assert unsigned in result.output

    def test_exempted_commit_passes(self, run: Runner, repo: tuple[Path, str]) -> None:
        work, _ = repo
        unsigned = _commit(work, "second.txt", signoff=None)
        _push(work)
        _exempt(work, unsigned)
        result = run("check", str(work))
        assert result.exit_code == 0
