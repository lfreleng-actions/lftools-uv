# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests that the Typer front-end runs the commands global-jjb calls.

``nexus release``, ``sign sigul``, ``infofile check-votes``,
``infofile get-committers``, ``infofile sync-committers`` and
``license check-dir`` existed only in the legacy Click front-end, so on the
default Typer front-end they failed as usage errors and global-jjb had to set
``LEGACY_CLI=1``. ``nexus create`` and ``nexus reorder-staged-repos``,
which the INFO.yaml automation runs, had the same gap, as did
``nexus docker``, which the ONAP and OpenDaylight ``run_releasedockerhub.sh``
scripts run, and ``infofile create-info-file`` was a placeholder that
exited 1. Each test runs the same arguments through both front-ends and
expects the same calls, output streams and exit codes.
"""

import subprocess
from pathlib import Path
from typing import Protocol
from unittest.mock import MagicMock

import pytest
import yaml
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from pytest_mock import MockerFixture
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.cli_app import app as typer_app


class Run(Protocol):
    """Run a command line through one front-end, with optional stdin."""

    def __call__(self, args: list[str], answer: str | None = None) -> ClickResult | TyperResult:
        """Invoke *args*, feeding *answer* to any prompt."""
        ...


def _click(args: list[str], answer: str | None = None) -> ClickResult:
    return ClickRunner().invoke(cli, args, obj={}, input=answer)


def _typer(args: list[str], answer: str | None = None) -> TyperResult:
    return TyperRunner().invoke(typer_app, args, input=answer)


FRONT_ENDS = pytest.mark.parametrize("run", [_click, _typer], ids=["click", "typer"])


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
# nexus create repo, nexus create role, nexus reorder-staged-repos

NEXUS_CMD = pytest.mark.parametrize(
    ("args", "target", "expected"),
    [
        (
            ["create", "repo", "-u", NEXUS, "-c", "repo-config.yaml"],
            "create_repos",
            ("repo-config.yaml", None, NEXUS),
        ),
        (
            ["create", "repo", "--configfile", "repo-config.yaml", "--settings", "settings.yaml"],
            "create_repos",
            ("repo-config.yaml", "settings.yaml", None),
        ),
        (
            ["create", "role", "-c", "role-config.yaml", "-s", "settings.yaml"],
            "create_roles",
            ("role-config.yaml", "settings.yaml"),
        ),
        (["reorder-staged-repos", "-s", "settings.yaml"], "reorder_staged_repos", ("settings.yaml",)),
    ],
    ids=["create-repo", "create-repo-settings", "create-role", "reorder-staged-repos"],
)


@FRONT_ENDS
@NEXUS_CMD
def test_nexus_command_passes_options(
    run: Run, mocker: MockerFixture, args: list[str], target: str, expected: tuple[str | None, ...]
) -> None:
    call = mocker.patch(f"lftools_uv.nexus.cmd.{target}")
    result = run(["nexus", *args])

    assert result.exit_code == 0, result.output
    call.assert_called_once_with(*expected)


@FRONT_ENDS
@pytest.mark.parametrize(
    ("args", "target"),
    [
        (["create", "repo", "-u", NEXUS], "create_repos"),
        (["create", "role", "-s", "settings.yaml"], "create_roles"),
        (["create", "role", "-c", "role-config.yaml"], "create_roles"),
        (["reorder-staged-repos"], "reorder_staged_repos"),
    ],
    ids=["repo-no-configfile", "role-no-config", "role-no-settings", "reorder-no-settings"],
)
def test_nexus_command_requires_options(run: Run, mocker: MockerFixture, args: list[str], target: str) -> None:
    call = mocker.patch(f"lftools_uv.nexus.cmd.{target}")
    result = run(["nexus", *args])

    assert result.exit_code == 2
    call.assert_not_called()


# ---------------------------------------------------------------------------
# nexus docker list, nexus docker delete, nexus docker releasedockerhub

IMAGES = [{"name": "app", "version": "1.0"}, {"name": "app", "version": "1.1"}]


@pytest.fixture
def search(mocker: MockerFixture) -> MagicMock:
    """Replace the image search so no test reaches a Nexus server."""
    mock: MagicMock = mocker.patch("lftools_uv.nexus.cmd.search", return_value=IMAGES)
    return mock


@pytest.fixture
def start_point(mocker: MockerFixture) -> MagicMock:
    """Replace the Docker Hub release so no test reaches a registry."""
    mock: MagicMock = mocker.patch("lftools_uv.nexus.release_docker_hub.start_point")
    return mock


@FRONT_ENDS
def test_nexus_help_lists_commands(run: Run) -> None:
    result = run(["nexus", "--help"])

    assert result.exit_code == 0, result.output
    for command in ("create", "docker", "release", "reorder-staged-repos"):
        assert command in result.output


@FRONT_ENDS
def test_docker_list_passes_arguments(run: Run, mocker: MockerFixture, search: MagicMock, tmp_path: Path) -> None:
    output = mocker.patch("lftools_uv.nexus.cmd.output_images")
    csv = str(tmp_path / "images.csv")
    result = run(["nexus", "docker", "list", "--settings", "s.yaml", "-s", NEXUS, "--csv", csv, "app*", "releases"])

    assert result.exit_code == 0, result.output
    search.assert_called_once_with("s.yaml", NEXUS, "releases", "app*")
    output.assert_called_once_with(IMAGES, csv)


@FRONT_ENDS
@pytest.mark.parametrize(("server", "expected"), [([], NEXUS), (["--server", "https://other"], "https://other")])
def test_docker_list_reads_server_from_environment(
    run: Run,
    mocker: MockerFixture,
    search: MagicMock,
    monkeypatch: pytest.MonkeyPatch,
    server: list[str],
    expected: str,
) -> None:
    mocker.patch("lftools_uv.nexus.cmd.output_images")
    monkeypatch.setenv("NEXUS_URL", NEXUS)
    result = run(["nexus", "docker", "list", *server, "*", "releases"])

    assert result.exit_code == 0, result.output
    search.assert_called_once_with(None, expected, "releases", "*")


@FRONT_ENDS
def test_docker_list_outputs_nothing_without_images(run: Run, mocker: MockerFixture, search: MagicMock) -> None:
    output = mocker.patch("lftools_uv.nexus.cmd.output_images")
    search.return_value = []
    result = run(["nexus", "docker", "list", "-s", NEXUS, "*", "releases"])

    assert result.exit_code == 0, result.output
    output.assert_not_called()


@FRONT_ENDS
@pytest.mark.parametrize(("answer", "deletes"), [("y\n", True), ("n\n", False)], ids=["confirmed", "declined"])
def test_docker_delete_asks_before_deleting(
    run: Run, mocker: MockerFixture, search: MagicMock, monkeypatch: pytest.MonkeyPatch, answer: str, deletes: bool
) -> None:
    delete = mocker.patch("lftools_uv.nexus.cmd.delete_images")
    monkeypatch.setenv("NEXUS_URL", NEXUS)
    result = run(["nexus", "docker", "delete", "--settings", "s.yaml", "app*", "releases"], answer)

    assert result.exit_code == 0, result.output
    assert "Would you like to delete all 2 images?" in result.output
    search.assert_called_once_with("s.yaml", None, "releases", "app*")
    if deletes:
        delete.assert_called_once_with("s.yaml", None, IMAGES)
    else:
        delete.assert_not_called()


@FRONT_ENDS
def test_docker_delete_yes_skips_confirmation(run: Run, mocker: MockerFixture, search: MagicMock) -> None:
    delete = mocker.patch("lftools_uv.nexus.cmd.delete_images")
    result = run(["nexus", "docker", "delete", "-y", "-s", NEXUS, "*", "releases"])

    assert result.exit_code == 0, result.output
    assert "Would you like" not in result.output
    delete.assert_called_once_with(None, NEXUS, IMAGES)


@FRONT_ENDS
@pytest.mark.parametrize(
    ("args", "expected"),
    [
        (["-o", "onap", "--summary"], ("onap", "", False, True, False, False, False, False, "")),
        (
            ["-o", "onap", "-r", "msb", "-e", "-s", "-v", "-c", "-p", "-f", "-x", "regexp.txt"],
            ("onap", "msb", True, True, True, True, True, True, "regexp.txt"),
        ),
        (
            ["--org", "odl", "--repo", "netconf", "--exact", "--verbose", "--copy", "--progbar", "--repofile"],
            ("odl", "netconf", True, False, True, True, True, True, ""),
        ),
    ],
    ids=["summary", "short-options", "long-options"],
)
def test_releasedockerhub_passes_options(
    run: Run, start_point: MagicMock, args: list[str], expected: tuple[str | bool, ...]
) -> None:
    result = run(["nexus", "docker", "releasedockerhub", *args])

    assert result.exit_code == 0, result.output
    start_point.assert_called_once_with(*expected)


@FRONT_ENDS
@pytest.mark.parametrize("option", ["--version_regexp", "--version-regexp"])
def test_releasedockerhub_accepts_both_version_spellings(run: Run, start_point: MagicMock, option: str) -> None:
    result = run(["nexus", "docker", "releasedockerhub", "-o", "onap", option, "regexp.txt"])

    assert result.exit_code == 0, result.output
    start_point.assert_called_once_with("onap", "", False, False, False, False, False, False, "regexp.txt")


@FRONT_ENDS
def test_releasedockerhub_requires_org(run: Run, start_point: MagicMock) -> None:
    result = run(["nexus", "docker", "releasedockerhub", "--summary"])

    assert result.exit_code == 2
    start_point.assert_not_called()


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


@FRONT_ENDS
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


@FRONT_ENDS
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


@FRONT_ENDS
def test_check_votes_tsc_majority(run: Run, info_file: Path, mocker: MockerFixture) -> None:
    _gerrit_votes(mocker, ["alice", "bob"])
    result = run(["infofile", "check-votes", str(info_file), GERRIT, CHANGE, "--tsc", str(info_file)])

    assert result.exit_code == 0, result.output
    lines = result.stdout.splitlines()
    assert "Need majority of TSC" in lines
    assert lines[-1] == "TSC majority reached - auto merging commit"


@FRONT_ENDS
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


@FRONT_ENDS
def test_check_dir_passes_with_headers(run: Run, reference: Path, source_dir: Path) -> None:
    result = run(["license", "check-dir", str(source_dir), "-l", str(reference)])

    assert result.exit_code == 0, result.output
    assert result.stdout == ""


@FRONT_ENDS
def test_check_dir_fails_on_missing_header(
    run: Run, reference: Path, source_dir: Path, caplog: pytest.LogCaptureFixture
) -> None:
    (source_dir / "bad.py").write_text("print('no header')\n")
    result = run(["license", "check-dir", str(source_dir), "-l", str(reference)])

    assert result.exit_code == 1
    assert "bad.py is missing or has incorrect license header" in caplog.text
    assert result.stdout == ""


@FRONT_ENDS
def test_check_dir_applies_regex(run: Run, reference: Path, source_dir: Path) -> None:
    (source_dir / "bad.sh").write_text("echo 'no header'\n")
    python_only = run(["license", "check-dir", str(source_dir), "-l", str(reference)])
    shell = run(["license", "check-dir", "-r", r".+\.sh$", str(source_dir), "-l", str(reference)])

    assert python_only.exit_code == 0, python_only.output
    assert shell.exit_code == 1


@FRONT_ENDS
def test_check_dir_fails_on_missing_directory(run: Run, reference: Path, tmp_path: Path) -> None:
    result = run(["license", "check-dir", str(tmp_path / "missing"), "-l", str(reference)])

    assert result.exit_code == 1


# ---------------------------------------------------------------------------
# infofile get-committers and sync-committers

COMMITTERS_INFO = """---
project: 'demo'
repositories:
    - 'demo'
    - 'demo-docs'
