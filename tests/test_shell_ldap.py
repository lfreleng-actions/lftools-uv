# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for how the LDAP helper scripts report failed lookups.

``yaml4info``, ``inactivecommitters`` and ``autocorrectinfofile`` build on
``lftools-uv ldap csv``, ``ldap yaml4info`` and ``infofile get-committers``.
A lookup that fails must fail the script, rather than produce an empty list
of committers, report every committer as inactive, or count as a match.
Click's ``infofile create-info-file`` must likewise print no INFO file when
its lookup fails, and never take an error message for committers.

Each script runs under real bash, with a PATH holding only stubs and system
tools. The ``lftools-uv`` stub answers from canned data and fails a command
when the test asks; ``curl`` and ``ssh`` stubs stand in for Gerrit.
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest import mock

import pytest
from click.testing import CliRunner, Result

from lftools_uv import ldap_cli
from lftools_uv.cli.infofile import infofile

XFAIL = pytest.mark.xfail(strict=True, reason="#858: the LDAP helpers exit 0 when a lookup fails")

SHELL_DIR = Path(__file__).resolve().parent.parent / "shell"
BASH = shutil.which("bash") or "/bin/bash"

# Answers ldap csv, ldap yaml4info and infofile get-committers from canned
# data, unless $FAIL names the command, which then prints an error and exits 1.
# With $EMPTY_GROUP set, ldap yaml4info finds no committers.
# get-committers prints the ids of the committers in the file, read with the
# real parser, so a file without a committers key fails as the real one does.
LFTOOLS_UV_STUB = r"""
import os
import sys

import yaml

args = sys.argv[1:]
command = " ".join(args[:2])
if command == os.environ.get("FAIL"):
    print(f"ERROR: {command} failed", file=sys.stderr)
    sys.exit(1)
if command == "ldap csv":
    print("grp,alice,Alice Example,alice@example.org")
    print("grp,bob,Bob Example,bob@example.org")
elif command == "ldap yaml4info" and not os.environ.get("EMPTY_GROUP"):
    print("    - name: 'Alice Example'\n      email: 'alice@example.org'\n      id: 'alice'")
    print("    - name: 'Bob Example'\n      email: 'bob@example.org'\n      id: 'bob'")
elif command == "infofile get-committers":
    if "--id" in args:
        sys.exit(0)
    with open(args[-1]) as f:
        data = yaml.safe_load(f)
    for committer in data.get("committers") or []:
        print(f"      id: {committer['id']}")
"""

# Answers a Gerrit query as Gerrit does: for alice with a change updated
# today, and for bob, an account Gerrit does not know, with HTTP 400. With
# $GERRIT_STATUS set it answers that status instead, and with $CURL_EXIT set
# it fails to connect. It writes the -w format after the body, as curl does.
CURL_STUB = r"""
import os
import sys

args = sys.argv[1:]
if os.environ.get("CURL_EXIT"):
    print("curl: (6) Could not resolve host", file=sys.stderr)
    sys.exit(int(os.environ["CURL_EXIT"]))
if os.environ.get("GERRIT_STATUS"):
    code, body = int(os.environ["GERRIT_STATUS"]), "Service Unavailable\n"
elif "alice" in args[-1]:
    code, body = 200, ')]}\'\n[{"id":"1","created":"2026-10-30 09:00:00.000000000","updated":"2026-11-01 10:00:00.000000000"}]\n'
else:
    code, body = 400, "Account 'bob' not found\n"
written = args[args.index("-w") + 1] if "-w" in args[:-1] else ""
sys.stdout.write(body + written.replace("\\n", "\n").replace("%{http_code}", str(code)))
"""

SSH_STUB = "#!/bin/sh\nexit 0\n"

TOOLS = (
    "awk",
    "cat",
    "date",
    "diff",
    "dirname",
    "grep",
    "mkdir",
    "sed",
    "sort",
)


