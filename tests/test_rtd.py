# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Test rtd command."""

import json
import os

import pytest
import responses

import lftools_uv.api.endpoints.readthedocs as client
from lftools_uv.api.endpoints.readthedocs import (
    ReadTheDocsAPIError,
    ReadTheDocsNotFoundError,
    ReadTheDocsValidationError,
    version_slug,
)

creds = {"authtype": "token", "endpoint": "https://readthedocs.org/api/v3/", "token": "xyz"}
rtd = client.ReadTheDocs(creds=creds)

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "fixtures",
)


# ---------------------------------------------------------------------------
# Version slug conversion
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("branch", "expected"),
    [
        ("master", "master"),
        ("latest", "latest"),
        ("maintenance/3.7.10", "maintenance-3.7.10"),
        ("mr/879/126960/2", "mr-879-126960-2"),
        ("Montreal", "montreal"),
        ("feature/ABC-123_thing", "feature-abc-123_thing"),
        ("release/1.0", "release-1.0"),
        ("  spaced/branch  ", "spaced-branch"),
    ],
)
def test_version_slug(branch, expected):
    """Branch names convert to the slug Read the Docs stores."""
    assert version_slug(branch) == expected


@pytest.mark.parametrize("branch", ["", "   ", "///", "!!!"])
def test_version_slug_rejects_unusable(branch):
    """Empty or punctuation-only branch names raise."""
    with pytest.raises(ReadTheDocsValidationError):
        version_slug(branch)


# ---------------------------------------------------------------------------
# Projects
# ---------------------------------------------------------------------------


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_list(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_list.json")
    json_data = json.loads(json_file.read())
    responses.add(responses.GET, url="https://readthedocs.org/api/v3/projects/", json=json_data, status=200)
    assert "TestProject1" in rtd.project_list()


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_details(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_details.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET, url="https://readthedocs.org/api/v3/projects/TestProject1/", json=json_data, status=200
    )
    details = rtd.project_details("TestProject1")
    assert isinstance(details, dict)
    assert "slug" in details


@responses.activate
def test_project_details_not_found():
    """A 404 raises a typed error rather than returning prose."""
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/nope/",
        json={"detail": "Not found."},
        status=404,
    )
    with pytest.raises(ReadTheDocsNotFoundError) as excinfo:
        rtd.project_details("nope")
    assert excinfo.value.status_code == 404


@responses.activate
def test_project_details_server_error():
    """A 500 raises an API error carrying the status code."""
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/boom/",
        json={"detail": "Server Error"},
        status=500,
    )
    with pytest.raises(ReadTheDocsAPIError) as excinfo:
        rtd.project_details("boom")
    assert excinfo.value.status_code == 500


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_exists_true(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_details.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET, url="https://readthedocs.org/api/v3/projects/TestProject1/", json=json_data, status=200
    )
    assert rtd.project_exists("TestProject1") is True


@responses.activate
def test_project_exists_false():
    """Absence reports as False rather than an error string."""
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/nope/",
        json={"detail": "Not found."},
        status=404,
    )
    assert rtd.project_exists("nope") is False


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_version_list(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_version_list.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/TestProject1/versions/?active=True",  # noqa
        json=json_data,
        status=200,
        match_querystring=True,
    )
    assert "test-trigger6" in rtd.project_version_list("TestProject1")


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_version_details(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_version_details.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/TestProject1/versions/latest/",  # noqa
        json=json_data,
        status=200,
    )
    details = rtd.project_version_details("TestProject1", "latest")
    assert isinstance(details, dict)
    assert "slug" in details


@responses.activate
def test_project_version_details_uses_slug():
    """A slugified branch resolves; the raw branch name would not."""
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/onap-cps/versions/maintenance-3.7.10/",
        json={"slug": "maintenance-3.7.10", "verbose_name": "maintenance/3.7.10", "active": False},
        status=200,
    )
    details = rtd.project_version_details("onap-cps", version_slug("maintenance/3.7.10"))
    assert details["verbose_name"] == "maintenance/3.7.10"
    assert details["active"] is False


@responses.activate
def test_project_version_update():
    responses.add(
        responses.PATCH,
        url="https://readthedocs.org/api/v3/projects/TestProject1/versions/latest/",  # noqa
        body="",
        status=204,
    )
    result = rtd.project_version_update("TestProject1", "latest", True)
    assert result["status"] == "success"
    assert result["version"] == "latest"
    assert result["active"] is True


@responses.activate
def test_project_create():
    data = {
        "name": "TestProject1",
        "repository": {"url": "https://repository_url", "type": "my_repo_type"},
        "homepage": "https://homepageurl",
        "programming_language": "py",
        "language": "en",
    }
    responses.add(responses.POST, url="https://readthedocs.org/api/v3/projects/", json=data, status=201)
    result = rtd.project_create(
        "TestProject1", "https://repository_url", "my_repo_type", "https://homepageurl", "py", "en"
    )
    assert result["name"] == "TestProject1"


@responses.activate
def test_project_update():
    responses.add(
        responses.PATCH,
        url="https://readthedocs.org/api/v3/projects/TestProject1/",
        body="",
        status=204,
    )
    result = rtd.project_update("TestProject1", {"default_version": "latest"})
    assert result["status"] == "success"
    assert result["updated"] == {"default_version": "latest"}


def test_project_update_rejects_empty_payload():
    """An empty update raises a typed error rather than IndexError."""
    with pytest.raises(ReadTheDocsValidationError):
        rtd.project_update("TestProject1", {})