committers:
    - name: 'Alice Example'
      email: 'alice@example.org'
      company: 'Example'
      id: 'alice'
      timezone: 'UTC'
    - name: 'Bob Example'
      email: 'bob@example.org'
      company: 'Example'
      id: 'bob'
      timezone: 'UTC'
"""

COMMITTERS_LDAP = """---
committers:
    - name: 'Alice Example'
      email: 'alice@example.org'
      company: 'Example'
      id: 'alice'
      timezone: 'UTC'
    - name: 'Carol Example'
      email: 'carol@example.org'
      company: 'Example'
      id: 'carol'
      timezone: 'Europe/London'
"""


@pytest.fixture
def committers_info(tmp_path: Path) -> Path:
    """Write an INFO.yaml naming alice and bob as committers."""
    path = tmp_path / "INFO.yaml"
    path.write_text(COMMITTERS_INFO)
    return path


@pytest.fixture
def committers_ldap(tmp_path: Path) -> Path:
    """Write an LDAP dump naming alice and carol as committers."""
    path = tmp_path / "LDAP.yaml"
    path.write_text(COMMITTERS_LDAP)
    return path


@FRONT_ENDS
@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ([], "      id: alice\n      id: bob\n"),
        (
            ["--full"],
            "    - name: Alice Example\n      email: alice@example.org\n      id: alice\n"
            "    - name: Bob Example\n      email: bob@example.org\n      id: bob\n",
        ),
        (["--id", "bob"], "      id: bob\n"),
        (["--id", "bob", "--full"], "    - name: Bob Example\n      email: bob@example.org\n      id: bob\n"),
        (["--id", "dave"], ""),
    ],
    ids=["plain", "full", "id-present", "id-full", "id-absent"],
)
def test_get_committers_prints_committers(run: Run, committers_info: Path, options: list[str], expected: str) -> None:
    result = run(["infofile", "get-committers", *options, str(committers_info)])

    assert result.exit_code == 0, result.output
    assert result.stdout == expected


@FRONT_ENDS
def test_get_committers_reads_file_from_environment(
    run: Run, committers_info: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("FILE_NAME", str(committers_info))
    result = run(["infofile", "get-committers"])

    assert result.exit_code == 0, result.output
    assert result.stdout == "      id: alice\n      id: bob\n"


@FRONT_ENDS
def test_get_committers_missing_file(run: Run, tmp_path: Path) -> None:
    """The shared error handler maps FileNotFoundError to exit code 7."""
    result = run(["infofile", "get-committers", str(tmp_path / "missing.yaml")])

    assert result.exit_code == 7
    assert result.stdout == ""


REPO_OPTIONS = pytest.mark.parametrize("repo", [None, "demo-new"], ids=["no-repo", "repo"])


def _sync(run: Run, info: Path, ldap: Path, committer: str, repo: str | None) -> ClickResult | TyperResult:
    repo_args = ["--repo", repo] if repo else []
    return run(["infofile", "sync-committers", str(info), str(ldap), committer, *repo_args])


@FRONT_ENDS
def test_sync_committers_without_repo_keeps_repositories(
    run: Run, committers_info: Path, committers_ldap: Path
) -> None:
    result = _sync(run, committers_info, committers_ldap, "carol", None)

    assert result.exit_code == 0, result.output
    info = yaml.safe_load(committers_info.read_text())
    assert info["repositories"] == ["demo", "demo-docs"]
    assert info["committers"][-1]["id"] == "carol"


@FRONT_ENDS
def test_sync_committers_with_repo_replaces_first_repository(
    run: Run, committers_info: Path, committers_ldap: Path
) -> None:
    result = _sync(run, committers_info, committers_ldap, "carol", "demo-new")

    assert result.exit_code == 0, result.output
    assert result.stdout == ""
    info = yaml.safe_load(committers_info.read_text())
    assert info["repositories"] == ["demo-new", "demo-docs"]
    assert info["committers"][-1] == {
        "name": "Carol Example",
        "company": "Example",
        "email": "carol@example.org",
        "id": "carol",
        "timezone": "Europe/London",
    }
    assert [c["id"] for c in info["committers"]] == ["alice", "bob", "carol"]


def test_sync_committers_writes_same_file_in_both_front_ends(tmp_path: Path, committers_ldap: Path) -> None:
    written = []
    for name, run in (("click", _click), ("typer", _typer)):
        info = tmp_path / f"{name}.yaml"
        info.write_text(COMMITTERS_INFO)
        result = _sync(run, info, committers_ldap, "carol", "demo-new")
        assert result.exit_code == 0, result.output
        written.append(info.read_text())

    assert written[0] == written[1]


@FRONT_ENDS
@REPO_OPTIONS
@pytest.mark.parametrize(("committer", "exit_code"), [("alice", 0), ("dave", 1)], ids=["present", "not-in-ldap"])
def test_sync_committers_leaves_file_alone(
    run: Run, committers_info: Path, committers_ldap: Path, repo: str | None, committer: str, exit_code: int
) -> None:
    """An existing committer exits 0, and one LDAP lacks exits 1, without writing."""
    result = _sync(run, committers_info, committers_ldap, committer, repo)

    assert result.exit_code == exit_code, result.output
    assert result.stdout == ""
    assert committers_info.read_text() == COMMITTERS_INFO


# ---------------------------------------------------------------------------
# infofile create-info-file

STUB_COMMITTERS = (
    "    - name: 'Alice Example'\n      email: 'alice@example.org'\n      company: 'Example'\n      id: 'alice'\n"
)
EMPTY_COMMITTER = "    - name: ''\n      email: ''\n      company: ''\n      id: ''\n"


@pytest.fixture
def gerrit(mocker: MockerFixture) -> MagicMock:
    """Answer Gerrit's access request with a project that has an owner."""
    mocker.patch("lftools_uv.cli.infofile.config.get_setting", return_value="secret")
    rest: MagicMock = mocker.patch("lftools_uv.cli.infofile.GerritRestAPI")
    rest.return_value.get.return_value = {
        "local": {"refs/*": {"permissions": {"owner": {"rules": {"ldap:cn=owners,ou=Groups": {}}}}}}
    }
    return rest


