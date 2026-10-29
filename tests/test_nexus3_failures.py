# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for Nexus3 commands that hid paging, uploads and failures.

``asset list``, ``asset search`` and ``task list`` must read every page
Nexus returns and exit 1 on a refused or malformed page. ``script
create`` must upload the named file's text. The script, tag, role and
user commands must exit 1 when Nexus answers with a status other than
the one its REST API documents. Every case runs through both the Click
and the Typer front-ends, and the success paths keep their output.

Every HTTP call is mocked: no test reaches a Nexus server.
"""

import json
import logging
from collections.abc import Callable

import pytest
import requests
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.typer_apps.nexus3 import nexus3_app

FQDN = "nexus3.example.org"
ENDPOINT = "https://nexus3.example.org/"

_SETTINGS = {
    "username": "user",
    "password": "pass",
    "endpoint": ENDPOINT,
}

NEXUS_ERROR_TEXT = "Internal error"
NEXUS_ERROR = {"message": NEXUS_ERROR_TEXT}
TOKEN = "a+b/c="
ENCODED_TOKEN = "a%2Bb%2Fc%3D"
SCRIPT_TEXT = 'log.info("cleanup")\n'

Call = tuple[str, str, object]

# Each command with the status Nexus documents for it, the body it
# answers with, the text it then prints, and an undocumented status.
WRITES = {
    "script-update": (["script", "update", "cleanup", "x = 1"], 204, None, "Successfully updated cleanup", 200),
    "script-delete": (["script", "delete", "cleanup"], 204, None, "Successfully deleted cleanup", 200),
    "script-read": (["script", "read", "cleanup"], 200, {"name": "cleanup"}, "cleanup", 204),
    "script-run": (["script", "run", "cleanup"], 200, {"result": "ran-ok"}, "ran-ok", 204),
    "tag-add": (["tag", "add", "t1"], 200, {"name": "t1"}, "Tag t1 successfully added.", 204),
    "tag-delete": (["tag", "delete", "t1"], 204, None, "Tag t1 successfully deleted.", 200),
    "role-create": (["role", "create", "r1", "Role one", "p1", "r0"], 200, {"id": "r1"}, "Role r1 created", 204),
    "user-create": (
        ["user", "create", "u1", "First", "Last", "u1@example.org", "r1", "s3cret"],
        200,
        {"userId": "u1"},
        "User u1 successfully created with password s3cret",
        204,
    ),
}


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, ["nexus3", FQDN, *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(nexus3_app, [FQDN, *args])


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _response(status: int, body: object = None) -> requests.Response:
    """Build a Nexus response: JSON for a dict, plain text for a str, empty for None."""
    response = requests.Response()
    response.status_code = status
    if isinstance(body, str):
        response.headers["Content-Type"] = "text/plain"
        response._content = body.encode()
    elif body is None:
        response._content = b""
    else:
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(body).encode()
    return response


def _page(paths: list[str], token: str | None) -> requests.Response:
    """Build one page of a Nexus 3 paged listing."""
    return _response(200, {"items": [{"path": path} for path in paths], "continuationToken": token})


@pytest.fixture
def nexus_api(monkeypatch: pytest.MonkeyPatch) -> Callable[..., list[Call]]:
    """Answer Nexus requests from a queue of responses and record each call."""
    calls: list[Call] = []
    queue: list[requests.Response] = []

    def fake_request(_session, method, url, data=None, **_kwargs):
        calls.append((method, url.removeprefix(ENDPOINT), data))
        if not queue:
            pytest.fail(f"Unexpected request: {method} {url}")
        return queue.pop(0)

    def install(*responses: requests.Response) -> list[Call]:
        queue.extend(responses)
        return calls

    monkeypatch.setattr("lftools_uv.api.endpoints.nexus3.config.get_setting", lambda _s, o: _SETTINGS[o])
    monkeypatch.setattr(requests.Session, "request", fake_request)
    return install


# ---------------------------------------------------------------------------
# asset list, asset search and task list: #956
# ---------------------------------------------------------------------------


@FRONT_ENDS
def test_asset_list_single_page(run, nexus_api):
    """A single page lists its assets."""
    nexus_api(_page(["a/1.jar"], None))

    result = run(["asset", "list", "r1"])

    assert result.exit_code == 0
    assert "a/1.jar" in result.output


@FRONT_ENDS
def test_asset_list_reads_every_page(run, nexus_api):
    """Assets on every page are listed, following the encoded token."""
    calls = nexus_api(_page(["a/1.jar", "a/2.jar"], TOKEN), _page(["a/3.jar"], None))

    result = run(["asset", "list", "r1"])

    assert result.exit_code == 0
    for path in ("a/1.jar", "a/2.jar", "a/3.jar"):
        assert path in result.output
    assert [url for _method, url, _data in calls] == [
        "service/rest/v1/assets?repository=r1",
        f"service/rest/v1/assets?repository=r1&continuationToken={ENCODED_TOKEN}",
    ]


@FRONT_ENDS
def test_asset_search_reads_every_page(run, nexus_api):
    """Search results on every page are listed in order."""
    calls = nexus_api(_page(["a/1.jar"], TOKEN), _page(["a/2.jar"], None))

    result = run(["asset", "search", "foo", "r1"])

    assert result.exit_code == 0
    assert result.output.split() == ["a/1.jar", "a/2.jar"]
    assert len(calls) == 2
    assert f"continuationToken={ENCODED_TOKEN}" in calls[1][1]


@FRONT_ENDS
def test_asset_search_details_reads_every_page(run, nexus_api):
    """``--details`` dumps the items from every page as one JSON list."""
    nexus_api(_page(["a/1.jar"], TOKEN), _page(["a/2.jar"], None))

    result = run(["asset", "search", "--details", "foo", "r1"])

    assert result.exit_code == 0
    assert json.loads(result.output) == [{"path": "a/1.jar"}, {"path": "a/2.jar"}]


@FRONT_ENDS
@pytest.mark.parametrize(
    "second_page",
    [_response(500, NEXUS_ERROR), _response(200), _response(200, {"continuationToken": None})],
    ids=["500", "empty", "no-items"],
)
def test_asset_list_bad_follow_up_page_exits_1(run, nexus_api, second_page):
    """A refused or malformed second page fails rather than listing part."""
    calls = nexus_api(_page(["a/1.jar"], TOKEN), second_page)

    result = run(["asset", "list", "r1"])

    assert result.exit_code == 1
    assert len(calls) == 2


@FRONT_ENDS
@pytest.mark.parametrize(
    "args",
    [["asset", "list", "r1"], ["asset", "search", "foo", "r1"], ["task", "list"]],
    ids=["asset-list", "asset-search", "task-list"],
)
def test_list_refused_exits_1(run, nexus_api, caplog, args):
    """A refused first page fails, logging Nexus's message."""
    caplog.set_level(logging.ERROR)
    calls = nexus_api(_response(500, NEXUS_ERROR))

    result = run(args)

    assert result.exit_code == 1
    assert len(calls) == 1
    assert NEXUS_ERROR_TEXT in caplog.text


