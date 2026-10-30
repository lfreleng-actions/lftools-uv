# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Click and Typer jenkins commands that run Groovy.

``groovy`` runs a file's script; ``get-credentials`` and ``get-secrets``
print each credential's password or secret; ``remove-offline-nodes``
removes the offline agents. Each sends its script to the Jenkins script
console through python-jenkins' ``run_script``.

The ``groovy`` tests keep python-jenkins' own ``run_script`` and fake only
``jenkins_open``: the fake console runs the script's ``print`` and
``println`` statements. The other tests mock ``run_script``. No test
reaches a server.
"""

import re
from collections.abc import Callable
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest import mock

import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package
import pytest
import requests
from click.testing import CliRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.jenkins import get_credentials, get_secrets, groovy, remove_offline_nodes
from lftools_uv.typer_apps.jenkins import jenkins_app

Run = Callable[[Any, list[str]], ClickResult | TyperResult]

_CLICK_COMMANDS = {
    "groovy": groovy,
    "get-credentials": get_credentials,
    "get-secrets": get_secrets,
    "remove-offline-nodes": remove_offline_nodes,
}


def _run_click(server: Any, args: list[str]) -> ClickResult:
    command, *rest = args
    return CliRunner().invoke(_CLICK_COMMANDS[command], rest, obj={"jenkins": SimpleNamespace(server=server)})


def _run_typer(server: Any, args: list[str]) -> TyperResult:
    with mock.patch("lftools_uv.typer_apps.jenkins.server.Jenkins", return_value=SimpleNamespace(server=server)):
        return TyperRunner().invoke(jenkins_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])

# A print or println statement whose argument, if any, is one string literal.
_PRINT = re.compile(r'(print|println)\s*\(?\s*(?:"((?:[^"\\]|\\.)*)")?\s*\)?')


def _console(request: requests.Request) -> str:
    """Answer a script console request with what its print statements print."""
    form = cast("dict[str, bytes]", request.data)
    printed: list[str] = []
    for line in form["script"].decode().splitlines():
        if not line.strip():
            continue
        statement = _PRINT.fullmatch(line.strip())
        assert statement, f"the fake console runs print statements only: {line!r}"
        text = (statement.group(2) or "").encode().decode("unicode_escape")
        printed.append(text + ("\n" if statement.group(1) == "println" else ""))
    return "".join(printed)


@pytest.fixture
def console_server():
    """Return a python-jenkins client whose script console is ``_console``."""
    server = jenkins.Jenkins("https://jenkins.example.org", username="admin", password="secret")
    with mock.patch.object(server, "jenkins_open", side_effect=_console):
        yield server


@FRONT_ENDS
@pytest.mark.parametrize(
    ("script", "stdout"),
    [
        pytest.param('print "alpha"', "alpha\n", id="no-newline"),
        pytest.param('println "alpha"\nprint "beta"', "alpha\nbeta\n", id="last-line"),
        pytest.param("", "", id="prints-nothing"),
        pytest.param('println "alpha"\nprintln "beta"', "alpha\nbeta\n", id="newline"),
        pytest.param('println ""', "\n", id="empty-line"),
    ],
)
def test_groovy_prints_script_output(
    run: Run, console_server: jenkins.Jenkins, tmp_path: Path, script: str, stdout: str
) -> None:
    path = tmp_path / "script.groovy"
    path.write_text(script)

    result = run(console_server, ["groovy", str(path)])

    assert result.exit_code == 0, result.output
    assert result.stdout == stdout


def _marker(script: str) -> str:
    """Return the marker the credentials script reports unreadable credentials with."""
    found = re.search(r'def marker = "(\w+)"', script)
    return found.group(1) if found else "no-marker"


def _credentials_server(shown: list[str], unreadable: list[str]) -> mock.MagicMock:
    """Answer the credentials script with *shown*, then *unreadable* after its marker."""

    def run_script(script: str) -> str:
        lines = [*shown, *(f"{_marker(script)} {item}" for item in unreadable)]
        return "".join(f"{line}\n" for line in lines)

    server = mock.MagicMock()
    server.run_script.side_effect = run_script
    return server


CREDENTIAL_COMMANDS = pytest.mark.parametrize(
    ("command", "field"), [("get-credentials", "password"), ("get-secrets", "secret")]
)


@FRONT_ENDS
@CREDENTIAL_COMMANDS
def test_readable_credentials_are_printed(run: Run, command: str, field: str) -> None:
    server = _credentials_server(["Printing...", "nexus-deploy : s3cret"], [])

    result = run(server, [command])

    assert result.exit_code == 0, result.output
    assert "nexus-deploy : s3cret" in result.stdout


@pytest.mark.xfail(strict=True, reason="#986: an unreadable credential is skipped and the command exits 0")
@FRONT_ENDS
@CREDENTIAL_COMMANDS
def test_unreadable_credential_exits_one(run: Run, command: str, field: str, caplog: pytest.LogCaptureFixture) -> None:
    server = _credentials_server(
        ["Printing...", "nexus-deploy : s3cret"],
        ["gerrit-bot: java.lang.IllegalStateException: secret store unreachable"],
    )

    result = run(server, [command])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "nexus-deploy : s3cret" in result.stdout
    assert "gerrit-bot" not in result.stdout
    assert "gerrit-bot: java.lang.IllegalStateException: secret store unreachable" in caplog.text
    assert field in caplog.text


@pytest.mark.xfail(strict=True, reason="#986: catch (MissingPropertyException) catches every exception")
@FRONT_ENDS
@CREDENTIAL_COMMANDS
def test_credentials_script_has_no_untyped_catch(run: Run, command: str, field: str) -> None:
    server = _credentials_server([], [])

    run(server, [command])

    script = str(server.run_script.call_args.args[0])
    # In Groovy, catch (Name) declares a variable called Name and catches any exception.
    assert not re.search(r"catch\s*\(\s*\w+\s*\)", script)


def _nodes_server() -> mock.MagicMock:
    server = mock.MagicMock()
    server.run_script.return_value = "Number of Nodes: 0\n"
    return server


@pytest.mark.xfail(strict=True, reason="#987: single-quoted Groovy strings print ${node.name} literally")
@FRONT_ENDS
def test_remove_offline_nodes_script_interpolates(run: Run) -> None:
    server = _nodes_server()

    result = run(server, ["remove-offline-nodes"])

    assert result.exit_code == 0, result.output
    script = str(server.run_script.call_args.args[0])
    assert "removeNode(slave)" in script
    assert not re.search(r"'[^'\n]*\$\{", script)
    assert re.search(r'"[^"\n]*Removing node \$\{node\.name\}[^"\n]*"', script)


@FRONT_ENDS
def test_force_remove_offline_nodes_script(run: Run) -> None:
    server = _nodes_server()

    result = run(server, ["remove-offline-nodes", "--force"])

    assert result.exit_code == 0, result.output
    script = str(server.run_script.call_args.args[0])
    assert "removeComputer(node)" in script
    assert not re.search(r"'[^'\n]*\$\{", script)
    assert "Number of Nodes: 0" in result.stdout


@FRONT_ENDS
@pytest.mark.parametrize("args", [["groovy"], ["get-credentials"], ["remove-offline-nodes"]], ids=lambda a: a[0])
def test_run_script_error_exits_one(run: Run, args: list[str], tmp_path: Path) -> None:
    server = mock.MagicMock()
    server.run_script.side_effect = jenkins.JenkinsException("java.lang.RuntimeException: boom")
    if args == ["groovy"]:
        path = tmp_path / "script.groovy"
        path.write_text('println "alpha"')
        args = ["groovy", str(path)]

    result = run(server, args)

    assert result.exit_code == 1
