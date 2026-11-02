# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``rtd project-update`` field names and Read the Docs request failures.

Read the Docs ignores a field it does not update and still answers 204, so
``project_update`` must refuse unknown fields before sending anything. A
request that fails, say because the server cannot be reached, must reach
the ``rtd`` commands as a Read the Docs error, which they report in one
line, not as a traceback.

``responses`` answers every request, so no test reaches a server.
"""

import pytest
import requests
import responses
from typer.testing import CliRunner

from lftools_uv.api.endpoints.readthedocs import ReadTheDocs, ReadTheDocsError, ReadTheDocsValidationError
from lftools_uv.typer_apps.rtd import rtd_app

ENDPOINT = "https://readthedocs.org/api/v3/"
PROJECT_URL = f"{ENDPOINT}projects/foo/"
BUSINESS_ENDPOINT = "https://readthedocs.com/api/v3/"

# The fields Read the Docs' v3 ProjectUpdateSerializer accepts.
DOCUMENTED_FIELDS = [
    "analytics_code",
    "analytics_disabled",
    "default_branch",
    "default_version",
    "external_builds_enabled",
    "external_builds_privacy_level",
    "homepage",
    "language",
    "name",
    "privacy_level",
    "programming_language",
    "readthedocs_yaml_path",
    "repository",
    "show_version_warning",
    "tags",
    "versioning_scheme",
]


# readthedocs.org does not allow private repositories, so it ignores these.
PRIVACY_FIELDS = ["external_builds_privacy_level", "privacy_level"]


def _rtd(endpoint: str = ENDPOINT) -> ReadTheDocs:
    return ReadTheDocs(creds={"authtype": "token", "endpoint": endpoint, "token": "xyz"})


@pytest.mark.parametrize(
    "updates",
    [{"defualt_version": "latest"}, {"default_version": "latest", "colour": "red"}],
    ids=["misspelt", "mixed"],
)
@responses.activate
def test_project_update_refuses_unknown_fields(updates: dict[str, str]) -> None:
    responses.add(responses.PATCH, PROJECT_URL, status=204)

    with pytest.raises(ReadTheDocsValidationError) as raised:
        _rtd().project_update("foo", updates)

    unknown = sorted(set(updates) - set(DOCUMENTED_FIELDS))
    assert all(repr(key) in str(raised.value) for key in unknown)
    assert "default_version" in str(raised.value)
    assert len(responses.calls) == 0


@pytest.mark.parametrize("field", [field for field in DOCUMENTED_FIELDS if field not in PRIVACY_FIELDS])
@responses.activate
def test_project_update_sends_documented_fields(field: str) -> None:
    responses.add(responses.PATCH, PROJECT_URL, status=204)

    result = _rtd().project_update("foo", {field: "x"})

    assert result["updated"] == {field: "x"}
    assert len(responses.calls) == 1


@pytest.mark.parametrize("field", PRIVACY_FIELDS)
@responses.activate
def test_project_update_sends_privacy_fields_elsewhere(field: str) -> None:
    """A deployment other than readthedocs.org may allow private repositories."""
    responses.add(responses.PATCH, f"{BUSINESS_ENDPOINT}projects/foo/", status=204)

    result = _rtd(BUSINESS_ENDPOINT).project_update("foo", {field: "private"})

    assert result["updated"] == {field: "private"}
    assert len(responses.calls) == 1


@pytest.mark.parametrize("field", PRIVACY_FIELDS)
@pytest.mark.parametrize("endpoint", [ENDPOINT, "https://api.readthedocs.org/api/v3/"], ids=["apex", "subdomain"])
@responses.activate
def test_project_update_refuses_privacy_fields_on_community_service(field: str, endpoint: str) -> None:
    """readthedocs.org does not allow private repositories, so it ignores privacy fields."""
    responses.add(responses.PATCH, f"{endpoint}projects/foo/", status=204)

    with pytest.raises(ReadTheDocsValidationError) as raised:
        _rtd(endpoint).project_update("foo", {field: "private"})

    assert repr(field) in str(raised.value)
    assert str(raised.value) == (
        f"readthedocs.org ignores {field!r} on project 'foo': privacy settings need Read the Docs for Business"
    )
    assert len(responses.calls) == 0


@responses.activate
def test_cli_project_update_refuses_unknown_field(monkeypatch: pytest.MonkeyPatch) -> None:
    responses.add(responses.PATCH, PROJECT_URL, status=204)
    monkeypatch.setattr("lftools_uv.typer_apps.rtd.ReadTheDocs", _rtd)

    result = CliRunner().invoke(rtd_app, ["project-update", "foo", "defualt_version=latest"])

    assert len(responses.calls) == 0
    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert "defualt_version" in result.output


FAILURES = pytest.mark.parametrize(
    "failure",
    [requests.exceptions.ConnectionError("connection refused"), requests.exceptions.ReadTimeout("read timed out")],
    ids=["connection", "timeout"],
)


@FAILURES
@pytest.mark.parametrize(
    ("call", "url"),
    [
        (lambda rtd: rtd.project_details("foo"), PROJECT_URL),
        (lambda rtd: rtd.project_update("foo", {"default_version": "latest"}), PROJECT_URL),
        (lambda rtd: rtd.project_build_trigger("foo", "latest"), f"{PROJECT_URL}versions/latest/builds/"),
    ],
    ids=["details", "update", "build-trigger"],
)
@responses.activate
def test_failed_request_is_a_read_the_docs_error(call: object, url: str, failure: Exception) -> None:
    for method in (responses.GET, responses.PATCH, responses.POST):
        responses.add(method, url, body=failure)

    with pytest.raises(ReadTheDocsError) as raised:
        call(_rtd())  # type: ignore[operator]

    assert raised.value.__cause__ is failure
    assert str(failure) in str(raised.value)


@FAILURES
@responses.activate
def test_cli_reports_failed_request_in_one_line(failure: Exception, monkeypatch: pytest.MonkeyPatch) -> None:
    responses.add(responses.GET, PROJECT_URL, body=failure)
    monkeypatch.setattr("lftools_uv.typer_apps.rtd.ReadTheDocs", _rtd)

    result = CliRunner().invoke(rtd_app, ["project-details", "foo"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.output.strip().splitlines() == [f"Error: GET request to Read the Docs failed: {failure}"]
