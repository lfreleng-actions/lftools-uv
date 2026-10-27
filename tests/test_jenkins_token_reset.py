# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the exit status of ``jenkins token reset`` in both front-ends."""

import contextlib
import importlib
from types import SimpleNamespace
from unittest import mock

import pytest
import requests
from click.testing import CliRunner
from typer.main import get_command

# ``lftools_uv.cli.jenkins`` re-exports the Click ``token`` group under the
# module's own name, so a dotted patch target would resolve to the group.
click_token_module = importlib.import_module("lftools_uv.cli.jenkins.token")
typer_token_module = importlib.import_module("lftools_uv.typer_apps.jenkins.token")

JJB_INI = """\
[srv1]
url = https://jenkins1.example.org
user = user
password = old1

[srv2]
url = https://jenkins2.example.org
user = user
password = old2
"""

FRONT_ENDS = {
    "click": click_token_module.token,
    "typer": get_command(typer_token_module.token_app),
}

runner = CliRunner()


def _invoke(front_end, tmp_path, args):
    config_file = tmp_path / "jenkins_jobs.ini"
    config_file.write_text(JJB_INI)
    obj = {
        "jenkins": SimpleNamespace(config_file=str(config_file)),
        "username": "user",
        "password": "secret",
    }
    return runner.invoke(FRONT_ENDS[front_end], ["reset", *args], obj=obj)


def _refused(*_args, **_kwargs):
    raise requests.exceptions.ConnectionError("connection refused")


def _patch_get_token(**kwargs):
    """Patch ``get_token`` in both front-end modules."""
    stack = contextlib.ExitStack()
    for module in (click_token_module, typer_token_module):
        stack.enter_context(mock.patch.object(module, "get_token", **kwargs))
    return stack


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_single_server_reset_failure_exits_1(front_end, tmp_path):
    """A failed reset of one server exits 1 and prints no token."""
    with _patch_get_token(side_effect=_refused):
        result = _invoke(front_end, tmp_path, ["srv1"])

    assert result.exit_code == 1
    assert result.stdout == ""


@pytest.mark.parametrize("front_end", FRONT_ENDS)
@pytest.mark.parametrize("args", [[], ["srv1", "srv2"]], ids=["all", "listed"])
def test_multi_server_reset_failure_exits_1(front_end, args, tmp_path):
    """Any failed reset in multi-server mode exits 1."""
    with _patch_get_token(side_effect=_refused):
        result = _invoke(front_end, tmp_path, args)

    assert result.exit_code == 1


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_single_server_reset_success_prints_token(front_end, tmp_path):
    """A successful reset of one server prints the new token and exits 0."""
    with _patch_get_token(return_value="new-token"):
        result = _invoke(front_end, tmp_path, ["srv1"])

    assert result.exit_code == 0
    assert result.stdout.strip() == "new-token"


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_multi_server_reset_success_exits_0(front_end, tmp_path):
    """A multi-server reset where every server succeeds exits 0."""
    with _patch_get_token(return_value="new-token"):
        result = _invoke(front_end, tmp_path, [])

    assert result.exit_code == 0
    assert "new-token" in (tmp_path / "jenkins_jobs.ini").read_text()
