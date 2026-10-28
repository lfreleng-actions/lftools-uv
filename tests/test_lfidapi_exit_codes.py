# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the ``lfidapi`` command names and exit codes.

The legacy Click group must expose ``create-group`` under that name, and
``invite`` and ``create-group`` must fail, in both front-ends, when the
address is invalid or the group already exists, rather than log the problem
and report success.
"""

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.lfidapi import lfidapi
from lftools_uv.typer_apps.lfidapi import lfidapi_app


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(lfidapi, args, obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(lfidapi_app, args)


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.status_code = 200
    return response


@pytest.fixture
def mock_requests():
    """Stand in for the LFID API: a token, a base URL and a 200 response."""
    with (
        patch("lftools_uv.lfidapi.oauth_helper", return_value=("token", "https://lfid.example.org/groups/")),
        patch("lftools_uv.lfidapi.requests") as requests,
    ):
        requests.post.return_value = _ok_response()
        yield requests


def test_click_registers_create_group_name():
    """Click 8.2 strips ``_group`` from the derived name, so set it."""
    assert "create-group" in lfidapi.commands
    assert "create" not in lfidapi.commands


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_invite_invalid_email_exits_1(run, mock_requests):
    """An invalid address fails the command and sends no invitation."""
    result = run(["invite", "not-an-email", "grp"])

    assert result.exit_code == 1
    mock_requests.post.assert_not_called()
    assert "Invitation sent" not in result.output


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_invite_valid_email_exits_0(run, mock_requests):
    """A valid address is invited and the command succeeds."""
    with patch("lftools_uv.lfidapi.validate_email"):
        result = run(["invite", "someone@example.org", "grp"])

    assert result.exit_code == 0
    mock_requests.post.assert_called_once()


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_create_group_existing_exits_1(run, mock_requests):
    """Creating a group that already exists is an error."""
    with patch("lftools_uv.lfidapi.helper_check_group_exists", return_value=200):
        result = run(["create-group", "grp"])

    assert result.exit_code == 1
    mock_requests.post.assert_not_called()
    assert "created successfully" not in result.output


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_create_group_new_exits_0(run, mock_requests):
    """A group that does not exist yet is created and the command succeeds."""
    with patch("lftools_uv.lfidapi.helper_check_group_exists", return_value=404):
        result = run(["create-group", "grp"])

    assert result.exit_code == 0
    mock_requests.post.assert_called_once()