@pytest.fixture
def sandbox(tmp_path):
    """Return an environment whose PATH resolves lftools-uv, curl and ssh to stubs."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    for tool in TOOLS:
        found = shutil.which(tool, path="/usr/bin:/bin")
        if found:
            (bin_dir / tool).symlink_to(found)
    for name, source in (("lftools-uv", LFTOOLS_UV_STUB), ("curl", CURL_STUB)):
        stub = bin_dir / name
        stub.write_text(f"#!{sys.executable}{source}")
        stub.chmod(0o755)
    ssh = bin_dir / "ssh"
    ssh.write_text(SSH_STUB)
    ssh.chmod(0o755)
    return {"PATH": str(bin_dir), "HOME": str(tmp_path)}


def _run(script: str, env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [BASH, str(SHELL_DIR / script), *args],
        capture_output=True,
        text=True,
        env=env,
        cwd=env["HOME"],
        timeout=60,
        check=False,
    )


def test_yaml4info_prints_each_committer(sandbox: dict[str, str]) -> None:
    result = _run("yaml4info", sandbox, "grp")

    assert result.returncode == 0, result.stderr
    assert "    - name: 'Alice Example'" in result.stdout
    assert "      id: 'bob'" in result.stdout


@XFAIL
def test_yaml4info_failed_lookup_exits_1(sandbox: dict[str, str]) -> None:
    sandbox["FAIL"] = "ldap csv"

    result = _run("yaml4info", sandbox, "grp")

    assert result.returncode == 1
    assert result.stdout == ""
    assert "ERROR" in result.stderr


def test_inactivecommitters_reports_each_committer(sandbox: dict[str, str]) -> None:
    """Gerrit answers bob, an account it does not know, with 400: no activity, not a failure."""
    result = _run("inactivecommitters", sandbox, "gerrit.example.org/gerrit", "grp")

    assert result.returncode == 0, result.stderr
    assert "  OK alice, Alice Example" in result.stdout
    assert "  ERROR bob, Bob Example, bob@example.org has no activity" in result.stdout


@XFAIL
def test_inactivecommitters_reads_date_from_compact_json(sandbox: dict[str, str]) -> None:
    """Gerrit sends each change's JSON on one line; the date is still found."""
    result = _run("inactivecommitters", sandbox, "gerrit.example.org/gerrit", "grp")

    assert result.returncode == 0, result.stderr
    assert "alice@example.org last submission or review 2026-11-01\n" in result.stdout


@XFAIL
def test_inactivecommitters_failed_lookup_exits_1(sandbox: dict[str, str]) -> None:
    sandbox["FAIL"] = "ldap csv"

    result = _run("inactivecommitters", sandbox, "gerrit.example.org/gerrit", "grp")

    assert result.returncode == 1
    assert "ERROR" in result.stderr


@XFAIL
def test_inactivecommitters_unreachable_gerrit_exits_1(sandbox: dict[str, str]) -> None:
    """An unreachable Gerrit must not make every committer look inactive."""
    sandbox["CURL_EXIT"] = "6"

    result = _run("inactivecommitters", sandbox, "gerrit.example.org/gerrit", "grp")

    assert result.returncode == 1
    assert "has no activity" not in result.stdout


@XFAIL
def test_inactivecommitters_gerrit_error_exits_1(sandbox: dict[str, str]) -> None:
    """A Gerrit that answers with an error must not make every committer look inactive."""
    sandbox["GERRIT_STATUS"] = "503"

    result = _run("inactivecommitters", sandbox, "gerrit.example.org/gerrit", "grp")

    assert result.returncode == 1
    assert "has no activity" not in result.stdout
    assert "503" in result.stderr


@pytest.fixture
def info_dir(tmp_path, sandbox):
    """Return the environment and work directory of an INFO.yaml that lists alice and carol."""
    work = tmp_path / "work"
    (work / "repo").mkdir(parents=True)
    (work / "repo" / "INFO.yaml").write_text(
        "committers:\n    - name: 'Alice Example'\n      id: 'alice'\n    - name: 'Carol Example'\n      id: 'carol'\n"
    )
    return {**sandbox, "DIR": str(work)}, work


