# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the branch ``gerrit addinfojob`` writes into an info job.

The info job must name the new project's own default branch, which
Gerrit reports as the project's HEAD, not the JJB repository's branch.
When Gerrit cannot report it, nothing is written or pushed.

Every network and git call is mocked: no test reaches a server or pushes.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
import requests

from lftools_uv.git.gerrit import Gerrit as GitGerrit

FQDN = "gerrit.example.org"
PROJECT = "foo/bar"
HEAD_URL = "https://gerrit.example.org/a/projects/foo%2Fbar/HEAD"

Captured = tuple[list[tuple[str, str]], list[tuple[str, str]], MagicMock]


def _response(status: int, body: object = None) -> requests.Response:
    """Build a Gerrit-style response, JSON behind the ``)]}'`` guard line."""
    response = requests.Response()
    response.status_code = status
    if body is None:
        response.headers["Content-Type"] = "text/plain"
        response._content = b"Not found" if status >= 400 else b""
    else:
        response.headers["Content-Type"] = "application/json; charset=UTF-8"
        response._content = (")]}'\n" + json.dumps(body)).encode()
    return response


def _git_gerrit() -> GitGerrit:
    """A git Gerrit built without its constructor, which clones a repository."""
    g = object.__new__(GitGerrit)
    g.params = {
        "fqdn": FQDN,
        "project": "ci-management",
        "creds": {
            "authtype": "basic",
            "username": "user",
            "password": "pass",
            "endpoint": "https://gerrit.example.org/a/",
            "email": "user@example.org",
        },
    }
    g.fqdn = FQDN
    g.project = "ci-management"
    g.repo = MagicMock()
    g.origin = MagicMock()
    g.default_branch = "main"
    return g


@pytest.fixture
def answer():
    """Answer every Gerrit REST call with one response; capture files and commits."""
    calls: list[tuple[str, str]] = []
    files: list[tuple[str, str]] = []
    reply: dict[str, requests.Response] = {}

    def fake_request(_session, method, url, **_kwargs):
        calls.append((method, url))
        return reply["response"]

    def fake_add_file(_self, path, content):
        files.append((path, content))

    with (
        patch.object(requests.Session, "request", fake_request),
        patch.object(GitGerrit, "add_file", fake_add_file),
        patch.object(GitGerrit, "commit") as commit,
    ):

        def install(response: requests.Response) -> Captured:
            reply["response"] = response
            return calls, files, commit

        yield install


def test_info_job_path(answer):
    """The info job still goes to the project's own JJB directory."""
    _calls, files, _commit = answer(_response(200, "refs/heads/develop"))

    _git_gerrit().add_info_job(FQDN, PROJECT, None, None)

    assert [path for path, _content in files] == ["jjb/foo-bar/foo-bar.yaml"]


@pytest.mark.xfail(strict=True, reason="#975: info job uses the JJB repository's branch")
def test_info_job_uses_project_head(answer):
    """The branch comes from the project's HEAD in Gerrit."""
    calls, files, commit = answer(_response(200, "refs/heads/develop"))

    _git_gerrit().add_info_job(FQDN, PROJECT, None, None)

    assert len(files) == 1
    content = files[0][1]
    assert "branch: develop" in content
    assert "branch: main" not in content
    assert calls == [("GET", HEAD_URL)]
    commit.assert_called_once()


@pytest.mark.xfail(strict=True, reason="#975: info job uses the JJB repository's branch")
@pytest.mark.parametrize(
    "response",
    [_response(404), _response(200, {"unexpected": True})],
    ids=["not-found", "not-a-ref"],
)
def test_info_job_without_head_pushes_nothing(answer, response):
    """When Gerrit cannot report the branch, nothing is written or pushed."""
    _calls, files, commit = answer(response)

    with pytest.raises(requests.HTTPError):
        _git_gerrit().add_info_job(FQDN, PROJECT, None, None)

    assert files == []
    commit.assert_not_called()