@FRONT_ENDS
def test_asset_list_empty_repository(run, nexus_api, caplog):
    """An empty repository prints nothing and says so in the log."""
    caplog.set_level(logging.INFO)
    nexus_api(_page([], None))

    result = run(["asset", "list", "r1"])

    assert result.exit_code == 0
    assert result.output == ""
    assert "r1 has no assets" in caplog.text


@FRONT_ENDS
def test_task_list_prints_task(run, nexus_api):
    """A task Nexus returns appears in the table."""
    task = {"name": "task-one", "message": "msg", "currentState": "WAITING", "lastRunResult": "OK"}
    nexus_api(_response(200, {"items": [task], "continuationToken": None}))

    result = run(["task", "list"])

    assert result.exit_code == 0
    assert "task-one" in result.output


# ---------------------------------------------------------------------------
# script create: #957
# ---------------------------------------------------------------------------


@FRONT_ENDS
def test_script_create_uploads_file_text(run, nexus_api, tmp_path):
    """``script create`` sends the file's text as the script content."""
    script = tmp_path / "cleanup.groovy"
    script.write_text(SCRIPT_TEXT, encoding="utf-8")
    calls = nexus_api(_response(204))

    result = run(["script", "create", "cleanup", str(script)])

    assert result.exit_code == 0
    assert "Script cleanup successfully added." in result.output
    assert len(calls) == 1
    method, url, data = calls[0]
    assert (method, url) == ("POST", "service/rest/v1/script")
    assert isinstance(data, bytes)
    assert json.loads(data) == {"name": "cleanup", "content": SCRIPT_TEXT, "type": "groovy"}