@XFAIL
def test_autocorrectinfofile_compares_ldap_with_info(info_dir: tuple[dict[str, str], Path]) -> None:
    """The LDAP dump is one get-committers can read, so only real differences are reported."""
    env, work = info_dir

    result = _run("autocorrectinfofile", env, "https://gerrit.example.org/r", "grp", "repo")

    assert result.returncode == 1, result.stderr
    assert "sending invite to carol" in result.stdout
    assert " bob --repo repo" in result.stdout
    assert "sending invite to alice" not in result.stdout
    assert (work / "LDAP.yaml").read_text().startswith("committers:\n")


def test_autocorrectinfofile_empty_ldap_group_syncs_nobody(info_dir: tuple[dict[str, str], Path]) -> None:
    """An LDAP group without committers is compared as empty, not as one blank entry."""
    env, _ = info_dir
    env["EMPTY_GROUP"] = "1"

    result = _run("autocorrectinfofile", env, "https://gerrit.example.org/r", "grp", "repo")

    assert result.returncode == 1, result.stderr
    assert "sending invite to alice" in result.stdout
    assert "sending invite to carol" in result.stdout
    assert "sync-committers" not in result.stdout


@XFAIL
@pytest.mark.parametrize("failing", ["ldap yaml4info", "infofile get-committers"])
def test_autocorrectinfofile_failed_lookup_exits_1(info_dir: tuple[dict[str, str], Path], failing: str) -> None:
    env, _ = info_dir
    env["FAIL"] = failing

    result = _run("autocorrectinfofile", env, "https://gerrit.example.org/r", "grp", "repo")

    assert result.returncode == 1
    assert "ERROR" in result.stderr


@XFAIL
@pytest.mark.skipif(os.geteuid() == 0, reason="root can overwrite a read-only file")
def test_autocorrectinfofile_unwritable_ldap_dump_exits_1(info_dir: tuple[dict[str, str], Path]) -> None:
    """An earlier run's LDAP.yaml that cannot be overwritten is never compared."""
    env, work = info_dir
    stale = work / "LDAP.yaml"
    stale.write_text("committers:\n    - name: 'Carol Example'\n      id: 'carol'\n")
    stale.chmod(0o444)

    result = _run("autocorrectinfofile", env, "https://gerrit.example.org/r", "grp", "repo")

    assert result.returncode == 1
    assert "Could not write" in result.stderr


def _create_info_file(runner_env: dict[str, str]) -> Result:
    """Run Click's create-info-file for project foo with Gerrit access mocked out."""
    access: dict[str, Any] = {"local": {"refs/*": {"permissions": {"owner": {"rules": {}}}}}}
    with (
        mock.patch("lftools_uv.cli.infofile.config.get_setting", return_value="secret"),
        mock.patch("lftools_uv.cli.infofile.GerritRestAPI") as rest,
    ):
        rest.return_value.get.return_value = access
        return CliRunner().invoke(infofile, ["create-info-file", "gerrit.example.org", "foo"], obj={}, env=runner_env)


def test_create_info_file_lists_ldap_committers(sandbox: dict[str, str]) -> None:
    result = _create_info_file({"PATH": sandbox["PATH"] + ":" + str(SHELL_DIR)})

    assert result.exit_code == 0, result.output
    assert "    - name: 'Alice Example'" in result.output
    assert "repositories:" in result.output


@XFAIL
def test_create_info_file_failed_lookup_prints_nothing(sandbox: dict[str, str]) -> None:
    """A failed lookup prints no INFO file, and its error never becomes committers."""
    result = _create_info_file({"PATH": sandbox["PATH"] + ":" + str(SHELL_DIR), "FAIL": "ldap csv"})

    assert result.exit_code == 1
    assert "repositories:" not in result.stdout
    assert "ERROR: ldap csv failed" not in result.stdout


@XFAIL
def test_helper_yaml4info_keeps_errors_out_of_its_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Only the script's standard output is YAML; a warning it prints is not."""
    script = tmp_path / "yaml4info"
    script.write_text("#!/bin/sh\necho \"    - name: 'Alice'\"\necho 'WARNING: slow LDAP server' >&2\n")
    script.chmod(0o755)
    monkeypatch.setenv("PATH", str(tmp_path))

    assert ldap_cli.helper_yaml4info("grp") == "    - name: 'Alice'\n"
