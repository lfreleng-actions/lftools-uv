# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Token lookup and shared behaviour of the ``github`` commands.

Every ``github`` command, in both front-ends, takes the ``token`` of
``[github.<org>]`` when that section has one and the ``token`` of
``[github]`` otherwise. ``create-repo``, ``create-team`` and the team
handling of ``update-repo`` behave the same in both front-ends.
"""

from __future__ import annotations

import logging
from unittest import mock

import pytest
from click.testing import CliRunner as ClickRunner
from github import GithubException, UnknownObjectException
from typer.testing import CliRunner as TyperRunner

from lftools_uv import config
from lftools_uv.cli.github_cli import github_cli
from lftools_uv.typer_apps.github_cli import github_app

_ORG = "an-org"
_REPO = "a-repo"
_TEAM_NAME = "Replication"
_TEAM_SLUG = "replication"


def _run_click(args):
    return ClickRunner().invoke(github_cli, args, obj={})


def _run_typer(args):
    return TyperRunner().invoke(github_app, args)


_FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _named(name, **attrs):
    obj = mock.MagicMock(**attrs)
    obj.name = name
    return obj


@pytest.fixture
def github():
    """Patch the GitHub client wherever the commands build one."""
    client = mock.MagicMock()
    with (
        mock.patch("lftools_uv.github_helper.Github", client),
        mock.patch("lftools_uv.cli.github_cli.Github", client),
        mock.patch("lftools_uv.typer_apps.github_cli.Github", client),
    ):
        yield client


@pytest.fixture
def org(github):
    """Return an organization holding ``_REPO`` and team ``_TEAM_NAME``."""
    org = github.return_value.get_organization.return_value
    repo = _named(_REPO)
    team = _named(_TEAM_NAME, slug=_TEAM_SLUG)

    def by_slug(slug):
        if slug == _TEAM_SLUG:
            return team
        raise UnknownObjectException(404, {"message": "Not Found"}, None)

    org.get_repos.return_value = [repo]
    org.get_repo.return_value = repo
    org.get_teams.return_value = [team]
    org.get_team_by_slug.side_effect = by_slug
    return org


# Token lookup

_COMMANDS = {
    "list": ["list", _ORG, "--teams"],
    "votes": ["votes", _ORG, _REPO, "1"],
    "user": ["user", _ORG, "a-user", _TEAM_NAME],
    "submit-pr": ["submit-pr", _ORG, _REPO, "1"],
    "create-repo": ["create-repo", _ORG, _REPO, "a description"],
    "update-repo": ["update-repo", _ORG, _REPO, "--has_wiki"],
    "create-team": ["create-team", _ORG, "a-team", "closed"],
}


@pytest.fixture
def write_config(tmp_path, monkeypatch):
    """Point the configuration at a file holding the given sections."""
    path = tmp_path / "lftools.ini"
    monkeypatch.setattr(config, "LFTOOLS_CONFIG_FILE", str(path))

    def _write(sections):
        path.write_text("".join(f"[{name}]\ntoken = {token}\n" for name, token in sections.items()))

    return _write


@pytest.mark.parametrize(
    ("sections", "expected"),
    [
        ({"github": "global-token"}, "global-token"),
        ({f"github.{_ORG}": "org-token"}, "org-token"),
        ({"github": "global-token", f"github.{_ORG}": "org-token"}, "org-token"),
    ],
    ids=["github-only", "org-only", "both"],
)
@pytest.mark.parametrize("command", list(_COMMANDS))
@_FRONT_ENDS
def test_token_lookup(run, command, sections, expected, write_config, github):
    """The organization's own token wins; ``[github]`` is the fallback."""
    write_config(sections)

    run(_COMMANDS[command])

    assert github.call_args_list[0] == mock.call(expected)


@pytest.mark.parametrize("command", list(_COMMANDS))
@_FRONT_ENDS
def test_no_token_exits_nonzero(run, command, write_config, github, caplog):
    """With neither section, the command names both and exits non-zero."""
    write_config({"other": "x"})

    with caplog.at_level(logging.ERROR):
        result = run(_COMMANDS[command])

    assert result.exit_code != 0
    assert isinstance(result.exception, SystemExit)
    assert f"[github.{_ORG}]" in caplog.text
    assert "[github]" in caplog.text
    github.assert_not_called()


# Shared behaviour

_TOKEN = mock.patch("lftools_uv.config.get_setting", return_value="token")


