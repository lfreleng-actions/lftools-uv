# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Click and Typer ``jenkins builds running`` and ``plugins sec`` commands.

``builds running`` must list every build on every node: those on a node
whose details Jenkins cannot serve, Pipeline builds on one-off executors,
and folder jobs by their full name. ``plugins sec`` must report every
advisory that applies to an installed plugin, decided as Jenkins does by
the advisory's version patterns, from the feed fetched over HTTPS.

Each test drives a real python-jenkins client; ``responses`` answers every
HTTP request, so no test reaches a server.
"""

import json
import re
from collections.abc import Callable
from types import SimpleNamespace
from typing import Any
from unittest import mock
from urllib.parse import parse_qs, unquote, urlsplit

import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package
import pytest
import requests
import responses
from click.testing import CliRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.jenkins.builds import running
from lftools_uv.cli.jenkins.plugins import sec
from lftools_uv.typer_apps.jenkins import jenkins_app

URL = "https://jenkins.example.org"
FEED = "https://updates.jenkins.io/update-center.actual.json"
OLD_FEED = "http://updates.jenkins-ci.org/update-center.actual.json"

Run = Callable[[jenkins.Jenkins, list[str]], ClickResult | TyperResult]

_CLICK_COMMANDS = {"running": running, "sec": sec}


def _run_click(server: jenkins.Jenkins, args: list[str]) -> ClickResult:
    return CliRunner().invoke(_CLICK_COMMANDS[args[-1]], [], obj={"jenkins": SimpleNamespace(server=server)})


def _run_typer(server: jenkins.Jenkins, args: list[str]) -> TyperResult:
    with mock.patch("lftools_uv.typer_apps.jenkins.server.Jenkins", return_value=SimpleNamespace(server=server)):
        return TyperRunner().invoke(jenkins_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


@pytest.fixture
def server():
    """Return a python-jenkins client for ``URL``, which issues no crumbs."""
    responses.add(responses.GET, f"{URL}/crumbIssuer/api/json", status=404)
    return jenkins.Jenkins(URL, username="admin", password="secret")


def _busy(executor: int, job_path: str, number: int) -> dict[str, Any]:
    """Return executor number *executor*, running build *number* of *job_path*."""
    return {"number": executor, "currentExecutable": {"number": number, "url": f"{URL}/{job_path}/{number}/"}}


# Nodes as Jenkins describes them: a Pipeline build on the built-in node's
# one-off executor, a freestyle build on agent-1, and on agent-2 a folder
# job's build, a build of a job whose name holds a space, and an idle executor.
COMPUTERS: list[dict[str, Any]] = [
    {"displayName": "Built-In Node", "executors": [], "oneOffExecutors": [_busy(-1, "job/pipe", 7)]},
    {"displayName": "agent-1", "executors": [_busy(0, "job/app-merge", 41)], "oneOffExecutors": []},
    {
        "displayName": "agent-2",
        "executors": [
            _busy(0, "job/folder/job/app-verify", 12),
            _busy(1, "job/my%20app", 3),
            {"number": 2, "currentExecutable": None},
        ],
        "oneOffExecutors": [],
    },
]


def _serve_computers(computers: list[dict[str, Any]]) -> None:
    """Answer every ``/computer/`` request from *computers*, as Jenkins would.

    A request for agent-1's details at depth 2 fails with HTTP 500, as it
    does when one of a node's builds cannot be serialized.
    """

    def answer(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        url = urlsplit(str(request.url))
        query = parse_qs(url.query)
        if url.path == "/computer/api/json":
            if "tree" in query:
                return 200, {}, json.dumps({"computer": computers})
            names = [{"displayName": c["displayName"], "offline": False} for c in computers]
            return 200, {}, json.dumps({"computer": names})
        name = unquote(url.path.split("/")[2]).replace("(master)", "Built-In Node")
        if name == "agent-1" and query.get("depth") == ["2"]:
            return 500, {}, "java.lang.IllegalStateException: a build on this node could not be serialized"
        return 200, {}, json.dumps(next(c for c in computers if c["displayName"] == name))

    responses.add_callback(responses.GET, re.compile(rf"{re.escape(URL)}/computer/.*"), callback=answer)


def _serve_answer(answer: Any) -> None:
    """Answer every ``/computer/`` request with the JSON *answer*."""
    responses.add(responses.GET, re.compile(rf"{re.escape(URL)}/computer/.*"), json=answer)


@FRONT_ENDS
def test_builds_running_lists_every_build(run: Run, server: jenkins.Jenkins) -> None:
    _serve_computers(COMPUTERS)

    result = run(server, ["builds", "running"])

    assert result.exit_code == 0, result.output
    assert result.stdout == (
        "- pipe on Built-In Node\n- app-merge on agent-1\n- folder/app-verify on agent-2\n- my app on agent-2\n"
    )


@FRONT_ENDS
def test_builds_running_warns_about_executable_without_url(
    run: Run, server: jenkins.Jenkins, caplog: pytest.LogCaptureFixture
) -> None:
    unexpected = {"number": 0, "currentExecutable": {"_class": "Unexpected"}}
    _serve_computers(
        [{"displayName": "agent-3", "executors": [unexpected, _busy(1, "job/a", 1)], "oneOffExecutors": []}]
    )

    result = run(server, ["builds", "running"])

    assert result.exit_code == 0, result.output
    assert result.stdout == "- a on agent-3\n"
    assert "agent-3" in caplog.text
    assert "no URL" in caplog.text


@FRONT_ENDS
@pytest.mark.parametrize(
    "answer",
    [
        {"computer": None},
        {},
        [],
        {"computer": ["agent-1"]},
        {"computer": [{"displayName": "agent-1", "executors": "busy", "oneOffExecutors": []}]},
    ],
    ids=["no-nodes", "empty", "not-object", "node-not-object", "executors-not-list"],
)
def test_builds_running_unusable_answer_exits_one(
    run: Run, server: jenkins.Jenkins, caplog: pytest.LogCaptureFixture, answer: Any
) -> None:
    _serve_answer(answer)

    result = run(server, ["builds", "running"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert re.search(r"Jenkins (did not list|listed a node as)", caplog.text)
    assert result.stdout == ""


@FRONT_ENDS
def test_builds_running_server_error_exits_one(run: Run, server: jenkins.Jenkins) -> None:
    responses.add(responses.GET, re.compile(rf"{re.escape(URL)}/computer/.*"), status=500, body="java.lang.Error")

    result = run(server, ["builds", "running"])

    assert result.exit_code == 1
    assert result.stdout == ""


# Advisories copied from the Jenkins update center, with a core advisory
# and a malformed one that names no plugin version, which must be ignored.
WARNINGS: list[dict[str, Any]] = [
    {
        "id": "SECURITY-372-email-ext",
        "name": "email-ext",
        "type": "plugin",
        "url": "https://jenkins.io/security/advisory/2017-03-20/",
        "versions": [{"lastVersion": "2.57", "pattern": "2[.]([0-9]|[1234][0-9]|5[0123456])(|[.-].*)|2.57(|[-].*)"}],
    },
    {
        "id": "SECURITY-257",
        "name": "email-ext",
        "type": "plugin",
        "url": "https://jenkins.io/security/advisory/2017-04-10/",
        "versions": [
            {
                "lastVersion": "2.57.1",
                "pattern": "2[.]([0-9]|[1234][0-9]|5[0123456])(|[.-].*)|2.57(|[-].*)|2.57.1(|[.-].*)",
            }
        ],
    },
    {
        "id": "SECURITY-504",
        "name": "vsphere-cloud",
        "type": "plugin",
        "url": "https://jenkins.io/security/advisory/2018-03-26/#SECURITY-504",
        "versions": [{"pattern": "([01]|2[.]([0-9]|1[0-6]))(|[-.].*)"}],
    },
    {
        "id": "SECURITY-713",
        "name": "maven-plugin",
        "type": "plugin",
        "url": "https://jenkins.io/security/advisory/2019-07-31/#SECURITY-713",
        "versions": [{"lastVersion": "3.3", "pattern": "(1|2|3[.][0-3])(|[-.].*)"}],
    },
    {
        "id": "SECURITY-1633",
        "name": "gatling",
        "type": "plugin",
        "url": "https://jenkins.io/security/advisory/2020-04-07/#SECURITY-1633",
        "versions": [{"lastVersion": "1.2.7", "pattern": "(1[.][0-2])(|[.-].+)"}],
    },
    {
        "id": "core-2_44",
        "name": "core",
        "type": "core",
        "url": "https://jenkins.io/security/advisory/2017-02-01/",
        "versions": [{"lastVersion": "2.43", "pattern": "(1[.].*|2[.]\\d|2[.][123]\\d|2[.]4[0123])(|[-].*)"}],
    },
    {
        "id": "SECURITY-2931",
        "name": "email-ext",
        "type": "plugin",
        "url": "https://www.jenkins.io/security/advisory/2023-02-15/#SECURITY-2931",
        "versions": [
            {
                "lastVersion": "2.93",
                "pattern": "(2[.]1[012345689]|2[.]2[01245789]|2[.]3[0-9]|2[.]4[0-7]|2[.]5[0-9]|2[.]6[012345689]"
                "|2[.]7[1-9]|2[.]8[0-8]|2[.]89[.]1|2[.]9[0-2])(|[.-].+)|(2[.]89|2[.]93)",
            }
        ],
    },
    {
        "id": "SECURITY-3588",
        "name": "gatling",
        "type": "plugin",
        "url": "https://www.jenkins.io/security/advisory/2025-06-06/#SECURITY-3588",
        "versions": [
            {"firstVersion": "136.vb_9009b_3d33a_e", "lastVersion": "136.vb_9009b_3d33a_e", "pattern": "(136)(|[.-].+)"}
        ],
    },
    {
        "id": "SECURITY-3705",
        "name": "email-ext",
        "type": "plugin",
        "url": "https://www.jenkins.io/security/advisory/2026-05-27/#SECURITY-3705",
        "versions": [
            {
                "lastVersion": "1933.v45cec755423f",
                "pattern": "(1806|1814|184[49]|185[15]|186[16]|1876|191[16]|192[25]|1933[.]v45cec755423f|2)(|[.-].+)",
            }
        ],
    },
]

# Installed plugins: email-ext and vsphere-cloud are affected, maven-plugin
# and gatling are not, and an inactive plugin is never reported.
PLUGINS: list[dict[str, Any]] = [
    {"shortName": "email-ext", "longName": "Email Extension Plugin", "version": "2.57", "active": True},
    {"shortName": "gatling", "longName": "Gatling Jenkins Plugin", "version": "1.3.0", "active": True},
    {"shortName": "maven-plugin", "longName": "Maven Integration plugin", "version": "3.28", "active": True},
    {"shortName": "vsphere-cloud", "longName": "vSphere Plugin", "version": "2.16", "active": True},
    {"shortName": "inactive", "longName": "Inactive Plugin", "version": "1.0", "active": False},
]
INACTIVE_WARNING = {"name": "inactive", "type": "plugin", "url": "https://example.org/inactive", "versions": []}

ADVISORIES = (
    "email-ext:2.57\temail-ext:2.57\thttps://jenkins.io/security/advisory/2017-03-20/\n"
    "email-ext:2.57.1\temail-ext:2.57\thttps://jenkins.io/security/advisory/2017-04-10/\n"
    "email-ext:2.93\temail-ext:2.57\thttps://www.jenkins.io/security/advisory/2023-02-15/#SECURITY-2931\n"
    "email-ext:1933.v45cec755423f\temail-ext:2.57\thttps://www.jenkins.io/security/advisory/2026-05-27/#SECURITY-3705\n"
    "vsphere-cloud:unknown\tvsphere-cloud:2.16\thttps://jenkins.io/security/advisory/2018-03-26/#SECURITY-504\n"
)


def _serve_plugins() -> None:
    responses.add(responses.GET, f"{URL}/pluginManager/api/json?depth=2", json={"plugins": PLUGINS})


def _serve_feed(**answer: Any) -> None:
    """Answer the advisory feed, at the old plain-HTTP address and the HTTPS one, with *answer*."""
    for url in (FEED, OLD_FEED):
        responses.add(responses.GET, url, **answer)


def _feed_requests() -> list[str]:
    return [str(call.request.url) for call in responses.calls if "update-center" in str(call.request.url)]


@FRONT_ENDS
def test_plugins_sec_reports_every_applicable_advisory(run: Run, server: jenkins.Jenkins) -> None:
    _serve_plugins()
    _serve_feed(json={"warnings": [*WARNINGS, INACTIVE_WARNING]})

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 0, result.output
    assert result.stdout == ADVISORIES


# An advisory with two version ranges, SECURITY-441, copied from the update
# center; one whose ranges overlap; and two that name no range.
MULTI_RANGE: dict[str, Any] = {
    "id": "SECURITY-441",
    "name": "pipeline-maven",
    "type": "plugin",
    "url": "https://jenkins.io/security/advisory/2017-03-09/",
    "versions": [
        {"lastVersion": "0.6", "pattern": "0[.][123456](|[.-].*)"},
        {"lastVersion": "2.0-beta-5", "pattern": "2[.]0[-]beta[-][345](|[.-].*)"},
    ],
}
OVERLAPPING: dict[str, Any] = {
    "id": "overlapping",
    "name": "pipeline-maven",
    "type": "plugin",
    "url": "https://example.org/overlapping",
    "versions": [{"lastVersion": "1.5", "pattern": "1[.].*"}, {"lastVersion": "1.9", "pattern": "1[.][0-9]"}],
}
EMPTY_VERSIONS: dict[str, Any] = {
    "id": "empty-versions",
    "name": "pipeline-maven",
    "type": "plugin",
    "url": "https://example.org/empty-versions",
    "versions": [],
}
NO_VERSIONS: dict[str, Any] = {
    "id": "no-versions",
    "name": "pipeline-maven",
    "type": "plugin",
    "url": "https://example.org/no-versions",
}


def _serve_pipeline_maven(installed: str, warning: dict[str, Any]) -> None:
    """Serve pipeline-maven *installed* as the one active plugin, and *warning* as the feed."""
    plugin = {"shortName": "pipeline-maven", "longName": "Pipeline Maven Integration", "version": installed}
    responses.add(
        responses.GET, f"{URL}/pluginManager/api/json?depth=2", json={"plugins": [{**plugin, "active": True}]}
    )
    _serve_feed(json={"warnings": [warning]})


def _line(last: str, installed: str, warning: dict[str, Any]) -> str:
    return f"pipeline-maven:{last}\tpipeline-maven:{installed}\t{warning['url']}\n"


@FRONT_ENDS
@pytest.mark.parametrize(
    ("installed", "warning", "stdout"),
    [
        ("0.5", MULTI_RANGE, _line("0.6", "0.5", MULTI_RANGE)),
        ("1.0", MULTI_RANGE, ""),
        ("1.2", OVERLAPPING, _line("1.5", "1.2", OVERLAPPING)),
        ("1.2", EMPTY_VERSIONS, _line("unknown", "1.2", EMPTY_VERSIONS)),
        ("1.2", NO_VERSIONS, _line("unknown", "1.2", NO_VERSIONS)),
    ],
    ids=["first-range", "outside-ranges", "overlapping-ranges", "empty-versions", "no-versions"],
)
def test_plugins_sec_reports_matching_range(
    run: Run, server: jenkins.Jenkins, installed: str, warning: dict[str, Any], stdout: str
) -> None:
    """Each applicable advisory is printed once, with its matching range's last version or ``unknown``."""
    _serve_pipeline_maven(installed, warning)

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 0, result.output
    assert result.stdout == stdout


