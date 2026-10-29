# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Click and Typer ``jenkins jobs enable/disable`` commands.

Both must match REGEX as a regular expression against the full name of
every job that can be disabled, print the jobs they changed, and exit 1
when nothing matches or a job did not change. REGEX travels to Jenkins
base64-encoded, so it never becomes Groovy source.

Jenkins is a mock: no test reaches a server.
"""

import base64
import re
from collections.abc import Callable
from types import SimpleNamespace
from unittest import mock

import pytest
from click.testing import CliRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.jenkins.jobs import jobs
from lftools_uv.typer_apps.jenkins import jenkins_app

REGEX = "^ci-.*-verify$"

Run = Callable[[mock.MagicMock, list[str]], ClickResult | TyperResult]


def _run_click(server: mock.MagicMock, args: list[str]) -> ClickResult:
    return CliRunner().invoke(jobs, args, obj={"jenkins": SimpleNamespace(server=server)})


def _run_typer(server: mock.MagicMock, args: list[str]) -> TyperResult:
    with mock.patch("lftools_uv.typer_apps.jenkins.server.Jenkins", return_value=SimpleNamespace(server=server)):
        return TyperRunner().invoke(jenkins_app, ["jobs", *args])


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
ACTIONS = pytest.mark.parametrize("action", ["enable", "disable"])


def _server(output: str) -> mock.MagicMock:
    server = mock.MagicMock()
    server.run_script.return_value = output
    return server


def _script(server: mock.MagicMock) -> str:
    server.run_script.assert_called_once()
    return str(server.run_script.call_args.args[0])


@pytest.mark.xfail(strict=True, reason="#976: jobs enable/disable print the wrong jobs")
@FRONT_ENDS
@ACTIONS
def test_prints_changed_jobs(run: Run, action: str) -> None:
    server = _server("CHANGED ci-foo-verify\nCHANGED folder/ci-bar-verify\nMATCHED=3\n")

    result = run(server, [action, REGEX])

    assert result.exit_code == 0
    assert result.stdout == "ci-foo-verify\nfolder/ci-bar-verify\n"


@pytest.mark.xfail(strict=True, reason="#976: jobs enable/disable exit 0 when nothing matches")
@FRONT_ENDS
@ACTIONS
def test_no_match_exits_one(run: Run, action: str, caplog: pytest.LogCaptureFixture) -> None:
    server = _server("MATCHED=0\n")

    result = run(server, [action, "no-such-job"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "no-such-job" in caplog.text


@pytest.mark.xfail(strict=True, reason="#976: jobs enable/disable ignore jobs that did not change")
@FRONT_ENDS
@ACTIONS
def test_failed_job_exits_one(run: Run, action: str, caplog: pytest.LogCaptureFixture) -> None:
    server = _server("CHANGED ci-foo-verify\nFAILED ci-odd-verify\nMATCHED=2\n")

    result = run(server, [action, REGEX])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "ci-odd-verify" in caplog.text


@pytest.mark.xfail(strict=True, reason="#976: REGEX is pasted into the Groovy source")
@FRONT_ENDS
@pytest.mark.parametrize("regex", [REGEX, 'a"b\\d$c'], ids=["anchored", "quotes"])
def test_regex_sent_base64(run: Run, regex: str) -> None:
    server = _server("MATCHED=1\n")

    run(server, ["disable", regex])

    script = _script(server)
    assert base64.b64encode(regex.encode()).decode() in script
    assert regex not in script


@pytest.mark.xfail(strict=True, reason="#976: jobs enable/disable match display names literally")
@FRONT_ENDS
@ACTIONS
def test_script_matches_full_name_by_regex(run: Run, action: str) -> None:
    server = _server("MATCHED=1\n")

    run(server, [action, REGEX])

    script = _script(server)
    assert "FreeStyleProject" not in script
    assert ".contains(" not in script
    assert "ParameterizedJobMixIn.ParameterizedJob" in script
    assert re.search(r"\.matcher\(\s*job\.fullName\s*\)\.find\(\)", script)
    assert f"def disable = {'true' if action == 'disable' else 'false'}" in script


@FRONT_ENDS
@ACTIONS
def test_run_script_error_exits_one(run: Run, action: str) -> None:
    server = mock.MagicMock()
    server.run_script.side_effect = RuntimeError("Jenkins is down")

    result = run(server, [action, REGEX])

    assert result.exit_code == 1
