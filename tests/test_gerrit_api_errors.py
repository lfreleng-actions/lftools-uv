# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for Gerrit commands that reported success after an HTTP error.

``gerrit createproject``, ``gerrit create-saml-group`` and
``gerrit addfile`` must exit 1 when Gerrit refuses a request, logging
Gerrit's error text, in both the Click and the Typer front-ends.
``addfile`` must stop at the first refused call. The success paths must
keep exiting 0.

Every HTTP call is mocked: no test reaches a Gerrit server.
"""

import json
import logging
from collections.abc import Callable
from pathlib import Path

import pytest
import requests
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.typer_apps.gerrit import gerrit_app

FQDN = "gerrit.example.org"
PROJECT = "foo/bar"
PROJECT_ENCODED = "foo%2Fbar"
ENDPOINT = "https://gerrit.example.org/a/"

_SETTINGS = {
    "username": "user",
    "password": "pass",
    "endpoint": ENDPOINT,
    "sob": "Automation <automation@example.org>",
}

XFAIL_847 = pytest.mark.xfail(strict=True, reason="#847: Gerrit commands exit 0 when Gerrit refuses a request")

# (method, URL fragment, response); the first matching route answers.
Routes = list[tuple[str, str, requests.Response]]


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, ["gerrit", *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(gerrit_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _response(status: int, body: object = None) -> requests.Response:
    """Build a Gerrit response: plain text for a str, guarded JSON otherwise."""
    response = requests.Response()
    response.status_code = status
    if isinstance(body, str):
        response.headers["Content-Type"] = "text/plain"
        response._content = body.encode()
    elif body is None:
        response._content = b""
    else:
        response.headers["Content-Type"] = "application/json"
        response._content = (")]}'\n" + json.dumps(body)).encode()
    return response


@pytest.fixture
def gerrit_api(monkeypatch: pytest.MonkeyPatch) -> Callable[[Routes], list[tuple[str, str]]]:
    """Route Gerrit REST calls through a per-test table and record each one."""
    calls: list[tuple[str, str]] = []
    table: dict[str, Routes] = {}

    def fake_request(_session, method, url, **_kwargs):
        calls.append((method, url))
        for route_method, fragment, response in table["routes"]:
            if method == route_method and fragment in url:
                return response
        return _response(404, f"no route for {method} {url}")

    def install(routes: Routes) -> list[tuple[str, str]]:
        table["routes"] = routes
        return calls

    monkeypatch.setattr("lftools_uv.api.endpoints.gerrit.config.get_setting", lambda _s, o: _SETTINGS[o])
    monkeypatch.setattr(requests.Session, "request", fake_request)
    return install


# ---------------------------------------------------------------------------
# createproject
# ---------------------------------------------------------------------------

CREATEPROJECT = ["createproject", FQDN, PROJECT, "ldap-grp", "--description", "demo"]


def _project_routes(existing: dict[str, object], put: requests.Response) -> Routes:
    return [
        ("GET", "projects/?query=name:", _response(200, existing)),
        ("PUT", f"projects/{PROJECT_ENCODED}", put),
    ]


@XFAIL_847
@FRONT_ENDS
def test_createproject_refused_exits_1(run, gerrit_api, caplog):
    """A project Gerrit refuses to create fails, logging Gerrit's message."""
    caplog.set_level(logging.ERROR)
    gerrit_api(_project_routes({}, _response(403, "administrate server not permitted")))

    result = run(CREATEPROJECT)

    assert result.exit_code == 1
    assert "administrate server not permitted" in caplog.text
    assert "Response [" not in result.output


@FRONT_ENDS
def test_createproject_created_exits_0(run, gerrit_api):
    """A project Gerrit creates exits 0."""
    calls = gerrit_api(_project_routes({}, _response(201, {"id": PROJECT_ENCODED, "name": PROJECT})))

    result = run(CREATEPROJECT)

    assert result.exit_code == 0
    assert ("PUT", f"{ENDPOINT}projects/{PROJECT_ENCODED}") in calls


@FRONT_ENDS
def test_createproject_existing_exits_1_without_put(run, gerrit_api):
    """An existing project fails without sending the create request."""
    calls = gerrit_api(_project_routes({PROJECT: {"id": PROJECT_ENCODED}}, _response(201, {})))

    result = run(CREATEPROJECT)

    assert result.exit_code == 1
    assert [method for method, _url in calls] == ["GET"]