@FRONT_ENDS
def test_plugins_sec_reports_last_range(run: Run, server: jenkins.Jenkins) -> None:
    """A version in an advisory's last range is reported with that range's last version."""
    _serve_pipeline_maven("2.0-beta-4", MULTI_RANGE)

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 0, result.output
    assert result.stdout == _line("2.0-beta-5", "2.0-beta-4", MULTI_RANGE)


@FRONT_ENDS
def test_plugins_sec_fetches_feed_over_https(run: Run, server: jenkins.Jenkins) -> None:
    _serve_plugins()
    _serve_feed(json={"warnings": WARNINGS})

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 0, result.output
    assert _feed_requests() == [FEED]


@FRONT_ENDS
def test_plugins_sec_refuses_redirect_off_https(
    run: Run, server: jenkins.Jenkins, caplog: pytest.LogCaptureFixture
) -> None:
    _serve_plugins()
    mirror = "http://mirror.example.org/update-center.actual.json"
    _serve_feed(status=302, headers={"Location": mirror})
    responses.add(responses.GET, mirror, json={"warnings": WARNINGS})

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "not HTTPS" in caplog.text
    assert result.stdout == ""
    assert mirror not in _feed_requests()


@FRONT_ENDS
def test_plugins_sec_follows_redirects_over_https(run: Run, server: jenkins.Jenkins) -> None:
    _serve_plugins()
    mirror = "https://mirror.example.org/current/update-center.actual.json"
    _serve_feed(status=301, headers={"Location": mirror})
    responses.add(responses.GET, mirror, json={"warnings": [*WARNINGS, INACTIVE_WARNING]})

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 0, result.output
    assert result.stdout == ADVISORIES
    assert mirror in _feed_requests()


@FRONT_ENDS
@pytest.mark.parametrize(
    "answer",
    [
        {"status": 503, "body": ""},
        {"body": "<html>maintenance</html>"},
        {"json": {"core": {}}},
        {
            "json": {
                "warnings": [{"name": "email-ext", "type": "plugin", "url": "https://example.org", "versions": "all"}]
            }
        },
        {"json": {"warnings": [{"type": "plugin", "url": "https://example.org", "versions": []}]}},
        {
            "json": {
                "warnings": [
                    {
                        "name": "email-ext",
                        "type": "plugin",
                        "url": "https://example.org",
                        "versions": [{"lastVersion": "2.57", "pattern": None}],
                    }
                ]
            }
        },
    ],
    ids=["unavailable", "not-json", "no-warnings", "versions-not-list", "no-name", "no-pattern"],
)
def test_plugins_sec_unusable_feed_exits_one(
    run: Run, server: jenkins.Jenkins, caplog: pytest.LogCaptureFixture, answer: dict[str, Any]
) -> None:
    _serve_plugins()
    _serve_feed(**answer)

    result = run(server, ["plugins", "sec"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert FEED in caplog.text
    assert result.stdout == ""