@FRONT_ENDS
def test_script_create_missing_file_is_usage_error(run, nexus_api, tmp_path):
    """A missing script file is a usage error, and nothing is sent."""
    calls = nexus_api()

    result = run(["script", "create", "cleanup", str(tmp_path / "missing.groovy")])

    assert result.exit_code == 2
    assert calls == []


@FRONT_ENDS
def test_script_create_succeeds(run, nexus_api, tmp_path):
    """A 204 reports the script as added."""
    script = tmp_path / "cleanup.groovy"
    script.write_text(SCRIPT_TEXT, encoding="utf-8")
    nexus_api(_response(204))

    result = run(["script", "create", "cleanup", str(script)])

    assert result.exit_code == 0
    assert "Script cleanup successfully added." in result.output


# ---------------------------------------------------------------------------
# undocumented statuses: #958
# ---------------------------------------------------------------------------


@FRONT_ENDS
@pytest.mark.parametrize(
    ("status", "body", "text"),
    [(401, None, ""), (404, "Tag not found", "Tag not found"), (500, NEXUS_ERROR, NEXUS_ERROR_TEXT)],
    ids=["401", "404", "500"],
)
def test_tag_show_refused_exits_1(run, nexus_api, caplog, status, body, text):
    """``tag show`` fails when Nexus refuses, logging its response."""
    caplog.set_level(logging.ERROR)
    nexus_api(_response(status, body))

    result = run(["tag", "show", "t1"])

    assert result.exit_code == 1
    assert "{" not in result.output
    assert f"HTTP {status}" in caplog.text
    assert text in caplog.text


@FRONT_ENDS
def test_tag_show_prints_tag(run, nexus_api):
    """``tag show`` prints the tag Nexus returns."""
    nexus_api(_response(200, {"name": "t1"}))

    result = run(["tag", "show", "t1"])

    assert result.exit_code == 0
    assert "t1" in result.output


@FRONT_ENDS
@pytest.mark.parametrize("kind", list(WRITES))
def test_undocumented_status_exits_1(run, nexus_api, kind):
    """A status other than the documented one fails the command."""
    args, _status, _body, _shown, undocumented = WRITES[kind]
    calls = nexus_api(_response(undocumented))

    result = run(args)

    assert result.exit_code == 1
    assert "successfully" not in result.output
    assert len(calls) == 1


@FRONT_ENDS
@pytest.mark.parametrize("kind", list(WRITES))
def test_documented_status_succeeds(run, nexus_api, kind):
    """The documented status keeps the command's output and exits 0."""
    args, status, body, shown, _undocumented = WRITES[kind]
    calls = nexus_api(_response(status, body))

    result = run(args)

    assert result.exit_code == 0
    assert shown in result.output
    assert len(calls) == 1


@FRONT_ENDS
def test_script_create_undocumented_status_exits_1(run, nexus_api, tmp_path):
    """A 200 to a script upload is not the documented 204, so it fails."""
    script = tmp_path / "cleanup.groovy"
    script.write_text(SCRIPT_TEXT, encoding="utf-8")
    nexus_api(_response(200))

    result = run(["script", "create", "cleanup", str(script)])

    assert result.exit_code == 1
    assert "successfully" not in result.output
