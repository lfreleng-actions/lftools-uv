# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the exit status of ``shell/version``'s ``version patch``.

``version patch`` fetches a git bundle, merges it and tags the release. If
any of those steps fails, the script must fail, rather than let a release
job go on without its patch or its tag.

The script runs under real bash and real git, in a repository under the
test's own directory, with a git configuration of the test's own and a
stub ``gpg`` that signs tags, or fails to when the test asks.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parent.parent / "shell" / "version"
BASH = shutil.which("bash") or "/bin/bash"
GIT = shutil.which("git") or "git"

# Signs whatever git passes it, as gpg does, or fails if $GPG_FAIL is set.
GPG_STUB = r"""
import os
import sys

sys.stdin.read()
if os.environ.get("GPG_FAIL"):
    print("gpg: signing failed: No secret key", file=sys.stderr)
    sys.exit(2)
sys.stderr.write("\n[GNUPG:] SIG_CREATED D 1 8 00 1700000000 0123456789ABCDEF\n")
sys.stdout.write("-----BEGIN PGP SIGNATURE-----\n\nc3R1Yg==\n-----END PGP SIGNATURE-----\n")
"""


@pytest.fixture
def env(tmp_path):
    """Return an environment whose git uses only a configuration of the test's own."""
    gpg = tmp_path / "gpg"
    gpg.write_text(f"#!{sys.executable}{GPG_STUB}")
    gpg.chmod(0o755)
    config = tmp_path / "gitconfig"
    config.write_text(
        "[user]\n\tname = Release Bot\n\temail = release@example.org\n\tsigningkey = 0123456789ABCDEF\n"
        f"[gpg]\n\tprogram = {gpg}\n[init]\n\tdefaultBranch = main\n"
    )
    return {
        "PATH": "/usr/bin:/bin",
        "HOME": str(tmp_path),
        "GIT_CONFIG_GLOBAL": str(config),
        "GIT_CONFIG_NOSYSTEM": "1",
    }


def _git(env: dict[str, str], cwd: Path, *args: str) -> str:
    """Run git with *args* in *cwd*; return its output."""
    done = subprocess.run([GIT, *args], cwd=cwd, env=env, capture_output=True, text=True, timeout=60, check=True)
    return done.stdout.strip()


@pytest.fixture
def project(tmp_path, env):
    """Return a project checkout at its release commit, and the directory of its patches.

    The patches directory holds ``taglist.log``, naming the release commit,
    and ``project.bundle``, a commit on top of it that changes the pom.
    """
    repo = tmp_path / "project"
    repo.mkdir()
    _git(env, repo, "init", "-q")
    (repo / "pom.xml").write_text("<version>1.0.0-SNAPSHOT</version>\n")
    _git(env, repo, "add", "pom.xml")
    _git(env, repo, "commit", "-q", "-m", "Initial")
    release = _git(env, repo, "rev-parse", "HEAD")

    upstream = tmp_path / "upstream"
    _git(env, tmp_path, "clone", "-q", str(repo), str(upstream))
    (upstream / "pom.xml").write_text("<version>1.0.0-Helium</version>\n")
    _git(env, upstream, "commit", "-q", "-am", "Release Helium")

    patches = tmp_path / "patches"
    patches.mkdir()
    _git(env, upstream, "bundle", "create", str(patches / "project.bundle"), f"{release}..HEAD", "HEAD")
    (patches / "taglist.log").write_text(f"project {release}\n")
    return repo, patches


def _patch(env: dict[str, str], repo: Path, patches: Path) -> subprocess.CompletedProcess[str]:
    """Run ``version patch Helium`` in *repo* with *patches*."""
    return subprocess.run(
        [BASH, str(SCRIPT), "patch", "Helium", str(patches), "Example"],
        cwd=repo,
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _tags(env: dict[str, str], repo: Path) -> list[str]:
    return _git(env, repo, "tag", "-l").split()


def test_patch_merges_bundle_and_tags_release(env: dict[str, str], project: tuple[Path, Path]) -> None:
    repo, patches = project

    result = _patch(env, repo, patches)

    assert result.returncode == 0, result.stderr
    assert _tags(env, repo) == ["release/helium"]
    assert (repo / "pom.xml").read_text() == "<version>1.0.0-Helium</version>\n"


def test_missing_bundle_exits_1(env: dict[str, str], project: tuple[Path, Path]) -> None:
    repo, patches = project
    (patches / "project.bundle").unlink()

    result = _patch(env, repo, patches)

    assert result.returncode == 1
    assert _tags(env, repo) == []
    assert "Tagging complete" not in result.stdout


def test_merge_conflict_exits_1(env: dict[str, str], project: tuple[Path, Path]) -> None:
    """A bundle that conflicts with the checkout is not merged, and nothing is tagged."""
    repo, patches = project
    taglist = patches / "taglist.log"
    (repo / "pom.xml").write_text("<version>1.0.0-Local</version>\n")
    _git(env, repo, "commit", "-q", "-am", "Local change")
    taglist.write_text(f"project {_git(env, repo, 'rev-parse', 'HEAD')}\n")

    result = _patch(env, repo, patches)

    assert result.returncode == 1
    assert _tags(env, repo) == []


def test_failed_tag_signing_exits_1(env: dict[str, str], project: tuple[Path, Path]) -> None:
    repo, patches = project
    env["GPG_FAIL"] = "1"

    result = _patch(env, repo, patches)

    assert result.returncode == 1
    assert _tags(env, repo) == []
    assert "ERROR" in result.stderr
