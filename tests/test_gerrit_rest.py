# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the requests-based Gerrit REST client.

The ``responses`` fixture stands in for Gerrit. It records the prepared
request, so the URL, credentials and timeout are those requests really
sends, and it honours the adapter's retry policy as urllib3 would.
"""

from __future__ import annotations

import base64
from pathlib import Path

import pytest
import requests
from requests.auth import HTTPBasicAuth
from responses import RequestsMock

from lftools_uv.gerrit_rest import GerritRestAPI

GERRIT = "https://gerrit.example.org/r"
REVIEWERS = f"{GERRIT}/changes/42/reviewers"
JSON = "application/json; charset=UTF-8"


@pytest.fixture(autouse=True)
def no_netrc(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> Path:
    """Point requests at a ~/.netrc that exists only if a test writes it."""
    netrc = tmp_path / "netrc"
    monkeypatch.setenv("NETRC", str(netrc))
    return netrc


def _basic(user: str, password: str) -> str:
    return "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()


def test_credentials_use_the_authenticated_url(responses: RequestsMock) -> None:
    url = f"{GERRIT}/a/projects/foo%2Fbar/access"
    responses.add(responses.GET, url, body="{}", content_type=JSON)

    GerritRestAPI(url=GERRIT, auth=HTTPBasicAuth("bob", "pw")).get(
        "projects/foo%2Fbar/access", headers={"Content-Type": JSON}
    )

    request = responses.calls[0].request
    assert request.url == url
    assert request.headers["Authorization"] == _basic("bob", "pw")
    assert request.headers["Accept"] == "application/json"
    assert request.headers["Content-Type"] == JSON


def test_no_credentials_use_the_plain_url(responses: RequestsMock) -> None:
    responses.add(responses.GET, REVIEWERS, body="[]", content_type=JSON)

    GerritRestAPI(url=GERRIT + "/a/").get("changes/42/reviewers")

    assert "Authorization" not in responses.calls[0].request.headers


def test_netrc_credentials_use_the_authenticated_url(responses: RequestsMock, no_netrc: Path) -> None:
    no_netrc.write_text("machine gerrit.example.org login alice password secret\n")
    no_netrc.chmod(0o600)
    responses.add(responses.GET, f"{GERRIT}/a/changes/42/reviewers", body="[]", content_type=JSON)

    GerritRestAPI(url=GERRIT).get("changes/42/reviewers")

    assert responses.calls[0].request.headers["Authorization"] == _basic("alice", "secret")


def test_magic_prefix_is_stripped_before_decoding(responses: RequestsMock) -> None:
    responses.add(responses.GET, REVIEWERS, body=')]}\'\n[{"username": "alice"}]\n', content_type=JSON)

    assert GerritRestAPI(url=GERRIT).get("changes/42/reviewers") == [{"username": "alice"}]


def test_non_json_body_is_returned_as_text(responses: RequestsMock) -> None:
    responses.add(responses.GET, f"{GERRIT}/config/server/version", body="3.9.1\n", content_type="text/plain")

    assert GerritRestAPI(url=GERRIT).get("config/server/version") == "3.9.1"


def test_error_status_raises(responses: RequestsMock) -> None:
    responses.add(responses.GET, REVIEWERS, status=404, body="Not found", content_type="text/plain")

    with pytest.raises(requests.HTTPError):
        GerritRestAPI(url=GERRIT).get("changes/42/reviewers")


@pytest.mark.parametrize("status", [500, 502, 504])
def test_server_errors_are_retried(responses: RequestsMock, status: int) -> None:
    responses.add(responses.GET, REVIEWERS, status=status, body="busy", content_type="text/plain")
    responses.add(responses.GET, REVIEWERS, body=')]}\'\n{"ok": true}', content_type=JSON)

    assert GerritRestAPI(url=GERRIT).get("changes/42/reviewers") == {"ok": True}
    assert len(responses.calls) == 2


@pytest.mark.parametrize("status", [500, 502, 504])
def test_persistent_server_errors_raise_http_error(
    responses: RequestsMock, monkeypatch: pytest.MonkeyPatch, status: int
) -> None:
    monkeypatch.setattr("urllib3.util.retry.Retry.sleep", lambda *_args, **_kwargs: None)
    responses.add(responses.GET, REVIEWERS, status=status, body="busy", content_type="text/plain")

    with pytest.raises(requests.HTTPError) as excinfo:
        GerritRestAPI(url=GERRIT).get("changes/42/reviewers")

    assert excinfo.value.response is not None
    assert excinfo.value.response.status_code == status
    assert len(responses.calls) == 6


def test_requests_time_out_after_ten_seconds(responses: RequestsMock) -> None:
    responses.add(responses.GET, REVIEWERS, body="[]", content_type=JSON)

    GerritRestAPI(url=GERRIT).get("changes/42/reviewers")

    # responses records the send() keyword arguments on the request it passes on.
    assert vars(responses.calls[0].request)["req_kwargs"]["timeout"] == 10
