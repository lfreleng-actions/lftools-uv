# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the running builds ``openstack stack delete-stale`` keeps stacks for.

``delete-stale`` deletes the stacks of builds that are no longer running, so
it must list every running build: those on a node whose details Jenkins
cannot serve, and Pipeline builds that hold only a one-off executor. When it
cannot list the builds, it must say so and stop before deleting anything.

Each test drives a real python-jenkins client; ``responses`` answers every
HTTP request, so no test reaches a server. The OpenStack connection and
``stack.delete`` are mocks.
"""

import json
import re
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

import pytest
import requests
import responses
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from openstack.orchestration.v1.stack import Stack
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.openstack import cmd as os_cmd
from lftools_uv.typer_apps.openstack import openstack_app

XFAIL = pytest.mark.xfail(strict=True, reason="#1011: delete-stale misses builds python-jenkins does not list")

URL = "https://jenkins.example.org/releng"

Run = Callable[[list[str]], ClickResult | TyperResult]


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(os_cmd.openstack, ["--os-cloud", "test-cloud", *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(openstack_app, ["--os-cloud", "test-cloud", *args])


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _busy(executor: int, job: str, number: int) -> dict[str, Any]:
    """Return executor number *executor*, running build *number* of *job*."""
    return {"number": executor, "currentExecutable": {"number": number, "url": f"{URL}/job/{job}/{number}/"}}


# Nodes as Jenkins describes them: a Pipeline build between node blocks,
# holding only the built-in node's one-off executor, a long build on agent-1,
# and on agent-2 a build and an idle executor.
COMPUTERS: list[dict[str, Any]] = [
    {"displayName": "Built-In Node", "executors": [], "oneOffExecutors": [_busy(-1, "pipe", 7)]},
    {"displayName": "agent-1", "executors": [_busy(0, "csit-longevity", 111)], "oneOffExecutors": []},
    {
        "displayName": "agent-2",
        "executors": [_busy(0, "csit-job", 112), {"number": 1, "currentExecutable": None}],
        "oneOffExecutors": [],
    },
]

# Stacks past the default minimum age of 24 hours: one for each running
# build, and one whose build has finished.
STACKS = [
    ("id-pipe", "releng-pipe-7"),
    ("id-longevity", "releng-csit-longevity-111"),
    ("id-active", "releng-csit-job-112"),
    ("id-orphan", "releng-csit-job-99"),
]


def _only(executable: dict[str, Any] | None, fields: list[str]) -> dict[str, Any] | None:
    """Return *executable* with only *fields*, as a ``tree`` query does; None for an idle executor."""
    return None if executable is None else {field: executable[field] for field in fields if field in executable}


def _project(computer: dict[str, Any], tree: str) -> dict[str, Any]:
    """Return *computer* as Jenkins answers the ``tree`` query *tree*.

    It holds only the executor lists *tree* names, and each executable only
    the fields named for it, so a field the query leaves out is missing.
    """
    projected: dict[str, Any] = {"displayName": computer["displayName"]}
    for key in ("executors", "oneOffExecutors"):
        match = re.search(rf"(?<![A-Za-z]){key}\[currentExecutable\[([^\]]*)\]\]", tree)
        if match:
            fields = match.group(1).split(",")
            projected[key] = [{"currentExecutable": _only(e["currentExecutable"], fields)} for e in computer[key]]
    return projected


def _serve_jenkins() -> None:
    """Answer every request to ``URL`` from ``COMPUTERS``, as Jenkins would.

    Jenkins issues no crumbs, and a ``tree`` query gets only the fields it
    names. A request for agent-1's details at depth 2 fails with HTTP 500,
    as it does when one of a node's builds cannot be serialized.
    """

    def answer(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        url = urlsplit(str(request.url))
        query = parse_qs(url.query)
        if url.path == "/releng/computer/api/json":
            if "tree" in query:
                return 200, {}, json.dumps({"computer": [_project(c, query["tree"][0]) for c in COMPUTERS]})
            names = [{"displayName": c["displayName"], "offline": False} for c in COMPUTERS]
            return 200, {}, json.dumps({"computer": names})
        name = unquote(url.path.split("/")[3]).replace("(master)", "Built-In Node")
        if name == "agent-1" and query.get("depth") == ["2"]:
            return 500, {}, "java.lang.IllegalStateException: a build on this node could not be serialized"
        return 200, {}, json.dumps(next(c for c in COMPUTERS if c["displayName"] == name))

    responses.add(responses.GET, f"{URL}/crumbIssuer/api/json", status=404)
    responses.add_callback(responses.GET, re.compile(rf"{re.escape(URL)}/computer/.*"), callback=answer)


def _heat_stack(stack_id: str, name: str) -> Stack:
    """Return a stack as openstacksdk lists it, created 30 hours ago."""
    created = datetime.now(UTC) - timedelta(hours=30)
    return Stack.existing(
        id=stack_id,
        stack_name=name,
        stack_status="CREATE_COMPLETE",
        creation_time=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@pytest.fixture
def deleted():
    """Make the cloud list ``STACKS``; return the mock of ``stack.delete``."""
    with (
        mock.patch("lftools_uv.openstack.stack.openstack.connection.from_config") as from_config,
        mock.patch("lftools_uv.openstack.stack.delete", return_value=True) as delete,
    ):
        from_config.return_value.search_stacks.return_value = [_heat_stack(*stack) for stack in STACKS]
        yield delete


@XFAIL
@FRONT_ENDS
def test_delete_stale_keeps_stacks_of_running_builds(run: Run, deleted: mock.MagicMock) -> None:
    _serve_jenkins()

    result = run(["stack", "delete-stale", URL])

    assert result.exit_code == 0, result.output
    assert [c.args for c in deleted.call_args_list] == [("test-cloud", "id-orphan")]


def _agent_running(executor: Any) -> dict[str, Any]:
    """Return Jenkins' answer for agent-1, with *executor* as its one executor."""
    return {"json": {"computer": [{"displayName": "agent-1", "executors": [executor], "oneOffExecutors": []}]}}