# ---------------------------------------------------------------------------
# Builds
# ---------------------------------------------------------------------------


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_build_list(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_build_list.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/testproject1/builds/?running=True",  # noqa
        json=json_data,
        status=200,
        match_querystring=True,
    )
    builds = rtd.project_build_list("testproject1")
    assert isinstance(builds, list)
    assert builds[0]["success"] is True


@responses.activate
def test_project_build_list_empty_returns_list():
    """No running builds yields an empty list, never prose."""
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/testproject1/builds/?running=True",
        json={"count": 0, "results": []},
        status=200,
        match_querystring=True,
    )
    assert rtd.project_build_list("testproject1") == []


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_project_build_details(datafiles):
    os.chdir(str(datafiles))
    json_file = open("project_build_details.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/testproject1/builds/9584913/",  # noqa
        json=json_data,
        status=200,
    )
    details = rtd.project_build_details("testproject1", "9584913")
    assert isinstance(details, dict)
    assert "id" in details


@responses.activate
def test_project_build_trigger():
    data = {"project": "testproject1", "version": "latest", "build": {"id": 12345}}
    responses.add(
        responses.POST,
        url="https://readthedocs.org/api/v3/projects/testproject1/versions/latest/builds/",  # noqa
        json=data,
        status=201,
    )
    result = rtd.project_build_trigger("testproject1", "latest")
    build = result["build"]
    assert isinstance(build, dict)
    assert build["id"] == 12345


@responses.activate
def test_project_build_trigger_unknown_version():
    """Triggering an unknown version raises rather than emitting a jq-breaking body."""
    responses.add(
        responses.POST,
        url="https://readthedocs.org/api/v3/projects/onap-cps/versions/maintenance-3.7.10/builds/",
        json={"detail": "Not found."},
        status=404,
    )
    with pytest.raises(ReadTheDocsNotFoundError):
        rtd.project_build_trigger("onap-cps", "maintenance-3.7.10")


# ---------------------------------------------------------------------------
# Subprojects
# ---------------------------------------------------------------------------


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_subproject_list(datafiles):
    os.chdir(str(datafiles))
    json_file = open("subproject_list.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/?limit=999",  # noqa
        json=json_data,
        status=200,
        match_querystring=True,
    )
    assert "testproject2" in rtd.subproject_list("TestProject1")


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_subproject_exists(datafiles):
    os.chdir(str(datafiles))
    json_file = open("subproject_list.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/?limit=999",
        json=json_data,
        status=200,
        match_querystring=True,
    )
    assert rtd.subproject_exists("TestProject1", "testproject2") is True


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "rtd"),
)
@responses.activate
def test_subproject_details(datafiles):
    os.chdir(str(datafiles))
    json_file = open("subproject_details.json")
    json_data = json.loads(json_file.read())
    responses.add(
        responses.GET,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/testproject2/",  # NOQA
        json=json_data,
        status=200,
    )
    details = rtd.subproject_details("TestProject1", "testproject2")
    assert isinstance(details, dict)
    assert "child" in details


@responses.activate
def test_subproject_create():
    responses.add(
        responses.POST,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/",
        status=201,  # NOQA
    )
    result = rtd.subproject_create("TestProject1", "testproject2")
    assert result["status"] == "success"
    assert result["subproject"] == "testproject2"


@responses.activate
def test_subproject_create_omits_absent_alias():
    """The payload carries no alias key when the caller supplies none.

    readthedocs.org fails with an unhandled HTTP 500 when the alias
    arrives as an explicit JSON null, rather than rejecting it as
    invalid, and it defaults the alias to the child's slug when the key
    stays absent. Every ONAP project publishing documentation for the
    first time hit the 500 through rtd-build-action, which passes no
    alias. See lfreleng-actions/rtd-build-action#5.
    """
    responses.add(
        responses.POST,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/",
        status=201,
    )
    _ = rtd.subproject_create("TestProject1", "testproject2")
    body = responses.calls[0].request.body
    assert body is not None
    payload = json.loads(body)
    assert payload == {"child": "testproject2"}
    assert "alias" not in payload


@responses.activate
def test_subproject_create_sends_supplied_alias():
    """A caller-supplied alias reaches the payload unchanged."""
    responses.add(
        responses.POST,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/",
        status=201,
    )
    _ = rtd.subproject_create("TestProject1", "testproject2", alias="docs")
    body = responses.calls[0].request.body
    assert body is not None
    payload = json.loads(body)
    assert payload == {"child": "testproject2", "alias": "docs"}


@responses.activate
def test_subproject_create_sends_empty_alias():
    """An explicit empty-string alias survives; the guard omits None."""
    responses.add(
        responses.POST,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/",
        status=201,
    )
    _ = rtd.subproject_create("TestProject1", "testproject2", alias="")
    body = responses.calls[0].request.body
    assert body is not None
    payload = json.loads(body)
    assert payload == {"child": "testproject2", "alias": ""}


@responses.activate
def test_subproject_delete():
    responses.add(
        responses.DELETE,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/testproject2/",
        status=204,
    )
    result = rtd.subproject_delete("TestProject1", "testproject2")
    assert result["status"] == "success"


@responses.activate
def test_subproject_delete_missing():
    """Deleting an absent relationship raises a typed error."""
    responses.add(
        responses.DELETE,
        url="https://readthedocs.org/api/v3/projects/TestProject1/subprojects/nope/",
        json={"detail": "Not found."},
        status=404,
    )
    with pytest.raises(ReadTheDocsNotFoundError):
        rtd.subproject_delete("TestProject1", "nope")
