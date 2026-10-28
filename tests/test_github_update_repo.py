# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``github update-repo`` in both front-ends.

The default CLI changes only the repository features named on the
command line. The legacy CLI keeps its documented behaviour of setting
all three features whenever one is given, and exits 1 when the
repository or a team is missing.
"""

from unittest import mock

import pytest
from github.GithubObject import NotSet
from typer.testing import CliRunner

from lftools_uv import cli
from lftools_uv.typer_apps.github_cli import github_app

runner = CliRunner()


def _changes(repo):
    """Return the features the ``edit`` calls changed, in call order."""
    changed = {}
    for call in repo.edit.call_args_list:
        changed.update({key: value for key, value in call.kwargs.items() if value is not NotSet})
    return changed


@pytest.fixture
def typer_org():
    """Patch the default CLI's GitHub client and return the organization mock."""
    with (
        mock.patch("lftools_uv.typer_apps.github_cli.config.get_setting", return_value="token"),
        mock.patch("lftools_uv.typer_apps.github_cli.Github") as github,
    ):
        yield github.return_value.get_organization.return_value


def _named(name):
    """Return a mock with its ``name`` attribute set."""
    obj = mock.MagicMock()
    obj.name = name
    return obj


@pytest.fixture
def legacy_org():
    """Patch the legacy CLI's GitHub client and return the organization mock.

    The organization holds repository ``r`` and team ``devs``.
    """
    with (
        mock.patch("lftools_uv.cli.github_cli.config.get_setting", return_value="token"),
        mock.patch("lftools_uv.cli.github_cli.Github") as github,
    ):
        org = github.return_value.get_organization.return_value
        org.get_repos.return_value = [_named("r")]
        org.get_teams.return_value = [_named("devs")]
        yield org


def _legacy_repo(org):
    return org.get_repos.return_value[0]


def _legacy_team(org):
    return org.get_teams.return_value[0]


def test_typer_add_team_changes_no_feature(typer_org):
    """Adding a team leaves the repository's features alone."""
    result = runner.invoke(github_app, ["update-repo", "o", "r", "--add-team", "devs"])
    repo = typer_org.get_repo.return_value
    assert result.exit_code == 0
    assert _changes(repo) == {}
    typer_org.get_team_by_slug.assert_called_once_with("devs")
    typer_org.get_team_by_slug.return_value.add_to_repos.assert_called_once_with(repo)


def test_typer_has_wiki_changes_only_wiki(typer_org):
    """``--has-wiki`` alone turns on the wiki and nothing else."""
    result = runner.invoke(github_app, ["update-repo", "o", "r", "--has-wiki"])
    assert result.exit_code == 0
    assert _changes(typer_org.get_repo.return_value) == {"has_wiki": True}


def test_typer_no_has_issues_changes_only_issues(typer_org):
    """``--no-has-issues`` turns off issues and nothing else."""
    result = runner.invoke(github_app, ["update-repo", "o", "r", "--no-has-issues"])
    assert result.exit_code == 0
    assert _changes(typer_org.get_repo.return_value) == {"has_issues": False}


def test_typer_no_options_changes_nothing(typer_org):
    """With nothing requested, nothing changes and the command succeeds."""
    result = runner.invoke(github_app, ["update-repo", "o", "r"])
    assert result.exit_code == 0
    assert _changes(typer_org.get_repo.return_value) == {}


def test_typer_all_features_on(typer_org):
    """All three ``--has-*`` flags turn all three features on."""
    result = runner.invoke(github_app, ["update-repo", "o", "r", "--has-issues", "--has-projects", "--has-wiki"])
    assert result.exit_code == 0
    assert _changes(typer_org.get_repo.return_value) == {"has_issues": True, "has_projects": True, "has_wiki": True}


@pytest.mark.parametrize(
    ("flag", "expected"),
    [
        ("--has_wiki", {"has_issues": False, "has_wiki": True, "has_projects": False}),
        ("--has_projects", {"has_issues": False, "has_wiki": False, "has_projects": True}),
    ],
)
def test_legacy_feature_flags(cli_runner, legacy_org, flag, expected):
    """One feature flag sets that feature and turns the other two off."""
    result = cli_runner.invoke(cli.cli, ["github", "update-repo", "o", "r", flag], obj={})
    assert result.exit_code == 0
    assert _changes(_legacy_repo(legacy_org)) == expected


def test_legacy_feature_missing_repo_exits_1(cli_runner, legacy_org):
    """A feature flag for a missing repository exits 1."""
    result = cli_runner.invoke(cli.cli, ["github", "update-repo", "o", "nosuch", "--has_wiki"], obj={})
    assert result.exit_code == 1


@pytest.mark.parametrize("option", ["--add_team", "--remove_team"])
def test_legacy_missing_team_exits_1(cli_runner, legacy_org, option):
    """A team that does not exist exits 1."""
    result = cli_runner.invoke(cli.cli, ["github", "update-repo", "o", "r", option, "nosuch"], obj={})
    assert result.exit_code == 1


def test_legacy_add_team(cli_runner, legacy_org):
    """``--add_team`` adds the team to the repository."""
    result = cli_runner.invoke(cli.cli, ["github", "update-repo", "o", "r", "--add_team", "devs"], obj={})
    assert result.exit_code == 0
    _legacy_team(legacy_org).add_to_repos.assert_called_once_with(_legacy_repo(legacy_org))


def test_legacy_add_team_missing_repo_exits_1(cli_runner, legacy_org):
    """``--add_team`` for a missing repository exits 1."""
    result = cli_runner.invoke(cli.cli, ["github", "update-repo", "o", "nosuch", "--add_team", "devs"], obj={})
    assert result.exit_code == 1
    _legacy_team(legacy_org).add_to_repos.assert_not_called()
