# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the failures ``nexus docker releasedockerhub`` must report.

A failed push, a failed setup step and a failed tag lookup each have to
stop the command with a non-zero exit instead of being read as success or
as "no repository". A 404 from a tag lookup still means the repository does
not exist, and a push whose progress stream holds no error still succeeds.

Every Nexus, Docker Hub and Docker daemon call is mocked.
"""

import json
from collections.abc import Iterator
from unittest.mock import MagicMock

import docker.errors
import pytest
import requests
from pytest_mock import MockerFixture
from responses import RequestsMock

import lftools_uv.nexus.release_docker_hub as rdh

ORG = "onap"
NEXUS_REPO = "aaf/aaf_service"
DOCKER_REPO = "aaf-aaf_service"
CATALOG_URL = "https://nexus3.onap.org:10002/v2/_catalog"
NEXUS_TAGS_URL = f"https://nexus3.onap.org:10002/v2/onap/{NEXUS_REPO}/tags/list"
DOCKER_TAGS_URL = f"https://registry.hub.docker.com/v2/namespaces/onap/repositories/{DOCKER_REPO}/tags"
PUSH_ERROR_CHUNK = {
    "errorDetail": {"message": "denied: requested access to the resource is denied"},
    "error": "denied: requested access to the resource is denied",
}


@pytest.fixture(autouse=True)
def _reset_module_state() -> Iterator[None]:
    """Start and finish each test with default settings and no catalog."""
    rdh.initialize(ORG)
    rdh.NexusCatalog = []
    rdh.projects = []
    yield
    rdh.initialize(ORG)
    rdh.NexusCatalog = []
    rdh.projects = []


def _make_project(mocker: MockerFixture) -> tuple[rdh.ProjectClass, MagicMock]:
    """Build a ProjectClass with no tag lookups and a mock Docker client.

    Return the project and the client's ``images.push`` mock.
    """
    nexus_mock = mocker.patch("lftools_uv.nexus.release_docker_hub.project.NexusTagClass")
    nexus_mock.return_value.valid = []
    docker_mock = mocker.patch("lftools_uv.nexus.release_docker_hub.project.DockerTagClass")
    docker_mock.return_value.valid = []
    client = mocker.MagicMock()
    return rdh.ProjectClass([ORG, NEXUS_REPO, ""], client), client.images.push


class TestDockerPush:
    """#838: a push the daemon reports as failed in its stream must raise."""

    @pytest.mark.xfail(strict=True, reason="#838: push stream errors are discarded")
    def test_error_chunk_raises(self, mocker: MockerFixture) -> None:
        proj, push = _make_project(mocker)
        push.return_value = iter([{"status": "Preparing"}, PUSH_ERROR_CHUNK])

        with pytest.raises(docker.errors.APIError, match="denied"):
            proj._docker_push(1, mocker.MagicMock(), "1.2.3", "")

        push.assert_called_once_with(f"{ORG}/{DOCKER_REPO}", tag="1.2.3", stream=True, decode=True)

    @pytest.mark.xfail(strict=True, reason="#838: push stream errors are discarded")
    def test_error_chunk_retried_then_fails(self, mocker: MockerFixture) -> None:
        mocker.patch("lftools_uv.nexus.release_docker_hub.project._MAX_RETRY_ATTEMPTS", 3)
        proj, push = _make_project(mocker)
        push.side_effect = lambda *args, **kwargs: iter([PUSH_ERROR_CHUNK])
        stage = proj._image_stage(proj._docker_push, mocker.MagicMock(), "1.2.3", False)

        with pytest.raises(requests.HTTPError):
            proj._retry_stage("push", stage)

        assert push.call_count == 3

    def test_clean_stream_returns(self, mocker: MockerFixture) -> None:
        proj, push = _make_project(mocker)
        push.return_value = iter([{"status": "Pushed"}, {"status": "1.2.3: digest: sha256:abc"}])

        proj._docker_push(1, mocker.MagicMock(), "1.2.3", "")

        push.assert_called_once()


