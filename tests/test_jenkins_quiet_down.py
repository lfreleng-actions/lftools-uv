# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Click and Typer ``jenkins quiet-down`` commands."""

from types import SimpleNamespace
from unittest import mock

import pytest
import requests
from click.testing import CliRunner, Result
from typer.testing import CliRunner as TyperRunner

from lftools_uv.cli.jenkins import quiet_down
from lftools_uv.typer_apps.jenkins import jenkins_app

CSRF_MESSAGE = "does not support Quiet Down without a CSRF Token"


def _http_error(status_code: int) -> requests.exceptions.HTTPError:
    # python-jenkins re-raises the HTTPError from response.raise_for_status()
    response = requests.Response()
    response.status_code = status_code
    response.url = "https://jenkins.example.org/quietDown"
    return requests.exceptions.HTTPError(f"{status_code} Client Error", response=response)


def _server(error_code: int | None = None) -> mock.MagicMock:
    server = mock.MagicMock()
    server.get_version.return_value = "2.400"
    if error_code is not None:
        server.quiet_down.side_effect = _http_error(error_code)
    return server


def _invoke(server: mock.MagicMock, args: list[str], stdin: str | None = None) -> Result:
    return CliRunner().invoke(quiet_down, args, obj={"jenkins": SimpleNamespace(server=server)}, input=stdin)


@pytest.mark.parametrize("flag", ["-y", "--yes"])
def test_yes_quiets_down(flag: str) -> None:
    server = _server()

    result = _invoke(server, [flag])

    assert result.exit_code == 0
    server.quiet_down.assert_called_once_with()


def test_legacy_n_quiets_down() -> None:
    server = _server()

    result = _invoke(server, ["-n"])

    assert result.exit_code == 0
    server.quiet_down.assert_called_once_with()


@pytest.mark.parametrize("flag", ["-y", "-n"])
def test_405_exits_one(flag: str, caplog: pytest.LogCaptureFixture) -> None:
    server = _server(405)

    result = _invoke(server, [flag])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert CSRF_MESSAGE in caplog.text
    server.quiet_down.assert_called_once_with()


def test_other_http_error_propagates() -> None:
    server = _server(500)

    result = _invoke(server, ["-y"])

    assert result.exit_code != 0
    assert isinstance(result.exception, requests.exceptions.HTTPError)


def test_prompt_yes_quiets_down() -> None:
    server = _server()

    result = _invoke(server, [], stdin="y\n")

    assert result.exit_code == 0
    server.quiet_down.assert_called_once_with()


def test_prompt_no_cancels() -> None:
    server = _server()

    result = _invoke(server, [], stdin="n\n")

    assert result.exit_code == 0
    server.quiet_down.assert_not_called()


def test_typer_405_exits_one(caplog: pytest.LogCaptureFixture) -> None:
    server = _server(405)

    with mock.patch("lftools_uv.typer_apps.jenkins.server.Jenkins", return_value=SimpleNamespace(server=server)):
        result = TyperRunner().invoke(jenkins_app, ["quiet-down", "-y"])

    assert result.exit_code == 1
    assert CSRF_MESSAGE in caplog.text
    server.quiet_down.assert_called_once_with()