# ---------------------------------------------------------------------------
# create-saml-group
# ---------------------------------------------------------------------------


@XFAIL_847
@FRONT_ENDS
@pytest.mark.parametrize(
    ("status", "text"),
    [(401, "Unauthorized"), (409, "group 'saml/grp' already exists")],
    ids=["401", "409"],
)
def test_create_saml_group_refused_exits_1(run, gerrit_api, caplog, status, text):
    """A group Gerrit refuses to create, or already has, fails."""
    caplog.set_level(logging.ERROR)
    gerrit_api([("PUT", "groups/saml%2Fgrp", _response(status, text))])

    result = run(["create-saml-group", FQDN, "grp"])

    assert result.exit_code == 1
    assert text in caplog.text


@FRONT_ENDS
def test_create_saml_group_created_exits_0(run, gerrit_api):
    """A group Gerrit creates exits 0."""
    gerrit_api([("PUT", "groups/saml%2Fgrp", _response(201, {"name": "saml/grp"}))])

    result = run(["create-saml-group", FQDN, "grp"])

    assert result.exit_code == 0


# ---------------------------------------------------------------------------
# addfile
# ---------------------------------------------------------------------------


def _addfile_args(tmp_path: Path) -> list[str]:
    info = tmp_path / "INFO.yaml"
    info.write_text("project: foo/bar\n")
    return ["addfile", FQDN, PROJECT, str(info)]


def _addfile_routes(
    create: requests.Response,
    edit: requests.Response,
    publish: requests.Response,
) -> Routes:
    # Most specific first: the publish URL also contains "changes/".
    return [
        ("POST", "changes/c1/edit:publish", publish),
        ("PUT", "changes/c1/edit/INFO.yaml", edit),
        ("POST", "changes/", create),
    ]


@XFAIL_847
@FRONT_ENDS
def test_addfile_create_refused_logs_gerrit_text(run, gerrit_api, caplog, tmp_path):
    """A refused change creation fails with Gerrit's message and goes no further."""
    caplog.set_level(logging.ERROR)
    calls = gerrit_api(
        _addfile_routes(_response(403, "create change not permitted"), _response(204), _response(204)),
    )

    result = run(_addfile_args(tmp_path))

    assert result.exit_code == 1
    assert "create change not permitted" in caplog.text
    assert len(calls) == 1


@XFAIL_847
@FRONT_ENDS
def test_addfile_edit_refused_does_not_publish(run, gerrit_api, caplog, tmp_path):
    """A refused upload fails and the change is not published."""
    caplog.set_level(logging.ERROR)
    calls = gerrit_api(
        _addfile_routes(_response(201, {"id": "c1"}), _response(403, "edit not permitted"), _response(204)),
    )

    result = run(_addfile_args(tmp_path))

    assert result.exit_code == 1
    assert "edit not permitted" in caplog.text
    assert not any(url.endswith("edit:publish") for _method, url in calls)


@XFAIL_847
@FRONT_ENDS
def test_addfile_publish_refused_exits_1(run, gerrit_api, caplog, tmp_path):
    """A refused publish fails, logging Gerrit's message."""
    caplog.set_level(logging.ERROR)
    gerrit_api(
        _addfile_routes(_response(201, {"id": "c1"}), _response(204), _response(409, "change is closed")),
    )

    result = run(_addfile_args(tmp_path))

    assert result.exit_code == 1
    assert "change is closed" in caplog.text


@FRONT_ENDS
def test_addfile_succeeds(run, gerrit_api, tmp_path):
    """Create, upload and publish all accepted exits 0 after three requests."""
    calls = gerrit_api(_addfile_routes(_response(201, {"id": "c1"}), _response(204), _response(204)))

    result = run(_addfile_args(tmp_path))

    assert result.exit_code == 0
    assert calls == [
        ("POST", f"{ENDPOINT}changes/"),
        ("PUT", f"{ENDPOINT}changes/c1/edit/INFO.yaml"),
        ("POST", f"{ENDPOINT}changes/c1/edit:publish"),
    ]