# Ways the build list can be unreadable: Jenkins fails the request, answers
# without listing a node's executors, or with an executor that is neither
# idle nor running a build with a URL and a number, or cannot be reached.
UNREADABLE = pytest.mark.parametrize(
    "answer",
    [
        {"status": 500, "body": "java.lang.Error"},
        {"json": {"computer": [{"displayName": "agent-1", "executors": "busy", "oneOffExecutors": []}]}},
        _agent_running("busy"),
        _agent_running({"currentExecutable": "busy"}),
        _agent_running({"currentExecutable": {"number": 7, "url": ""}}),
        _agent_running({"currentExecutable": {"url": f"{URL}/job/csit-job/112/"}}),
        _agent_running({"currentExecutable": {"number": True, "url": f"{URL}/job/csit-job/112/"}}),
        None,
    ],
    ids=[
        "server-error",
        "executors-not-list",
        "executor-not-object",
        "executable-not-object",
        "build-without-url",
        "build-without-number",
        "build-number-boolean",
        "unreachable",
    ],
)


def _serve_answer(answer: dict[str, Any] | None) -> None:
    """Answer every request for ``URL``'s nodes with *answer*; None leaves Jenkins unreachable."""
    if answer is not None:
        responses.add(responses.GET, f"{URL}/crumbIssuer/api/json", status=404)
        responses.add(responses.GET, re.compile(rf"{re.escape(URL)}/computer/.*"), **answer)


@FRONT_ENDS
@UNREADABLE
def test_delete_stale_deletes_nothing_without_build_list(
    run: Run, deleted: mock.MagicMock, answer: dict[str, Any] | None
) -> None:
    _serve_answer(answer)

    result = run(["stack", "delete-stale", URL])

    assert result.exit_code == 1
    deleted.assert_not_called()


@XFAIL
@FRONT_ENDS
@UNREADABLE
@pytest.mark.usefixtures("deleted")
def test_delete_stale_reports_unreadable_build_list(
    run: Run, answer: dict[str, Any] | None, caplog: pytest.LogCaptureFixture
) -> None:
    _serve_answer(answer)

    run(["stack", "delete-stale", URL])

    assert f"Could not list the builds running on {URL}" in caplog.text
    assert "no stack was deleted" in caplog.text
