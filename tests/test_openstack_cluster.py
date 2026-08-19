# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2025 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Test OpenStack cluster operations."""

from unittest.mock import MagicMock, patch

import pytest
import responses

from lftools_uv.openstack import cluster as os_cluster


@responses.activate
def test_fetch_jenkins_builds_production():
    """Test fetching builds from production Jenkins."""
    jenkins_url = "https://jenkins.example.org"
    api_url = f"{jenkins_url}/computer/api/json"

    jenkins_response = {
        "computer": [
            {
                "executors": [{"currentExecutable": {"url": "https://jenkins.example.org/job/test-job/123/"}}],
                "oneOffExecutors": [{"currentExecutable": {"url": "https://jenkins.example.org/job/another-job/456/"}}],
            }
        ]
    }

    responses.add(
        responses.GET,
        api_url,
        json=jenkins_response,
        status=200,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert len(builds) == 2
    assert "production-test-job-123" in builds
    assert "production-another-job-456" in builds


@responses.activate
def test_fetch_jenkins_builds_silo():
    """Test fetching builds from silo Jenkins."""
    jenkins_url = "https://jenkins.example.com/sandbox"
    api_url = f"{jenkins_url}/computer/api/json"

    jenkins_response = {
        "computer": [
            {
                "executors": [{"currentExecutable": {"url": "https://jenkins.example.com/sandbox/job/build-job/789/"}}],
                "oneOffExecutors": [],
            }
        ]
    }

    responses.add(
        responses.GET,
        api_url,
        json=jenkins_response,
        status=200,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert len(builds) == 1
    assert "sandbox-build-job-789" in builds


@responses.activate
def test_fetch_jenkins_builds_null_url():
    """Test that null URLs in Jenkins response are filtered out."""
    jenkins_url = "https://jenkins.example.org"
    api_url = f"{jenkins_url}/computer/api/json"

    jenkins_response = {
        "computer": [
            {
                "executors": [
                    {"currentExecutable": {"url": "null"}},
                    {"currentExecutable": {"url": "https://jenkins.example.org/job/valid-job/100/"}},
                ],
                "oneOffExecutors": [],
            }
        ]
    }

    responses.add(
        responses.GET,
        api_url,
        json=jenkins_response,
        status=200,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert len(builds) == 1
    assert "production-valid-job-100" in builds


@responses.activate
def test_fetch_jenkins_builds_http_error():
    """Test handling of HTTP errors when fetching Jenkins builds."""
    jenkins_url = "https://jenkins.example.org"
    api_url = f"{jenkins_url}/computer/api/json"

    responses.add(
        responses.GET,
        api_url,
        json={"error": "Not found"},
        status=404,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert len(builds) == 0


@pytest.mark.parametrize(
    "payload",
    [
        {"computer": None},
        {"computer": [{"executors": None, "oneOffExecutors": []}]},
        {"computer": [{"executors": [{"currentExecutable": {"url": 42}}], "oneOffExecutors": []}]},
        ["not", "an", "object"],
    ],
    ids=["null-computer", "null-executors", "non-string-url", "top-level-list"],
)
@responses.activate
def test_fetch_jenkins_builds_malformed_shape(payload, capsys):
    """A valid JSON body with an unexpected shape yields no builds.

    Cluster cleanup treats an unusable Jenkins as having no active builds, so
    a surprising response shape must report the problem and carry on rather
    than aborting the whole cleanup run.
    """
    jenkins_url = "https://jenkins.example.org"
    responses.add(
        responses.GET,
        f"{jenkins_url}/computer/api/json",
        json=payload,
        status=200,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert builds == []
    assert "ERROR" in capsys.readouterr().out


@responses.activate
def test_fetch_jenkins_builds_timeout(capsys):
    """Test handling of timeout when fetching Jenkins builds."""
    jenkins_url = "https://jenkins.example.org"
    api_url = f"{jenkins_url}/computer/api/json"

    responses.add(
        responses.GET,
        api_url,
        body=Exception("Timeout"),
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert len(builds) == 0
    captured = capsys.readouterr()
    assert "ERROR" in captured.out


@responses.activate
def test_fetch_jenkins_builds_invalid_json(capsys):
    """Test handling of invalid JSON response."""
    jenkins_url = "https://jenkins.example.org"
    api_url = f"{jenkins_url}/computer/api/json"

    responses.add(
        responses.GET,
        api_url,
        body="not valid json",
        status=200,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url])

    assert len(builds) == 0
    captured = capsys.readouterr()
    assert "ERROR" in captured.out


@responses.activate
def test_fetch_jenkins_builds_multiple_urls():
    """Test fetching builds from multiple Jenkins URLs."""
    jenkins_url1 = "https://jenkins.example.org"
    jenkins_url2 = "https://jenkins.example.io"

    responses.add(
        responses.GET,
        f"{jenkins_url1}/computer/api/json",
        json={
            "computer": [
                {
                    "executors": [{"currentExecutable": {"url": "https://jenkins.example.org/job/job1/111/"}}],
                    "oneOffExecutors": [],
                }
            ]
        },
        status=200,
    )

    responses.add(
        responses.GET,
        f"{jenkins_url2}/computer/api/json",
        json={
            "computer": [
                {
                    "executors": [{"currentExecutable": {"url": "https://jenkins.example.io/job/job2/222/"}}],
                    "oneOffExecutors": [],
                }
            ]
        },
        status=200,
    )

    builds = os_cluster._fetch_jenkins_builds([jenkins_url1, jenkins_url2])

    assert len(builds) == 2
    assert "production-job1-111" in builds
    assert "production-job2-222" in builds


def test_cluster_in_jenkins():
    """Test checking if cluster is in active Jenkins builds."""
    jenkins_builds = [
        "production-build-job-123",
        "sandbox-test-job-456",
        "production-deploy-job-789",
    ]

    assert os_cluster._cluster_in_jenkins("build-job-123", jenkins_builds) is True
    assert os_cluster._cluster_in_jenkins("test-job-456", jenkins_builds) is True
    assert os_cluster._cluster_in_jenkins("missing-cluster", jenkins_builds) is False


@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_list_clusters(mock_from_config, capsys):
    """Test listing COE clusters."""
    # Mock OpenStack connection
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud

    # Mock cluster objects
    mock_cluster1 = MagicMock()
    mock_cluster1.name = "test-cluster-1"
    mock_cluster2 = MagicMock()
    mock_cluster2.name = "test-cluster-2"

    mock_cloud.list_coe_clusters.return_value = [mock_cluster1, mock_cluster2]

    # Call list function
    os_cluster.list_clusters("test-cloud")

    # Verify output
    captured = capsys.readouterr()
    assert "test-cluster-1" in captured.out
    assert "test-cluster-2" in captured.out

    # Verify OpenStack SDK was called correctly
    mock_from_config.assert_called_once_with(cloud="test-cloud")
    mock_cloud.list_coe_clusters.assert_called_once()


@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_list_clusters_error(mock_from_config, capsys):
    """Test handling errors when listing clusters."""
    from openstack.cloud.exc import OpenStackCloudException

    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.list_coe_clusters.side_effect = OpenStackCloudException("Test error")

    with pytest.raises(SystemExit) as exc_info:
        os_cluster.list_clusters("test-cloud")

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "Failed to list clusters" in captured.out


@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_list_clusters_not_supported(mock_from_config, capsys):
    """Test handling when COE operations are not supported."""
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.list_coe_clusters.side_effect = AttributeError("Not supported")

    with pytest.raises(SystemExit) as exc_info:
        os_cluster.list_clusters("test-cloud")

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR" in captured.out
    assert "not supported" in captured.out


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_no_jenkins_urls(mock_from_config, mock_fetch_builds, capsys):
    """Test cleanup with no Jenkins URLs provided."""
    os_cluster.cleanup("test-cloud", jenkins_urls=None)

    captured = capsys.readouterr()
    assert "WARN" in captured.out
    assert "No Jenkins URLs provided" in captured.out

    # Should not attempt to fetch builds or connect to OpenStack
    mock_fetch_builds.assert_not_called()
    mock_from_config.assert_not_called()


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_empty_jenkins_urls(mock_from_config, mock_fetch_builds, capsys):
    """Test cleanup with empty Jenkins URLs string."""
    os_cluster.cleanup("test-cloud", jenkins_urls="   ")

    captured = capsys.readouterr()
    assert "WARN" in captured.out
    assert "No Jenkins URLs provided" in captured.out

    mock_fetch_builds.assert_not_called()
    mock_from_config.assert_not_called()


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_orphaned_clusters(mock_from_config, mock_fetch_builds, capsys):
    """Test cleanup of orphaned clusters."""
    # Mock Jenkins builds
    mock_fetch_builds.return_value = ["production-active-job-123"]

    # Mock OpenStack connection
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud

    # Mock cluster objects
    mock_cluster1 = MagicMock()
    mock_cluster1.name = "orphaned-cluster-1"
    mock_cluster2 = MagicMock()
    mock_cluster2.name = "active-job-123"
    mock_cluster3 = MagicMock()
    mock_cluster3.name = "orphaned-cluster-2"

    mock_cloud.list_coe_clusters.return_value = [mock_cluster1, mock_cluster2, mock_cluster3]

    # Call cleanup
    os_cluster.cleanup("test-cloud", jenkins_urls="https://jenkins.example.org")

    # Verify orphaned clusters were deleted but active one was not
    captured = capsys.readouterr()
    assert "Deleting orphaned k8s cluster: orphaned-cluster-1" in captured.out
    assert "Deleting orphaned k8s cluster: orphaned-cluster-2" in captured.out
    assert "Cluster active-job-123 is in use by active build" in captured.out
    assert "Deleted 2 orphaned cluster(s)" in captured.out

    # Verify delete was called for orphaned clusters
    assert mock_cloud.delete_coe_cluster.call_count == 2
    mock_cloud.delete_coe_cluster.assert_any_call("orphaned-cluster-1")
    mock_cloud.delete_coe_cluster.assert_any_call("orphaned-cluster-2")


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_preserves_managed_clusters(mock_from_config, mock_fetch_builds, capsys):
    """Test that managed clusters are preserved during cleanup."""
    # Mock Jenkins builds (empty - no active builds)
    mock_fetch_builds.return_value = []

    # Mock OpenStack connection
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud

    # Mock cluster objects including managed ones
    mock_cluster1 = MagicMock()
    mock_cluster1.name = "orphaned-cluster"
    mock_cluster2 = MagicMock()
    mock_cluster2.name = "project-managed-prod-k8s-cluster"
    mock_cluster3 = MagicMock()
    mock_cluster3.name = "project-managed-test-k8s-cluster"

    mock_cloud.list_coe_clusters.return_value = [mock_cluster1, mock_cluster2, mock_cluster3]

    # Call cleanup
    os_cluster.cleanup("test-cloud", jenkins_urls="https://jenkins.example.org")

    # Verify managed clusters were skipped
    captured = capsys.readouterr()
    assert "Skipping managed cluster: project-managed-prod-k8s-cluster" in captured.out
    assert "Skipping managed cluster: project-managed-test-k8s-cluster" in captured.out
    assert "Deleting orphaned k8s cluster: orphaned-cluster" in captured.out
    assert "Deleted 1 orphaned cluster(s)" in captured.out

    # Verify delete was only called once
    mock_cloud.delete_coe_cluster.assert_called_once_with("orphaned-cluster")


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_delete_error(mock_from_config, mock_fetch_builds, capsys):
    """Test handling of errors when deleting clusters."""
    from openstack.cloud.exc import OpenStackCloudException

    # Mock Jenkins builds
    mock_fetch_builds.return_value = []

    # Mock OpenStack connection
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud

    # Mock cluster
    mock_cluster = MagicMock()
    mock_cluster.name = "orphaned-cluster"
    mock_cloud.list_coe_clusters.return_value = [mock_cluster]

    # Make delete raise an error
    mock_cloud.delete_coe_cluster.side_effect = OpenStackCloudException("Delete failed")

    # Call cleanup - should not exit, just log error
    os_cluster.cleanup("test-cloud", jenkins_urls="https://jenkins.example.org")

    captured = capsys.readouterr()
    assert "ERROR: Failed to delete cluster orphaned-cluster" in captured.out
    assert "Deleted 0 orphaned cluster(s)" in captured.out


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_multiple_jenkins_urls(mock_from_config, mock_fetch_builds, capsys):
    """Test cleanup with multiple Jenkins URLs."""
    # Mock Jenkins builds
    mock_fetch_builds.return_value = ["production-job-1", "sandbox-job-2"]

    # Mock OpenStack connection
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.list_coe_clusters.return_value = []

    # Call cleanup with multiple URLs
    jenkins_urls = "https://jenkins1.example.org https://jenkins2.example.com/sandbox"
    os_cluster.cleanup("test-cloud", jenkins_urls=jenkins_urls)

    # Verify both URLs were processed
    captured = capsys.readouterr()
    # Check for the full INFO message to avoid CodeQL's incomplete URL substring sanitization warning
    # These are test assertions verifying output format, not security-related URL validation
    expected_info_line = (
        "INFO: Checking Jenkins URLs for active builds: "
        "https://jenkins1.example.org https://jenkins2.example.com/sandbox"
    )
    assert expected_info_line in captured.out
    assert "Found 2 active builds in Jenkins" in captured.out


@patch("lftools_uv.openstack.cluster._fetch_jenkins_builds")
@patch("lftools_uv.openstack.cluster.openstack.connection.from_config")
def test_cleanup_list_clusters_error(mock_from_config, mock_fetch_builds, capsys):
    """Test handling of errors when listing clusters during cleanup."""
    from openstack.cloud.exc import OpenStackCloudException

    # Mock Jenkins builds
    mock_fetch_builds.return_value = []

    # Mock OpenStack connection
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.list_coe_clusters.side_effect = OpenStackCloudException("List failed")

    # Call cleanup
    with pytest.raises(SystemExit) as exc_info:
        os_cluster.cleanup("test-cloud", jenkins_urls="https://jenkins.example.org")

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "ERROR: Failed to list clusters" in captured.out
