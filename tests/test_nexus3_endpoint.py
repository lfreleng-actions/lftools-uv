# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for how the ``Nexus3`` endpoint handles HTTP responses."""

import json
from unittest import mock

import pytest
import requests

from lftools_uv.api.endpoints.nexus3 import Nexus3

ENDPOINT = "https://nexus3.example.org/"


def _response(status, body=None, content_type="application/json"):
    """Build a ``requests.Response`` with the given status and body."""
    resp = requests.Response()
    resp.status_code = status
    resp.url = ENDPOINT
    if body is not None:
        text = json.dumps(body) if content_type == "application/json" else body
        resp._content = text.encode("utf-8")
        resp.headers["Content-Type"] = content_type
    else:
        resp._content = b""
    return resp


def _tags_page(names, token):
    return _response(200, {"items": [{"name": name} for name in names], "continuationToken": token})


@pytest.fixture
def nexus3():
    return Nexus3(
        fqdn="nexus3.example.org",
        creds={"authtype": "basic", "username": "user", "password": "secret", "endpoint": ENDPOINT},
    )


def test_delete_user_success(nexus3):
    """A 204 reports the user as deleted."""
    with mock.patch.object(nexus3.r, "request", return_value=_response(204)):
        assert nexus3.delete_user("alice") == "Successfully deleted user alice"


@pytest.mark.parametrize(
    "resp",
    [
        _response(404, {"message": "User not found"}),
        _response(500, "<html>Internal Server Error</html>", content_type="text/html"),
    ],
    ids=["404-json", "500-html"],
)
def test_delete_user_failure_raises(nexus3, resp):
    """Any status but 204 raises ``HTTPError``."""
    with mock.patch.object(nexus3.r, "request", return_value=resp), pytest.raises(requests.HTTPError):
        nexus3.delete_user("alice")


@pytest.mark.xfail(strict=True, reason="#846: the last page of tags is dropped")
def test_list_tags_returns_every_page(nexus3):
    """Tags on every page reach the result, the last page's included."""
    pages = [_tags_page(["t1", "t2"], "a"), _tags_page(["t3", "t4"], "b"), _tags_page(["t5"], None)]
    with mock.patch.object(nexus3.r, "request", side_effect=pages):
        assert nexus3.list_tags() == ["t1", "t2", "t3", "t4", "t5"]


def test_list_tags_single_page(nexus3):
    """A single page returns its tags."""
    with mock.patch.object(nexus3.r, "request", return_value=_tags_page(["t1", "t2"], None)):
        assert nexus3.list_tags() == ["t1", "t2"]


def test_list_tags_empty(nexus3):
    """An empty first response means there are no tags."""
    with mock.patch.object(nexus3.r, "request", return_value=_response(200)):
        assert nexus3.list_tags() == "There are no tags"


@pytest.mark.xfail(strict=True, reason="#846: a failed or empty follow-up page ends the listing silently")
@pytest.mark.parametrize(
    "second_page",
    [_response(500, {"message": "boom"}), _response(200)],
    ids=["failed", "empty"],
)
def test_list_tags_bad_follow_up_page_raises(nexus3, second_page):
    """A failed or empty follow-up page raises rather than returning part of the list."""
    pages = [_tags_page(["t1", "t2"], "a"), second_page]
    with mock.patch.object(nexus3.r, "request", side_effect=pages), pytest.raises(requests.HTTPError):
        nexus3.list_tags()