class TestStartPointFailures:
    """#839: setup and catalog failures must exit 1."""

    @pytest.mark.xfail(strict=True, reason="#839: --exact without a pattern exits 0")
    def test_exact_without_pattern_exits_1(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            rdh.start_point(ORG, "", exact_match=True)
        assert excinfo.value.code == 1

    @pytest.mark.xfail(strict=True, reason="#839: an invalid version regexp exits 0")
    def test_invalid_version_regexp_exits_1(self) -> None:
        with pytest.raises(SystemExit) as excinfo:
            rdh.start_point(ORG, "", version_regexp="(unclosed")
        assert excinfo.value.code == 1

    @pytest.mark.xfail(strict=True, reason="#839: a non-200 catalog reads as success")
    def test_catalog_500_returns_false(self, responses: RequestsMock) -> None:
        responses.add(responses.GET, CATALOG_URL, body="boom", status=500)

        assert rdh.get_nexus3_catalog(ORG) is False
        assert rdh.NexusCatalog == []

    @pytest.mark.xfail(strict=True, reason="#839: a non-200 catalog reads as success")
    def test_catalog_500_exits_1(self, responses: RequestsMock) -> None:
        responses.add(responses.GET, CATALOG_URL, body="boom", status=500)

        with pytest.raises(SystemExit) as excinfo:
            rdh.start_point(ORG)
        assert excinfo.value.code == 1
        assert rdh.projects == []


class TestTagLookupFailures:
    """#840: only a 404 means "no repository"; any other failure raises."""

    @pytest.mark.xfail(strict=True, reason="#840: a failed Nexus lookup reads as no repository")
    def test_nexus_500_raises(self, responses: RequestsMock) -> None:
        responses.add(responses.GET, NEXUS_TAGS_URL, body="boom", status=500)

        with pytest.raises(requests.HTTPError, match="500"):
            rdh.NexusTagClass(ORG, NEXUS_REPO, False)

    def test_nexus_404_means_no_repository(self, responses: RequestsMock) -> None:
        responses.add(responses.GET, NEXUS_TAGS_URL, body="{}", status=404)

        tags = rdh.NexusTagClass(ORG, NEXUS_REPO, False)

        assert tags.repository_exist is False
        assert tags.valid == []

    @pytest.mark.xfail(strict=True, reason="#840: a failed Docker Hub lookup reads as no repository")
    def test_docker_500_first_page_raises(self, responses: RequestsMock) -> None:
        responses.add(responses.GET, DOCKER_TAGS_URL, body="boom", status=500)

        with pytest.raises(requests.HTTPError, match="500"):
            rdh.DockerTagClass(ORG, DOCKER_REPO, False)

    @pytest.mark.xfail(strict=True, reason="#840: a failed later page keeps a partial tag list")
    def test_docker_500_second_page_raises(self, responses: RequestsMock) -> None:
        page2_url = f"{DOCKER_TAGS_URL}?page=2"
        page1 = {"count": 2, "next": page2_url, "results": [{"name": "1.0.0"}]}
        responses.add(responses.GET, DOCKER_TAGS_URL, body=json.dumps(page1), status=200)
        responses.add(responses.GET, page2_url, body="boom", status=500)

        with pytest.raises(requests.HTTPError, match="500"):
            rdh.DockerTagClass(ORG, DOCKER_REPO, False)

    @pytest.mark.xfail(strict=True, reason="#840: a failed later page keeps a partial tag list")
    def test_docker_404_after_empty_first_page_raises(self, responses: RequestsMock) -> None:
        page2_url = f"{DOCKER_TAGS_URL}?page=2"
        page1 = {"count": 0, "next": page2_url, "results": []}
        responses.add(responses.GET, DOCKER_TAGS_URL, body=json.dumps(page1), status=200)
        responses.add(responses.GET, page2_url, body="{}", status=404)

        with pytest.raises(requests.HTTPError, match="404"):
            rdh.DockerTagClass(ORG, DOCKER_REPO, False)

    def test_docker_404_first_page_means_no_repository(self, responses: RequestsMock) -> None:
        responses.add(responses.GET, DOCKER_TAGS_URL, body="{}", status=404)

        tags = rdh.DockerTagClass(ORG, DOCKER_REPO, False)

        assert tags.repository_exist is False
        assert tags.valid == []