@pytest.mark.parametrize("team", [_TEAM_NAME, _TEAM_SLUG], ids=["name", "slug"])
@_FRONT_ENDS
def test_update_repo_add_team_grants_push(run, team, org):
    """A team named by name or slug is added and granted ``push``."""
    with _TOKEN:
        result = run(["update-repo", _ORG, _REPO, "--add_team", team])

    assert result.exit_code == 0
    team_obj = org.get_teams.return_value[0]
    repo = org.get_repos.return_value[0]
    team_obj.add_to_repos.assert_called_once_with(repo)
    team_obj.update_team_repository.assert_called_once_with(repo, "push")


@pytest.mark.parametrize("team", [_TEAM_NAME, _TEAM_SLUG], ids=["name", "slug"])
@_FRONT_ENDS
def test_update_repo_remove_team(run, team, org):
    """A team named by name or slug is removed."""
    with _TOKEN:
        result = run(["update-repo", _ORG, _REPO, "--remove_team", team])

    assert result.exit_code == 0
    org.get_teams.return_value[0].remove_from_repos.assert_called_once_with(org.get_repos.return_value[0])


@pytest.mark.parametrize("option", ["--add_team", "--remove_team"])
@_FRONT_ENDS
def test_update_repo_unknown_team_exits_1(run, option, org):
    """An unknown team exits 1 and changes nothing."""
    with _TOKEN:
        result = run(["update-repo", _ORG, _REPO, option, "nosuch"])

    assert result.exit_code == 1
    team_obj = org.get_teams.return_value[0]
    team_obj.add_to_repos.assert_not_called()
    team_obj.remove_from_repos.assert_not_called()


@pytest.mark.parametrize("option", ["--add_team", "--remove_team"])
@_FRONT_ENDS
def test_update_repo_unknown_team_leaves_features(run, option, org):
    """An unknown team exits 1 before any repository feature changes."""
    with _TOKEN:
        result = run(["update-repo", _ORG, _REPO, "--has_wiki", option, "nosuch"])

    assert result.exit_code == 1
    org.get_repos.return_value[0].edit.assert_not_called()


@pytest.mark.parametrize(
    "error",
    [GithubException(500, {"message": "boom"}, None), UnknownObjectException(404, {"message": "boom"}, None)],
    ids=["500", "404"],
)
@_FRONT_ENDS
def test_update_repo_team_listing_error_exits_1(run, error, org, caplog):
    """An API error while listing teams, a 404 included, is logged and exits 1."""
    org.get_teams.side_effect = error

    with _TOKEN, caplog.at_level(logging.ERROR):
        result = run(["update-repo", _ORG, _REPO, "--has_wiki", "--add_team", _TEAM_NAME])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "boom" in caplog.text
    assert "team not found" not in caplog.text
    org.get_repos.return_value[0].edit.assert_not_called()


@_FRONT_ENDS
def test_create_repo_existing_exits_1(run, org):
    """An existing repository exits 1 and nothing is created."""
    with _TOKEN:
        result = run(["create-repo", _ORG, _REPO, "a description"])

    assert result.exit_code == 1
    org.create_repo.assert_not_called()


@_FRONT_ENDS
def test_create_repo_settings(run, org):
    """A new repository is public, empty and refuses rebase merges."""
    with _TOKEN:
        result = run(["create-repo", _ORG, "new-repo", "a description"])

    assert result.exit_code == 0
    org.create_repo.assert_called_once_with(
        "new-repo",
        allow_rebase_merge=False,
        auto_init=False,
        description="a description",
        has_issues=False,
        has_projects=False,
        has_wiki=False,
        private=False,
    )


@_FRONT_ENDS
def test_create_team_existing_exits_1(run, org):
    """An existing team name exits 1 and nothing is created."""
    with _TOKEN:
        result = run(["create-team", _ORG, _TEAM_NAME, "closed"])

    assert result.exit_code == 1
    org.create_team.assert_not_called()


@_FRONT_ENDS
def test_create_team_missing_repo_exits_1(run, org):
    """``--repo`` naming no repository exits 1 and nothing is created."""
    with _TOKEN:
        result = run(["create-team", _ORG, "new-team", "closed", "--repo", "nosuch"])

    assert result.exit_code == 1
    org.create_team.assert_not_called()


@_FRONT_ENDS
def test_create_team_with_repo(run, org):
    """``--repo`` creates the team with that repository."""
    with _TOKEN:
        result = run(["create-team", _ORG, "new-team", "closed", "--repo", _REPO])

    assert result.exit_code == 0
    org.create_team.assert_called_once_with(
        name="new-team", repo_names=[org.get_repos.return_value[0]], privacy="closed"
    )
