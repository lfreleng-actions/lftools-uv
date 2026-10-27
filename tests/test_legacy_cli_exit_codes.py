# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Exit codes of legacy Click commands when the remote API call fails.

The Typer front-end exits 1 when GitHub or Read the Docs rejects a
request. The legacy Click commands, reachable with ``LEGACY_CLI=1``,
must do the same rather than log the failure and exit 0.
"""

from unittest import mock

import pytest
from github import GithubException

from lftools_uv import cli
from lftools_uv.api.endpoints.readthedocs import ReadTheDocsError, ReadTheDocsNotFoundError


@pytest.fixture
def github_org():
    """Patch the GitHub client and return the organization mock."""
    with (
        mock.patch("lftools_uv.cli.github_cli.config.get_setting", return_value="token"),
        mock.patch("lftools_uv.cli.github_cli.Github") as github,
    ):
        org = github.return_value.get_organization.return_value
        org.get_repos.return_value = []
        org.get_teams.return_value = []
        yield org


@pytest.mark.xfail(strict=True, reason="#853: create-repo exits 0 on API error")
def test_github_create_repo_api_error_exits_1(cli_runner, github_org):
    """``github create-repo`` exits 1 when GitHub rejects the repository."""
    github_org.create_repo.side_effect = GithubException(422, message="Validation Failed")
    result = cli_runner.invoke(cli.cli, ["github", "create-repo", "o", "r", "desc"], obj={})
    assert github_org.create_repo.called
    assert result.exit_code == 1


@pytest.mark.xfail(strict=True, reason="#853: create-team exits 0 on API error")
@pytest.mark.parametrize("with_repo", [False, True])
def test_github_create_team_api_error_exits_1(cli_runner, github_org, with_repo):
    """``github create-team`` exits 1 when GitHub rejects the team."""
    args = ["github", "create-team", "o", "t", "closed"]
    if with_repo:
        repo = mock.MagicMock()
        repo.name = "r"
        github_org.get_repos.return_value = [repo]
        args += ["--repo", "r"]
    github_org.create_team.side_effect = GithubException(403, message="Forbidden")
    result = cli_runner.invoke(cli.cli, args, obj={})
    assert github_org.create_team.called
    assert result.exit_code == 1


@pytest.mark.xfail(strict=True, reason="#864: subproject-delete exits 0 on API error")
@pytest.mark.parametrize(
    "error",
    [ReadTheDocsNotFoundError("not found"), ReadTheDocsError("server error")],
    ids=["not-found", "error"],
)
def test_rtd_subproject_delete_api_error_exits_1(cli_runner, error):
    """``rtd subproject-delete`` exits 1 when the API call fails."""
    with mock.patch("lftools_uv.cli.rtd.readthedocs.ReadTheDocs") as rtd_client:
        rtd_client.return_value.subproject_delete.side_effect = error
        result = cli_runner.invoke(cli.cli, ["rtd", "subproject-delete", "parent", "child"], obj={})
    assert rtd_client.return_value.subproject_delete.called
    assert result.exit_code == 1
