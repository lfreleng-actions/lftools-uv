# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for rtd list paging, subproject aliases and an empty ACTIVE.

``project-list``, ``subproject-list``, ``project-build-list`` and
``project-version-list`` must read every page Read the Docs returns,
and fail when a later page fails. ``subproject-details`` and
``subproject-delete`` must address a relationship by its alias, which
Read the Docs keys those routes by. ``project-version-update`` must
refuse an empty or blank ACTIVE rather than read it as false.

Every HTTP call is mocked with ``responses``: no test reaches Read the
Docs or reads the user's configuration.
"""

import configparser
import json
from collections.abc import Callable

import pytest
import responses
from click.testing import CliRunner as ClickRunner
from responses import matchers
from typer.testing import CliRunner as TyperRunner

from lftools_uv.api.endpoints.readthedocs import ReadTheDocs, ReadTheDocsAPIError
from lftools_uv.cli import cli
from lftools_uv.typer_apps.rtd import rtd_app

ENDPOINT = "https://readthedocs.org/api/v3/"
CREDS = {"authtype": "token", "endpoint": ENDPOINT, "token": "xyz"}
_RTD_SETTINGS = {"token": "xyz", "endpoint": ENDPOINT}

Runner = Callable[[list[str]], tuple[int, str]]


def _run_click(args: list[str]) -> tuple[int, str]:
    result = ClickRunner().invoke(cli, ["rtd", *args], obj={})
    return result.exit_code, result.stdout


def _run_typer(args: list[str]) -> tuple[int, str]:
    result = TyperRunner().invoke(rtd_app, args)
    return result.exit_code, result.stdout


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _fake_get_setting(section: str, option: str | None = None) -> str:
    if section != "rtd":
        raise configparser.NoSectionError(section)
    return _RTD_SETTINGS[str(option)]


@pytest.fixture
def settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """Answer configuration reads without touching the user's files."""
    monkeypatch.setattr("lftools_uv.config.get_setting", _fake_get_setting)


def _rtd() -> ReadTheDocs:
    return ReadTheDocs(creds=CREDS)


def _get_page(path: str, query: str, results: list[object], next_query: str | None) -> None:
    """Register one page of a list, answering only its exact query."""
    next_url = f"{ENDPOINT}{path}?{next_query}" if next_query is not None else None
    responses.add(
        responses.GET,
        url=f"{ENDPOINT}{path}",
        json={"count": None, "next": next_url, "results": results},
        status=200,
        match=[matchers.query_string_matcher(query)],
    )


def _calls(method: str, path: str) -> list[responses.Call]:
    return [call for call in responses.calls if call.request.method == method and call.request.url == ENDPOINT + path]


# ---------------------------------------------------------------------------
# Paging: #966
# ---------------------------------------------------------------------------

BUILDS_PATH = "projects/p/builds/"


def _register_build_pages() -> None:
    _get_page(
        BUILDS_PATH,
        "running=True",
        [{"id": i} for i in range(1, 11)],
        "limit=10&offset=10&running=True",
    )
    _get_page(BUILDS_PATH, "limit=10&offset=10&running=True", [{"id": i} for i in range(11, 14)], None)


@responses.activate
def test_project_build_list_reads_every_page():
    _register_build_pages()
    builds = _rtd().project_build_list("p")
    assert [b["id"] for b in builds] == list(range(1, 14))


@responses.activate
def test_project_build_list_single_page():
    _get_page(BUILDS_PATH, "running=True", [{"id": 1}, {"id": 2}], None)
    builds = _rtd().project_build_list("p")
    assert [b["id"] for b in builds] == [1, 2]


@responses.activate
def test_project_list_reads_every_page():
    _get_page("projects/", "limit=999", [{"slug": "a"}, {"slug": "b"}], "limit=999&offset=999")
    _get_page("projects/", "limit=999&offset=999", [{"slug": "c"}, {"slug": "d"}], None)
    assert _rtd().project_list() == ["a", "b", "c", "d"]


@responses.activate
def test_subproject_list_reads_every_page():
    path = "projects/parent/subprojects/"
    _get_page(path, "limit=999", [{"child": {"slug": "one"}}], "limit=999&offset=999")
    _get_page(path, "limit=999&offset=999", [{"child": {"slug": "two"}}], None)
    assert _rtd().subproject_list("parent") == ["one", "two"]


@responses.activate
def test_project_version_list_reads_every_page():
    path = "projects/p/versions/"
    _get_page(path, "active=True", [{"slug": "latest"}], "active=True&limit=10&offset=10")
    _get_page(path, "active=True&limit=10&offset=10", [{"slug": "stable"}], None)
    assert _rtd().project_version_list("p") == ["latest", "stable"]


@responses.activate
def test_project_build_list_fails_on_failed_page():
    _get_page(BUILDS_PATH, "running=True", [{"id": 1}], "limit=10&offset=10&running=True")
    responses.add(
        responses.GET,
        url=f"{ENDPOINT}{BUILDS_PATH}",
        json={"detail": "Server error"},
        status=500,
        match=[matchers.query_string_matcher("limit=10&offset=10&running=True")],
    )
    with pytest.raises(ReadTheDocsAPIError):
        _ = _rtd().project_build_list("p")


