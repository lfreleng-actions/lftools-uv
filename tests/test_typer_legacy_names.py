# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests that the default front-end accepts legacy command and option names.

The port from Click to Typer renamed ``lfidapi match-ldap-to-info`` and
several underscored options. Callers written for legacy lftools pass the old
names, so each must reach the same function with the same arguments as the
current name.
"""

from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest
from typer.testing import CliRunner

from lftools_uv.cli_app import app

runner = CliRunner()

FQDN = "gerrit.example.org"
PROJECT = "foo/bar"
JJB = "ci-management"


@pytest.fixture
def gerrit_mocks() -> Iterator[tuple[MagicMock, MagicMock]]:
    """Replace the Gerrit clients so no test reaches a server or clones."""
    with (
        patch("lftools_uv.typer_apps.gerrit.gerrit.Gerrit") as api,
        patch("lftools_uv.typer_apps.gerrit.git_gerrit") as git,
    ):
        api.return_value.add_file.return_value = {}
        yield api, git


@pytest.fixture
def github_org() -> Iterator[MagicMock]:
    """Replace the GitHub client and return the organization mock."""
    with (
        patch("lftools_uv.typer_apps.github_cli.config.get_setting", return_value="token"),
        patch("lftools_uv.typer_apps.github_cli.Github") as github,
    ):
        yield github.return_value.get_organization.return_value


def _gerrit_calls(args: list[str], mocks: tuple[MagicMock, MagicMock]) -> list:
    api, git = mocks
    api.reset_mock()
    git.reset_mock()
    result = runner.invoke(app, ["gerrit", *args])
    assert result.exit_code == 0, result.output
    return [api.mock_calls, git.mock_calls]


def _github_calls(args: list[str], org: MagicMock) -> list:
    org.reset_mock()
    result = runner.invoke(app, ["github", *args])
    assert result.exit_code == 0, result.output
    return org.mock_calls


GERRIT_CASES = {
    "addfile-issue-id": (
        ["addfile", FQDN, PROJECT, "f.txt", "--issue-id=X"],
        ["addfile", FQDN, PROJECT, "f.txt", "--issue_id=X"],
    ),
    "addfile-file-location": (
        ["addfile", FQDN, PROJECT, "f.txt", "--file-location", "dir"],
        ["addfile", FQDN, PROJECT, "f.txt", "--file_location", "dir"],
    ),
    "addinfojob-issue-id": (
        ["addinfojob", FQDN, PROJECT, JJB, "--issue-id=X"],
        ["addinfojob", FQDN, PROJECT, JJB, "--issue_id=X"],
    ),
    "addgitreview-issue-id": (
        ["addgitreview", FQDN, PROJECT, "--issue-id", "X"],
        ["addgitreview", FQDN, PROJECT, "--issue_id", "X"],
    ),
    "addmavenconfig-issue-id": (
        ["addmavenconfig", FQDN, PROJECT, JJB, "--issue-id", "X"],
        ["addmavenconfig", FQDN, PROJECT, JJB, "--issue_id", "X"],
    ),
    "addmavenconfig-nexus3-ports": (
        ["addmavenconfig", FQDN, PROJECT, JJB, "--nexus3-ports", "10001,10002"],
        ["addmavenconfig", FQDN, PROJECT, JJB, "--nexus3_ports", "10001,10002"],
    ),
}

GITHUB_COMMANDS = {"create-repo": ["create-repo", "o", "r", "desc"], "update-repo": ["update-repo", "o", "r"]}

GITHUB_CASES = {
    f"{command}-{feature}": (
        [*prefix, f"--{feature.replace('_', '-')}"],
        [*prefix, f"--{feature}"],
    )
    for command, prefix in GITHUB_COMMANDS.items()
    for feature in ("has_issues", "has_projects", "has_wiki")
}
GITHUB_CASES.update(
    {
        f"update-repo-{option}": (
            [*GITHUB_COMMANDS["update-repo"], f"--{option.replace('_', '-')}", "devs"],
            [*GITHUB_COMMANDS["update-repo"], f"--{option}", "devs"],
        )
        for option in ("add_team", "remove_team")
    }
)


@pytest.mark.xfail(strict=True, reason="legacy option names not yet accepted")
@pytest.mark.parametrize(("current", "legacy"), GERRIT_CASES.values(), ids=GERRIT_CASES.keys())
def test_gerrit_legacy_option_matches_current(gerrit_mocks, current, legacy):
    """The underscored spelling makes the same calls as the hyphenated one."""
    expected = _gerrit_calls(current, gerrit_mocks)
    assert _gerrit_calls(legacy, gerrit_mocks) == expected


@pytest.mark.xfail(strict=True, reason="legacy option names not yet accepted")
@pytest.mark.parametrize(("current", "legacy"), GITHUB_CASES.values(), ids=GITHUB_CASES.keys())
def test_github_legacy_option_matches_current(github_org, current, legacy):
    """The underscored spelling makes the same calls as the hyphenated one."""
    expected = _github_calls(current, github_org)
    assert expected
    assert _github_calls(legacy, github_org) == expected


@pytest.mark.parametrize("feature", ["issues", "projects", "wiki"])
def test_github_update_repo_off_form_still_works(github_org, feature):
    """The ``--no-has-*`` form still turns a feature off."""
    _github_calls(["update-repo", "o", "r", f"--no-has-{feature}"], github_org)
    edit = github_org.get_repo.return_value.edit
    assert edit.call_args.kwargs[f"has_{feature}"] is False


@pytest.mark.parametrize(
    "command",
    [
        pytest.param(
            "match-ldap-to-info",
            marks=pytest.mark.xfail(strict=True, reason="legacy command name not yet registered"),
        ),
        "match-ldap-info",
    ],
)
def test_lfidapi_match_ldap_names_reach_helper(command):
    """Both command names call the helper with the same arguments."""
    with patch("lftools_uv.typer_apps.lfidapi.helper_match_ldap_to_info") as helper:
        result = runner.invoke(app, ["lfidapi", command, "INFO.yaml", "grp", "--githuborg", "org", "--noop"])
    assert result.exit_code == 0, result.output
    helper.assert_called_once_with("INFO.yaml", "grp", "org", True)


@pytest.mark.xfail(strict=True, reason="legacy command name not yet registered")
def test_lfidapi_help_lists_match_ldap_to_info():
    """``lfidapi --help`` names the command as the legacy front-end does."""
    result = runner.invoke(app, ["lfidapi", "--help"])
    assert result.exit_code == 0, result.output
    assert "match-ldap-to-info" in result.output
