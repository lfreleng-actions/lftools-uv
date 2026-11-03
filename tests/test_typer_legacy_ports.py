# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests that the Typer front-end runs the commands global-jjb calls.

``nexus release``, ``sign sigul``, ``infofile check-votes`` and
``license check-dir`` existed only in the legacy Click front-end, so on the
default Typer front-end they failed as usage errors and global-jjb had to set
``LEGACY_CLI=1``. Each test runs the same arguments through both front-ends
and expects the same calls, output streams and exit codes.
"""

from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from pytest_mock import MockerFixture
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.cli_app import app as typer_app

Run = Callable[[list[str]], ClickResult | TyperResult]


def _click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, args, obj={})


def _typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(typer_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_click, _typer], ids=["click", "typer"])


def _typer_lacks(command: str) -> pytest.MarkDecorator:
    """Run both front-ends, expecting Typer to fail until it gains *command*."""
    missing = pytest.mark.xfail(strict=True, reason=f"Typer has no {command}")
    return pytest.mark.parametrize(
        "run", [pytest.param(_click, id="click"), pytest.param(_typer, id="typer", marks=missing)]
    )


# ---------------------------------------------------------------------------
# nexus release

NEXUS = "https://nexus.example.org"


@pytest.fixture
def release(mocker: MockerFixture) -> MagicMock:
    """Replace the staging release so no test reaches a Nexus server."""
    mock: MagicMock = mocker.patch("lftools_uv.nexus.cmd.release_staging_repos")
    return mock


@FRONT_ENDS
@pytest.mark.parametrize("verify", [False, True], ids=["release", "verify-only"])
def test_nexus_release_passes_repos_and_server(run: Run, release: MagicMock, verify: bool) -> None:
    flag = ["-v"] if verify else []
    result = run(["nexus", "release", *flag, "--server", NEXUS, "repo-1", "repo-2"])

    assert result.exit_code == 0, result.output
    release.assert_called_once_with(("repo-1", "repo-2"), verify, NEXUS, max_wait=60)


@FRONT_ENDS
def test_nexus_release_reads_server_from_environment(
    run: Run, release: MagicMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("NEXUS_URL", NEXUS)
    result = run(["nexus", "release", "--max-wait", "5", "repo-1"])

    assert result.exit_code == 0, result.output
    release.assert_called_once_with(("repo-1",), False, NEXUS, max_wait=5)


@FRONT_ENDS
@pytest.mark.parametrize(
    "args",
    [["-s", NEXUS], ["-s", NEXUS, "--max-wait", "0", "repo-1"]],
    ids=["no-repos", "zero-wait"],
)
def test_nexus_release_rejects_bad_usage(run: Run, release: MagicMock, args: list[str]) -> None:
    result = run(["nexus", "release", *args])

    assert result.exit_code == 2
    release.assert_not_called()


@FRONT_ENDS
def test_nexus_release_keeps_release_exit_code(run: Run, release: MagicMock) -> None:
    release.side_effect = SystemExit(1)
    result = run(["nexus", "release", "-s", NEXUS, "repo-1"])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# sign sigul


@FRONT_ENDS
@pytest.mark.parametrize("status", [0, 1, 3])
@pytest.mark.parametrize(("mode_args", "mode"), [([], "parallel"), (["-m", "serial"], "serial")])
def test_sign_sigul_runs_script_and_keeps_its_status(
    run: Run, mocker: MockerFixture, tmp_path: Path, status: int, mode_args: list[str], mode: str
) -> None:
    call = mocker.patch("subprocess.call", return_value=status)
    result = run(["sign", "sigul", *mode_args, str(tmp_path)])

    assert result.exit_code == status, result.output
    call.assert_called_once_with(["sign", "sigul", str(tmp_path), mode])
    assert result.stdout == ""


@FRONT_ENDS
def test_sign_sigul_fails_without_sign_script(run: Run, mocker: MockerFixture, tmp_path: Path) -> None:
    mocker.patch("subprocess.call", side_effect=FileNotFoundError("sign"))
    result = run(["sign", "sigul", str(tmp_path)])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# infofile check-votes

GERRIT = "https://gerrit.example.org/r/"
CHANGE = "1234"
INFO = """---
project: 'demo'
committers:
    - name: 'Alice Example'
      id: 'alice'
      github_id: 'alice-gh'
    - name: 'Bob Example'
      id: 'bob'
      github_id: 'bob-gh'
    - name: 'Carol Example'
      id: 'carol'
      github_id: 'carol-gh'
