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
import sys

import openstack
import openstack.connection
import requests
from openstack.cloud.exc import OpenStackCloudException


def _fetch_jenkins_builds(jenkins_urls: list[str]) -> list[str]:
    """Fetch active builds from Jenkins URLs.

    :arg list jenkins_urls: List of Jenkins URLs to check.
    :returns: List of active build identifiers (silo-job-build format).
    """
    builds: list[str] = []

    for jenkins in jenkins_urls:
        jenkins = jenkins.rstrip("/")
        params = "tree=computer[executors[currentExecutable[url]],oneOffExecutors[currentExecutable[url]]]"
        params += "&xpath=//url&wrapper=builds"
        jenkins_url = f"{jenkins}/computer/api/json?{params}"

        try:
            # Use requests to fetch data
            response = requests.get(
                jenkins_url,
                headers={"Content-Type": "application/json"},
                timeout=30,
            )

            if response.status_code != 200:
                print(f"ERROR: Failed to fetch data from {jenkins_url} with status code {response.status_code}")
                continue

            # Determine silo name
            if "jenkins." in jenkins and (".org" in jenkins or ".io" in jenkins):
                silo = "production"
            else:
                silo = jenkins.split("/")[-1]

            # Parse JSON and extract build identifiers
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                print(f"ERROR: Failed to parse JSON from {jenkins_url}: {e}")
                continue

            for computer in data.get("computer", []):
                for executor in computer.get("executors", []) + computer.get("oneOffExecutors", []):
                    current_exec = executor.get("currentExecutable", {})
                    url = current_exec.get("url")
                    if url and url != "null":
                        parts = url.rstrip("/").split("/")
                        if len(parts) >= 2:
                            job_name = parts[-2]
                            build_num = parts[-1]
                            builds.append(f"{silo}-{job_name}-{build_num}")

        except requests.exceptions.Timeout:
            print(f"ERROR: Timeout fetching data from {jenkins_url}")
        except requests.exceptions.RequestException as e:
            print(f"ERROR: Request failed for {jenkins_url}: {e}")
        except Exception as e:
            print(f"ERROR: Unexpected error fetching from {jenkins_url}: {e}")

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
            print(cluster.name)

    except OpenStackCloudException as e:
        print(f"ERROR: Failed to list clusters: {e}")
        sys.exit(1)
    except AttributeError:
        # Fallback if list_coe_clusters is not available
        print("ERROR: COE cluster operations not supported by this OpenStack SDK version")
        print("Please ensure openstacksdk >= 4.0.0 is installed")
        sys.exit(1)


def cleanup(os_cloud: str, jenkins_urls: str | None = None) -> None:
    """Remove orphaned COE clusters from cloud.

    Scans for COE clusters not in use by active Jenkins builds and removes them.
    Clusters with names containing '-managed-prod-k8s-' or '-managed-test-k8s-'
    are preserved as they are long-lived managed clusters.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg str jenkins_urls: Space-separated list of Jenkins URLs to check for active builds.
    """
    # Parse Jenkins URLs
    jenkins_url_list: list[str] = []
    if jenkins_urls:
        jenkins_url_list = [url.strip() for url in jenkins_urls.split() if url.strip()]

    if not jenkins_url_list:
        print("WARN: No Jenkins URLs provided, skipping cluster cleanup to be safe")
        return

    print(f"INFO: Checking Jenkins URLs for active builds: {' '.join(jenkins_url_list)}")

    # Fetch active builds from Jenkins
    active_builds = _fetch_jenkins_builds(jenkins_url_list)
    print(f"INFO: Found {len(active_builds)} active builds in Jenkins")

    cloud = openstack.connection.from_config(cloud=os_cloud)

    # Fetch COE cluster list
    try:
        clusters = cloud.list_coe_clusters()
        cluster_names = [cluster.name for cluster in clusters]

        print(f"INFO: Found {len(cluster_names)} COE clusters on cloud {os_cloud}")

        # Delete orphaned clusters
        deleted_count = 0
        for cluster_name in cluster_names:
            # Check if cluster is managed (long-lived)
            if "-managed-prod-k8s-" in cluster_name or "-managed-test-k8s-" in cluster_name:
                print(f"INFO: Skipping managed cluster: {cluster_name}")
                continue

            # Check if cluster is in active Jenkins builds
            if _cluster_in_jenkins(cluster_name, active_builds):
                print(f"INFO: Cluster {cluster_name} is in use by active build, skipping")
                continue

            # Delete orphaned cluster
            print(f"INFO: Deleting orphaned k8s cluster: {cluster_name}")
            try:
                cloud.delete_coe_cluster(cluster_name)
                deleted_count += 1
                print(f"INFO: Successfully deleted cluster: {cluster_name}")
            except OpenStackCloudException as e:
                print(f"ERROR: Failed to delete cluster {cluster_name}: {e}")

        print(f"INFO: Deleted {deleted_count} orphaned cluster(s)")

    except OpenStackCloudException as e:
        print(f"ERROR: Failed to list clusters: {e}")
        sys.exit(1)
    except AttributeError:
        # Fallback if COE operations are not available
        print("ERROR: COE cluster operations not supported by this OpenStack SDK version")
        print("Please ensure openstacksdk >= 4.0.0 is installed")
        sys.exit(1)
