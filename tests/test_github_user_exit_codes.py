# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the ``github user`` exit codes.

A failed team add, remove or invitation, and a membership check that answers
neither 204 (member) nor 404 (not a member), must fail the command in both
front-ends rather than log the problem and exit 0.
"""

from unittest.mock import MagicMock, call, patch

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from github import GithubException
from github.NamedUser import NamedUser
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.github_cli import github_cli
from lftools_uv.typer_apps.github_cli import github_app

_ORG = "an-org"
_USER = "a-user"
_TEAM = "a-team"
_ORG_URL = f"https://api.github.com/orgs/{_ORG}"
_REDIRECT = f"https://api.github.com/orgs/{_ORG}/public_members/{_USER}"


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(github_cli, ["user", _ORG, _USER, _TEAM, *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(github_app, ["user", _ORG, _USER, _TEAM, *args])


def _make_org(membership_status: int, *, redirect: bool = False) -> MagicMock:
    """Build an organization whose membership check answers ``membership_status``.

    With ``redirect``, the check first answers 302 to ``_REDIRECT``, and the
    status comes from the GET that follows it.
    """
    team = MagicMock()
    team.name = _TEAM
    team.id = 1

    org = MagicMock()
    org.url = _ORG_URL
    if redirect:
        org.requester.requestJson.side_effect = [
            (302, {"location": _REDIRECT}, ""),
            (membership_status, {}, ""),
        ]
    else:
        org.requester.requestJson.return_value = (membership_status, {}, "")
    org.get_teams.return_value = [team]
    org.get_team.return_value = team
    return org


@pytest.fixture
def make_github():
    """Patch the GitHub client and return a factory for its organization."""
    user = MagicMock(spec=NamedUser)
    user.login = _USER
    with (
        patch("lftools_uv.github_helper.config.get_setting", return_value="token"),
        patch("lftools_uv.github_helper.Github") as github,
    ):
        client = github.return_value
        client.get_user.return_value = user

        def _factory(membership_status: int, *, redirect: bool = False) -> MagicMock:
            org = _make_org(membership_status, redirect=redirect)
            client.get_organization.return_value = org
            return org

        yield _factory


def _error(status: int) -> GithubException:
    return GithubException(status, {"message": "refused"}, None)


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_failed_removal_exits_1(run, make_github):
    """A removal GitHub refuses fails the command."""
    org = make_github(204)
    org.get_team.return_value.remove_membership.side_effect = _error(403)

    result = run(["--delete"])

    assert result.exit_code == 1


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_add_non_member_failed_invite_exits_1(run, make_github):
    """An invitation GitHub refuses fails the command."""
    org = make_github(404)
    org.invite_user.side_effect = _error(422)

    result = run([])

    assert result.exit_code == 1


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_add_member_failed_add_exits_1(run, make_github):
    """A team add GitHub refuses fails the command."""
    org = make_github(204)
    org.get_team.return_value.add_membership.side_effect = _error(403)

    result = run([])

    assert result.exit_code == 1


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_membership_check_forbidden_exits_1(run, make_github):
    """A 403 from the membership check is an error, not "not a member"."""
    org = make_github(403)

    result = run(["--delete"])

    assert result.exit_code == 1
    org.get_team.return_value.remove_membership.assert_not_called()


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_member_exits_0(run, make_github):
    """Removing a member succeeds."""
    org = make_github(204)

    result = run(["--delete"])

    assert result.exit_code == 0
    org.get_team.return_value.remove_membership.assert_called_once()


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_non_member_exits_0(run, make_github):
    """A non-member has nothing to remove; say so and succeed."""
    org = make_github(404)

    result = run(["--delete"])

    assert result.exit_code == 0
    assert "cannot delete" in result.output
    org.get_team.return_value.remove_membership.assert_not_called()


def _assert_followed_redirect(org: MagicMock) -> None:
    assert org.requester.requestJson.call_args_list == [
        call("GET", f"{_ORG_URL}/members/{_USER}"),
        call("GET", _REDIRECT),
    ]


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_redirected_member_exits_0(run, make_github):
    """A 302 to a 204 is a member, read from the redirect's location."""
    org = make_github(204, redirect=True)

    result = run(["--delete"])

    assert result.exit_code == 0
    _assert_followed_redirect(org)
    org.get_team.return_value.remove_membership.assert_called_once()


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_redirected_non_member_exits_0(run, make_github):
    """A 302 to a 404 is a non-member, read from the redirect's location."""
    org = make_github(404, redirect=True)

    result = run(["--delete"])

    assert result.exit_code == 0
    assert "cannot delete" in result.output
    _assert_followed_redirect(org)
    org.get_team.return_value.remove_membership.assert_not_called()


@pytest.mark.parametrize("args", [["--delete"], []], ids=["delete", "add"])
@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_redirected_membership_check_forbidden_exits_1(run, args, make_github):
    """A 302 to a 403 is an error, and nothing changes membership."""
    org = make_github(403, redirect=True)

    result = run(args)

    assert result.exit_code == 1
    _assert_followed_redirect(org)
    team = org.get_team.return_value
    team.remove_membership.assert_not_called()
    team.add_membership.assert_not_called()
    org.invite_user.assert_not_called()