@pytest.fixture
def yaml4info(mocker: MockerFixture) -> MagicMock:
    """Return two committers from the LDAP helper without running it."""
    mock: MagicMock = mocker.patch("lftools_uv.cli.infofile.helper_yaml4info", return_value=STUB_COMMITTERS)
    return mock


@FRONT_ENDS
def test_create_info_file_empty_makes_no_request(run: Run, gerrit: MagicMock, yaml4info: MagicMock) -> None:
    result = run(["infofile", "create-info-file", "gerrit.example.org", "foo/bar", "--empty"])

    assert result.exit_code == 0, result.output
    assert result.stdout.startswith("---\nproject: 'foo_bar'\n")
    assert "repositories:\n    - foo/bar\ncommitters:\n    - <<: *example_foo_bar_ptl\n" in result.stdout
    assert f"*example_foo_bar_ptl\n{EMPTY_COMMITTER}tsc:\n" in result.stdout
    assert "    approval: 'missing'\n" in result.stdout
    gerrit.assert_not_called()
    yaml4info.assert_not_called()


def test_create_info_file_empty_matches_between_front_ends() -> None:
    args = ["infofile", "create-info-file", "gerrit.example.org", "foo/bar", "--empty"]
    click_result = _click(args)
    typer_result = _typer(args)

    assert typer_result.exit_code == click_result.exit_code == 0
    assert typer_result.stdout == click_result.stdout


