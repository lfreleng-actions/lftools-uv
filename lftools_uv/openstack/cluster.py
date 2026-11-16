# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2025 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Cluster related sub-commands for openstack command."""

from __future__ import annotations

__author__ = "Anil Belur"

import json
import logging
import sys
from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any

# aislop-ignore-file hallucinated-import -- the declared openstacksdk dependency provides the `openstack` import package
import openstack
import openstack.connection
import requests
from openstack.cloud.exc import OpenStackCloudException

from lftools_uv.output import echo

log = logging.getLogger(__name__)


class JenkinsBuildsUnavailableError(RuntimeError):
    """A Jenkins server could not report its active builds."""


def _silo_name(jenkins: str) -> str:
    """Derive the silo label used to namespace build identifiers."""
    if "jenkins." in jenkins and (".org" in jenkins or ".io" in jenkins):
        return "production"
    return jenkins.split("/")[-1]


def _executable_urls(data: dict[str, Any]) -> Iterator[str]:
    """Yield the URL of every executable currently running on any node."""
    for computer in data.get("computer", []):
        for executor in computer.get("executors", []) + computer.get("oneOffExecutors", []):
            current = executor.get("currentExecutable") or {}
            url = current.get("url")
            if url and url != "null":
                yield url


def _build_id(silo: str, executable_url: str) -> str | None:
    """Return a ``silo-job-build`` identifier, or None if the URL lacks both parts."""
    parts = executable_url.rstrip("/").split("/")
    if len(parts) < 2:
        return None
    job_name, build_num = parts[-2], parts[-1]
    return f"{silo}-{job_name}-{build_num}"


def _fetch_builds_from(jenkins: str) -> list[str]:
    """Return the active build identifiers reported by a single Jenkins.

    Returns an empty list only when the server answers with a well-formed
    reply that holds no builds.

    :raises JenkinsBuildsUnavailableError: if the server cannot be reached,
        answers with an error status, or its reply cannot be parsed.
    """
    params = "tree=computer[executors[currentExecutable[url]],oneOffExecutors[currentExecutable[url]]]"
    params += "&xpath=//url&wrapper=builds"
    jenkins_url = f"{jenkins}/computer/api/json?{params}"

    try:
        response = requests.get(
            jenkins_url,
            headers={"Content-Type": "application/json"},
            timeout=30,
        )
    except requests.exceptions.Timeout as e:
        raise JenkinsBuildsUnavailableError(f"Timeout fetching data from {jenkins_url}") from e
    except requests.exceptions.RequestException as e:
        raise JenkinsBuildsUnavailableError(f"Request failed for {jenkins_url}: {e}") from e
    except Exception as e:
        raise JenkinsBuildsUnavailableError(f"Unexpected error fetching from {jenkins_url}: {e}") from e

    if response.status_code != 200:
        raise JenkinsBuildsUnavailableError(
            f"Failed to fetch data from {jenkins_url} with status code {response.status_code}"
        )

    try:
        data = response.json()
    except json.JSONDecodeError as e:
        raise JenkinsBuildsUnavailableError(f"Failed to parse JSON from {jenkins_url}: {e}") from e

    silo = _silo_name(jenkins)
    try:
        return [build for url in _executable_urls(data) if (build := _build_id(silo, url)) is not None]
    except (AttributeError, TypeError) as e:
        # A syntactically valid reply can still have an unexpected shape, for
        # example {"computer": null}. Its builds are unknown, so it cannot be
        # treated as idle.
        raise JenkinsBuildsUnavailableError(f"Unexpected response shape from {jenkins_url}: {e}") from e


def _fetch_jenkins_builds(jenkins_urls: list[str]) -> list[str]:
    """Fetch active builds from Jenkins URLs.

    :arg list jenkins_urls: List of Jenkins URLs to check.
    :returns: List of active build identifiers (silo-job-build format).
    :raises JenkinsBuildsUnavailableError: if any server cannot report its
        builds, since the builds from the others are not a complete list.
    """
    builds: list[str] = []
    for jenkins in jenkins_urls:
        builds.extend(_fetch_builds_from(jenkins.rstrip("/")))
    return builds


def _cluster_in_jenkins(cluster_name: str, jenkins_builds: list[str]) -> bool:
    """Check if cluster is in active Jenkins builds.

    :arg str cluster_name: Name of the cluster to check.
    :arg list jenkins_builds: List of active build identifiers.
    :returns: True if cluster is in use, False otherwise.
    """
    return cluster_name in " ".join(jenkins_builds)