"""

VOTES = pytest.mark.parametrize(
    ("voters", "exit_code", "outcome"),
    [
        ([], 1, "No one has voted."),
        (["alice"], 1, "Majority not yet reached"),
        (["alice", "bob"], 0, "Majority committer vote reached"),
    ],
    ids=["none", "minority", "majority"],
)


@pytest.fixture
def info_file(tmp_path: Path) -> Path:
    """Write an INFO.yaml naming three committers."""
    path = tmp_path / "INFO.yaml"
    path.write_text(INFO)
    return path


def _gerrit_votes(mocker: MockerFixture, voters: list[str]) -> MagicMock:
    """Have Gerrit answer *voters* as Code-Review +1 on ``CHANGE``."""
    gerrit: MagicMock = mocker.patch("lftools_uv.cli.infofile.GerritRestAPI")
    gerrit.return_value.get.return_value = [
        {"username": user, "approvals": {"Code-Review": "+1" if user in voters else " 0"}}
        for user in ("alice", "bob", "carol")
    ]
    return gerrit


@_typer_lacks("infofile check-votes")
@VOTES
def test_check_votes_gerrit(
    run: Run,
    info_file: Path,
    mocker: MockerFixture,
    voters: list[str],
    exit_code: int,
    outcome: str,
) -> None:
    gerrit = _gerrit_votes(mocker, voters)
    result = run(["infofile", "check-votes", str(info_file), GERRIT, CHANGE])

    assert result.exit_code == exit_code, result.output
    gerrit.assert_called_once_with(url=GERRIT)
    gerrit.return_value.get.assert_called_once_with(f"changes/{CHANGE}/reviewers")
    lines = result.stdout.splitlines()
    assert "Number of Committers: 3" in lines
    assert f"Committers that have voted: {voters} ({len(voters)})" in lines
    assert outcome in lines


@_typer_lacks("infofile check-votes")
@VOTES
def test_check_votes_github(
    run: Run, info_file: Path, mocker: MockerFixture, voters: list[str], exit_code: int, outcome: str
) -> None:
    github_voters = [f"{voter}-gh" for voter in voters]
    prvotes = mocker.patch("lftools_uv.cli.infofile.prvotes", return_value=github_voters)
    result = run(["infofile", "check-votes", str(info_file), "example-org", CHANGE, "--github_repo", "demo"])

    assert result.exit_code == exit_code, result.output
    prvotes.assert_called_once_with("example-org", "demo", int(CHANGE))
    assert f"Committers that have voted: {github_voters} ({len(voters)})" in result.stdout.splitlines()
    assert outcome in result.stdout.splitlines()


@_typer_lacks("infofile check-votes")
def test_check_votes_tsc_majority(run: Run, info_file: Path, mocker: MockerFixture) -> None:
    _gerrit_votes(mocker, ["alice", "bob"])
    result = run(["infofile", "check-votes", str(info_file), GERRIT, CHANGE, "--tsc", str(info_file)])

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert "Need majority of TSC" in lines
    assert lines[-1] == "TSC majority reached - auto merging commit"


@_typer_lacks("infofile check-votes")
def test_check_votes_missing_info_file(run: Run, tmp_path: Path) -> None:
    """The shared error handler maps FileNotFoundError to exit code 7."""
    result = run(["infofile", "check-votes", str(tmp_path / "missing.yaml"), GERRIT, CHANGE])

    assert result.exit_code == 7
    assert result.stdout == ""


@FRONT_ENDS
def test_check_votes_rejects_non_numeric_change(run: Run, info_file: Path) -> None:
    result = run(["infofile", "check-votes", str(info_file), GERRIT, "abc"])

    assert result.exit_code == 2


# ---------------------------------------------------------------------------
# license check-dir

HEADER = "# Example licence header used by these tests.\n# Every checked file must carry it.\n"


@pytest.fixture
def reference(tmp_path: Path) -> Path:
    """Write the reference licence header."""
    path = tmp_path / "license-header.txt"
    path.write_text(HEADER)
    return path


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create a directory holding one Python file with the header."""
    path = tmp_path / "src"
    path.mkdir()
    (path / "good.py").write_text(HEADER + "print('ok')\n")
    return path


@_typer_lacks("license check-dir")
def test_check_dir_passes_with_headers(run: Run, reference: Path, source_dir: Path) -> None:
    result = run(["license", "check-dir", str(source_dir), "-l", str(reference)])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""


@_typer_lacks("license check-dir")
def test_check_dir_fails_on_missing_header(
    run: Run, reference: Path, source_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (source_dir / "bad.py").write_text("print('no header')\n")
    result = run(["license", "check-dir", str(source_dir), "-l", str(reference)])

    assert result.exit_code == 1
    assert "bad.py is missing or has incorrect license header" in caplog.text
    assert result.stdout == ""


@_typer_lacks("license check-dir")
def test_check_dir_applies_regex(run: Run, reference: Path, source_dir: Path) -> None:
    (source_dir / "bad.sh").write_text("echo 'no header'\n")
    python_only = run(["license", "check-dir", str(source_dir), "-l", str(reference)])
    shell = run(["license", "check-dir", "-r", r".+\.sh$", str(source_dir), "-l", str(reference)])

    assert python_only.exit_code == 0, python_only.output
    assert shell.exit_code == 1


@_typer_lacks("license check-dir")
def test_check_dir_fails_on_missing_directory(run: Run, reference: Path, tmp_path: Path) -> None:
    result = run(["license", "check-dir", str(tmp_path / "missing"), "-l", str(reference)])

    assert result.exit_code == 1