@pytest.mark.parametrize(
    ("run", "args", "key"),
    [
        (_run_click, ["project-build-list", "p"], "results"),
        (_run_typer, ["project-build-list", "p", "--json"], "builds"),
    ],
    ids=["click", "typer"],
)
@responses.activate
def test_project_build_list_command_reads_every_page(settings, run, args, key):
    _register_build_pages()
    exit_code, stdout = run(args)
    assert exit_code == 0
    payload = json.loads(stdout)
    assert payload["count"] == 13
    assert [b["id"] for b in payload[key]] == list(range(1, 14))


# ---------------------------------------------------------------------------
# Subproject aliases: #967
# ---------------------------------------------------------------------------

SUBPROJECTS_PATH = "projects/onap/subprojects/"


def _register_subprojects(*entries: tuple[str, str]) -> None:
    """Register the subproject list of ``onap`` as (child, alias) pairs."""
    results: list[object] = [{"child": {"slug": child}, "alias": alias} for child, alias in entries]
    _get_page(SUBPROJECTS_PATH, "limit=999", results, None)


def _register_delete(alias: str) -> None:
    responses.add(responses.DELETE, url=f"{ENDPOINT}{SUBPROJECTS_PATH}{alias}/", status=204)


@pytest.mark.xfail(strict=True, reason="#967: subproject-delete uses the child slug, not the alias")
@FRONT_ENDS
@responses.activate
def test_subproject_delete_uses_alias(settings, run):
    _register_subprojects(("onap-cps", "cps"))
    _register_delete("cps")
    exit_code, _ = run(["subproject-delete", "onap", "onap-cps"])
    assert exit_code == 0
    assert len(_calls("DELETE", f"{SUBPROJECTS_PATH}cps/")) == 1


@pytest.mark.xfail(strict=True, reason="#967: subproject-delete removes another relationship")
@FRONT_ENDS
@responses.activate
def test_subproject_delete_spares_other_relationship(settings, run):
    _register_subprojects(("onap-cps", "cps"), ("onap-cps-old", "onap-cps"))
    _register_delete("cps")
    _register_delete("onap-cps")
    exit_code, _ = run(["subproject-delete", "onap", "onap-cps"])
    assert exit_code == 0
    assert len(_calls("DELETE", f"{SUBPROJECTS_PATH}cps/")) == 1
    assert _calls("DELETE", f"{SUBPROJECTS_PATH}onap-cps/") == []


@pytest.mark.xfail(strict=True, reason="#967: subproject-delete matches an alias, not the child")
@FRONT_ENDS
@responses.activate
def test_subproject_delete_refuses_non_child(settings, run):
    _register_subprojects(("onap-cps-old", "onap-cps"))
    _register_delete("onap-cps")
    exit_code, _ = run(["subproject-delete", "onap", "onap-cps"])
    assert exit_code == 1
    assert _calls("DELETE", f"{SUBPROJECTS_PATH}onap-cps/") == []


@FRONT_ENDS
@responses.activate
def test_subproject_delete_alias_equal_to_slug(settings, run):
    _register_subprojects(("onap-cps", "onap-cps"))
    _register_delete("onap-cps")
    exit_code, _ = run(["subproject-delete", "onap", "onap-cps"])
    assert exit_code == 0
    assert len(_calls("DELETE", f"{SUBPROJECTS_PATH}onap-cps/")) == 1


@pytest.mark.xfail(strict=True, reason="#967: subproject-details uses the child slug, not the alias")
@FRONT_ENDS
@responses.activate
def test_subproject_details_uses_alias(settings, run):
    _register_subprojects(("onap-cps", "cps"))
    responses.add(
        responses.GET,
        url=f"{ENDPOINT}{SUBPROJECTS_PATH}cps/",
        json={"child": {"slug": "onap-cps"}, "alias": "cps"},
        status=200,
    )
    exit_code, stdout = run(["subproject-details", "onap", "onap-cps"])
    assert exit_code == 0
    assert "onap-cps" in stdout


# ---------------------------------------------------------------------------
# Empty ACTIVE: #968
# ---------------------------------------------------------------------------

VERSION_PATH = "projects/p/versions/v/"


@pytest.mark.xfail(strict=True, reason="#968: an empty ACTIVE reads as false")
@pytest.mark.parametrize("value", ["", " "], ids=["empty", "blank"])
@FRONT_ENDS
@responses.activate
def test_project_version_update_refuses_empty_active(settings, run, value):
    responses.add(responses.PATCH, url=f"{ENDPOINT}{VERSION_PATH}", json={}, status=204)
    exit_code, _ = run(["project-version-update", "p", "v", value])
    assert exit_code == 2
    assert _calls("PATCH", VERSION_PATH) == []


@pytest.mark.parametrize(
    ("value", "expected"),
    [("true", True), ("False", False), ("yes", True), ("0", False)],
)
@FRONT_ENDS
@responses.activate
def test_project_version_update_converts_active(settings, run, value, expected):
    responses.add(responses.PATCH, url=f"{ENDPOINT}{VERSION_PATH}", status=204)
    exit_code, _ = run(["project-version-update", "p", "v", value])
    assert exit_code == 0
    patches = _calls("PATCH", VERSION_PATH)
    assert len(patches) == 1
    body = patches[0].request.body
    assert isinstance(body, (str, bytes))
    assert json.loads(body) == {"active": expected}