@FRONT_ENDS
@pytest.mark.parametrize(
    ("host", "project", "group"),
    [
        ("gerrit.example.org", "foo/bar", "example-gerrit-foo-bar-committers"),
        ("gerrit.example.org", "foo/bar_baz", "example-gerrit-foo-bar-baz-committers"),
        ("gerrit.o-ran-sc.org", "foo", "oran-gerrit-foo-committers"),
        ("git.opendaylight.org", "foo", "odl-gerrit-foo-committers"),
    ],
    ids=["example", "underscore", "o-ran-sc", "opendaylight"],
)
def test_create_info_file_lists_derived_group(
    run: Run, gerrit: MagicMock, yaml4info: MagicMock, host: str, project: str, group: str
) -> None:
    result = run(["infofile", "create-info-file", host, project])

    assert result.exit_code == 0, result.output
    yaml4info.assert_called_once_with(group)
    assert f"_ptl\n{STUB_COMMITTERS}tsc:\n" in result.stdout
    gerrit.return_value.get.assert_called_once()


@FRONT_ENDS
def test_create_info_file_group_replaces_derived_name(run: Run, gerrit: MagicMock, yaml4info: MagicMock) -> None:
    result = run(["infofile", "create-info-file", "gerrit.example.org", "foo/bar", "--group", "foo-maintainers"])

    assert result.exit_code == 0, result.output
    yaml4info.assert_called_once_with("foo-maintainers")
    assert f"_ptl\n{STUB_COMMITTERS}tsc:\n" in result.stdout


@FRONT_ENDS
@pytest.mark.parametrize("option", ["--tsc_approval", "--tsc-approval"], ids=["underscore", "hyphen"])
def test_create_info_file_tsc_approval_spellings(run: Run, option: str) -> None:
    link = "https://example.org/tsc/approval"
    result = run(["infofile", "create-info-file", "gerrit.example.org", "foo", "--empty", option, link])

    assert result.exit_code == 0, result.output
    assert f"    approval: '{link}'\n" in result.stdout


@FRONT_ENDS
def test_create_info_file_failed_lookup_prints_nothing(run: Run, gerrit: MagicMock, yaml4info: MagicMock) -> None:
    yaml4info.side_effect = subprocess.CalledProcessError(1, ["yaml4info"])
    result = run(["infofile", "create-info-file", "gerrit.example.org", "foo/bar"])

    assert result.exit_code != 0
    assert result.stdout == ""
