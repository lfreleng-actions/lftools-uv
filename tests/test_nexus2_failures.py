# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for Nexus2 commands that reported success after Nexus refused them.

Every ``nexus2`` create, delete and list command must exit 1 when Nexus
answers with an unexpected status, logging Nexus's response body, in
both the Click and the Typer front-ends. A list must also exit 1 when a
200 response lacks the ``{"data": [...]}`` envelope. The success paths
must keep their output and exit 0.

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
from lftools_uv.typer_apps.nexus2 import nexus2_app

FQDN = "nexus.example.org"

_SETTINGS = {
    "username": "user",
    "password": "pass",
    "endpoint": "https://nexus.example.org/",
}

NEXUS_ERROR = {"errors": [{"id": "*", "msg": "Nexus refused it"}]}
NEXUS_ERROR_TEXT = "Nexus refused it"
HTML_ERROR_TEXT = "Internal proxy failure page"
HTML_ERROR = f"<html><body><h1>{HTML_ERROR_TEXT}</h1></body></html>"

CREATES = {
    "privilege": (["privilege", "create", "p1", "desc", "repo1"], "Privilege successfully created."),
    "repo": (["repo", "create", "hosted", "r1", "Repo 1", "maven2", "RELEASE"], "Repo successfully created."),
    "role": (["role", "create", "role1", "Role 1"], "Role successfully created."),
    "user": (["user", "add", "u1", "First", "Last", "u1@example.org", "role1"], "User successfully created."),
}

DELETES = {
    "privilege": (["privilege", "delete", "p1"], "Privilege successfully deleted."),
    "role": (["role", "delete", "role1"], "Role successfully deleted."),
    "user": (["user", "delete", "u1"], "User successfully deleted."),
}

REPO_DELETE = (["repo", "delete", "r1"], "Repo successfully deleted.")

LISTS = {
    "privilege": (["privilege", "list"], {"name": "priv-one", "id": "p1"}, "priv-one"),
    "repo": (
        ["repo", "list"],
        {"name": "repo-one", "repoType": "hosted", "provider": "maven2", "id": "r1"},
        "repo-one",
    ),
    "role": (["role", "list"], {"id": "role1", "name": "role-one", "roles": [], "privileges": []}, "role-one"),
    "user": (
        ["user", "list"],
        {
            "userId": "user-one",
            "firstName": "First",
            "lastName": "Last",
            "status": "active",
            "roles": [{"roleId": "role1"}],
        },
        "user-one",
    ),
}