def list_clusters(os_cloud: str) -> None:
    """List COE clusters.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)

    try:
        # Use the container_infrastructure endpoint to list clusters
        # Note: openstacksdk's container_infrastructure module provides cluster operations
        clusters = cloud.list_coe_clusters()

        for cluster in clusters:
            echo(cluster.name)

    except OpenStackCloudException as e:
        log.error("Failed to list clusters: %s", e)
        sys.exit(1)
    except AttributeError:
        # Fallback if list_coe_clusters is not available
        log.error("COE cluster operations not supported by this OpenStack SDK version")
        log.error("Please ensure openstacksdk >= 4.0.0 is installed")
        sys.exit(1)


def _get_cluster(cloud: openstack.connection.Connection, cluster_name: str) -> Any:
    """Return the full record of the named COE cluster, exiting 1 if it cannot be found.

    :arg cloud: Connection to the cloud holding the cluster.
    :arg str cluster_name: Name or ID of the cluster.
    """
    try:
        # get_coe_cluster resolves the name from Magnum's list summary, which
        # omits created_at and details such as api_address, so fetch the
        # full resource by ID.
        summary = cloud.get_coe_cluster(cluster_name)
        cluster = cloud.container_infrastructure_management.get_cluster(summary.id) if summary else None
    except OpenStackCloudException as e:
        log.error("Failed to look up cluster %s: %s", cluster_name, e)
        sys.exit(1)
    except AttributeError as e:
        log.error("COE cluster operations not supported by this OpenStack SDK version: %s", e)
        log.error("Please ensure openstacksdk >= 4.0.0 is installed")
        sys.exit(1)

    if not cluster:
        log.error("Cluster %s not found.", cluster_name)
        sys.exit(1)
    return cluster


def _created_within_minutes(created_at: str, minutes: int) -> bool:
    """Return whether a resource was created within the last ``minutes`` minutes.

    Magnum reports ``created_at`` in UTC, with or without a zone suffix,
    so a value without one is read as UTC.
    """
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created >= datetime.now(UTC) - timedelta(minutes=minutes)


def remove(os_cloud: str, cluster_name: str, minutes: int = 0) -> None:
    """Remove a COE cluster from cloud.

    Exits non-zero if the cluster cannot be found or deleted.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg str cluster_name: Name or ID of the cluster to remove.
    :arg int minutes: Only delete the cluster if it is older than this many
        minutes; the default 0 deletes it whatever its age.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)
    cluster = _get_cluster(cloud, cluster_name)

    if minutes > 0 and _created_within_minutes(cluster.created_at, minutes):
        log.warning('Cluster "%s" (%s) is not older than %d minutes.', cluster.name, cluster.id, minutes)
        return

    try:
        deleted = cloud.delete_coe_cluster(cluster.id)
    except OpenStackCloudException as e:
        log.error("Failed to delete cluster %s: %s", cluster_name, e)
        sys.exit(1)
    # delete_coe_cluster looks the cluster up again and returns False,
    # without raising, when that lookup finds nothing.
    if not deleted:
        log.error("Failed to delete cluster %s: not found.", cluster_name)
        sys.exit(1)
    log.info("Deleted cluster %s", cluster_name)


def show(os_cloud: str, cluster_name: str) -> None:
    """Print the attributes of a COE cluster as JSON.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg str cluster_name: Name or ID of the cluster to show.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)
    cluster = _get_cluster(cloud, cluster_name)
    echo(json.dumps(cluster.to_dict(), indent=2, sort_keys=True, default=str))


def cleanup(os_cloud: str, jenkins_urls: str | None = None) -> None:
    """Remove orphaned COE clusters from cloud.

    Scans for COE clusters not in use by active Jenkins builds and removes them.
    Clusters with names containing '-managed-prod-k8s-' or '-managed-test-k8s-'
    are preserved as they are long-lived managed clusters. Exits non-zero if
    any orphaned cluster could not be deleted.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg str jenkins_urls: Space-separated list of Jenkins URLs to check for active builds.
    """
    jenkins_url_list: list[str] = []
    if jenkins_urls:
        jenkins_url_list = [url.strip() for url in jenkins_urls.split() if url.strip()]

    if not jenkins_url_list:
        log.warning("No Jenkins URLs provided, skipping cluster cleanup to be safe")
        return

    log.info("Checking Jenkins URLs for active builds: %s", " ".join(jenkins_url_list))

    try:
        active_builds = _fetch_jenkins_builds(jenkins_url_list)
    except JenkinsBuildsUnavailableError as e:
        log.error("%s", e)
        log.error("Cannot determine active builds, no cluster was deleted")
        sys.exit(1)
    log.info("Found %d active builds in Jenkins", len(active_builds))

    cloud = openstack.connection.from_config(cloud=os_cloud)

    failed: list[str] = []
    try:
        clusters = cloud.list_coe_clusters()
        cluster_names = [cluster.name for cluster in clusters]

        log.info("Found %d COE clusters on cloud %s", len(cluster_names), os_cloud)

        deleted_count = 0
        for cluster_name in cluster_names:
            # Check if cluster is managed (long-lived)
            if "-managed-prod-k8s-" in cluster_name or "-managed-test-k8s-" in cluster_name:
                log.info("Skipping managed cluster: %s", cluster_name)
                continue

            # Check if cluster is in active Jenkins builds
            if _cluster_in_jenkins(cluster_name, active_builds):
                log.info("Cluster %s is in use by active build, skipping", cluster_name)
                continue

            log.info("Deleting orphaned k8s cluster: %s", cluster_name)
            try:
                cloud.delete_coe_cluster(cluster_name)
                deleted_count += 1
                log.info("Successfully deleted cluster: %s", cluster_name)
            except OpenStackCloudException as e:
                log.error("Failed to delete cluster %s: %s", cluster_name, e)
                failed.append(cluster_name)

        log.info("Deleted %d orphaned cluster(s)", deleted_count)

    except OpenStackCloudException as e:
        log.error("Failed to list clusters: %s", e)
        sys.exit(1)
    except AttributeError:
        # Fallback if COE operations are not available
        log.error("COE cluster operations not supported by this OpenStack SDK version")
        log.error("Please ensure openstacksdk >= 4.0.0 is installed")
        sys.exit(1)

    if failed:
        log.error("Failed to delete %d orphaned cluster(s): %s", len(failed), ", ".join(failed))
        sys.exit(1)