XFAIL_841 = pytest.mark.xfail(strict=True, reason="#841: Nexus2 commands exit 0 when Nexus refuses a request")


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, ["nexus2", FQDN, *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(nexus2_app, [FQDN, *args])


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _response(status: int, body: object = None) -> requests.Response:
    """Build a Nexus response: JSON for a dict, HTML for a str, empty for None."""
    response = requests.Response()
    response.status_code = status
    if isinstance(body, str):
        response.headers["Content-Type"] = "text/html"
        response._content = body.encode()
    elif body is None:
        response._content = b""
    else:
        response.headers["Content-Type"] = "application/json"
        response._content = json.dumps(body).encode()
    return response


@pytest.fixture
def nexus_api(monkeypatch: pytest.MonkeyPatch) -> Callable[[requests.Response], list[tuple[str, str]]]:
    """Answer every Nexus request with one response and record each call."""
    calls: list[tuple[str, str]] = []
    answer: dict[str, requests.Response] = {}

    def fake_request(_session, method, url, **_kwargs):
        calls.append((method, url))
        return answer["response"]

    def install(response: requests.Response) -> list[tuple[str, str]]:
        answer["response"] = response
        return calls

    monkeypatch.setattr("lftools_uv.api.endpoints.nexus2.config.get_setting", lambda _s, o: _SETTINGS[o])
    monkeypatch.setattr(requests.Session, "request", fake_request)
    return install


# ---------------------------------------------------------------------------
# create
# ---------------------------------------------------------------------------


@XFAIL_841
@FRONT_ENDS
@pytest.mark.parametrize("kind", list(CREATES))
def test_create_refused_exits_1(run, nexus_api, caplog, kind):
    """A create Nexus refuses fails, logging Nexus's message."""
    caplog.set_level(logging.ERROR)
    args, _message = CREATES[kind]
    nexus_api(_response(400, NEXUS_ERROR))

    result = run(args)

    assert result.exit_code == 1
    assert "successfully" not in result.output
    assert NEXUS_ERROR_TEXT in caplog.text


@FRONT_ENDS
@pytest.mark.parametrize("kind", list(CREATES))
def test_create_succeeds(run, nexus_api, kind):
    """A create Nexus accepts prints its success message and exits 0."""
    args, message = CREATES[kind]
    calls = nexus_api(_response(201, {"data": {"id": "created"}}))

    result = run(args)

    assert result.exit_code == 0
    assert message in result.output
    assert [method for method, _url in calls] == ["POST"]


# ---------------------------------------------------------------------------
# delete
# ---------------------------------------------------------------------------


@XFAIL_841
@FRONT_ENDS
@pytest.mark.parametrize("kind", list(DELETES))
@pytest.mark.parametrize(
    ("status", "body", "text"),
    [(404, NEXUS_ERROR, NEXUS_ERROR_TEXT), (500, HTML_ERROR, HTML_ERROR_TEXT)],
    ids=["404", "500"],
)
def test_delete_refused_exits_1(run, nexus_api, caplog, kind, status, body, text):
    """A delete Nexus refuses fails, logging Nexus's response body."""
    caplog.set_level(logging.ERROR)
    args, _message = DELETES[kind]
    nexus_api(_response(status, body))

    result = run(args)

    assert result.exit_code == 1
    assert "successfully" not in result.output
    assert text in caplog.text


@FRONT_ENDS
@pytest.mark.parametrize("kind", [*DELETES, "repo"])
def test_delete_succeeds(run, nexus_api, kind):
    """A delete Nexus accepts with 204 prints its success message and exits 0."""
    args, message = REPO_DELETE if kind == "repo" else DELETES[kind]
    calls = nexus_api(_response(204))

    result = run(args)

    assert result.exit_code == 0
    assert message in result.output
    assert [method for method, _url in calls] == ["DELETE"]


@FRONT_ENDS
def test_repo_delete_refused_exits_1(run, nexus_api):
    """A repo delete Nexus refuses already fails, and still does."""
    args, _message = REPO_DELETE
    nexus_api(_response(500, HTML_ERROR))

    result = run(args)

    assert result.exit_code == 1
    assert "successfully" not in result.output


# ---------------------------------------------------------------------------
# list
# ---------------------------------------------------------------------------


@XFAIL_841
@FRONT_ENDS
@pytest.mark.parametrize("kind", list(LISTS))
@pytest.mark.parametrize("status", [401, 500])
def test_list_refused_exits_1(run, nexus_api, caplog, kind, status):
    """A list Nexus refuses fails instead of printing an empty table."""
    caplog.set_level(logging.ERROR)
    args, _item, _shown = LISTS[kind]
    nexus_api(_response(status, HTML_ERROR))

    result = run(args)

    assert result.exit_code == 1
    assert HTML_ERROR_TEXT in caplog.text


@XFAIL_841
@FRONT_ENDS
@pytest.mark.parametrize("kind", list(LISTS))
def test_list_without_envelope_exits_1(run, nexus_api, kind):
    """A 200 list response without the ``data`` envelope fails."""
    args, _item, _shown = LISTS[kind]
    nexus_api(_response(200, {"unexpected": True}))

    result = run(args)

    assert result.exit_code == 1


@FRONT_ENDS
@pytest.mark.parametrize("kind", list(LISTS))
def test_list_prints_items(run, nexus_api, kind):
    """A list Nexus answers prints each item and exits 0."""
    args, item, shown = LISTS[kind]
    nexus_api(_response(200, {"data": [item]}))

    result = run(args)

    assert result.exit_code == 0
    assert shown in result.output


@FRONT_ENDS
@pytest.mark.parametrize("kind", list(LISTS))
def test_list_empty_exits_0(run, nexus_api, kind):
    """An empty ``data`` list is a valid, empty result."""
    args, _item, _shown = LISTS[kind]
    nexus_api(_response(200, {"data": []}))

    result = run(args)

    assert result.exit_code == 0
