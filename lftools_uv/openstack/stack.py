# -*- code: utf-8 -*-
from __future__ import annotations

# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""stack related sub-commands for openstack command."""

__author__ = "Thanh Ha"

import json
import logging
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Any

import openstack
import openstack.connection
from openstack.cloud.exc import OpenStackCloudHTTPError

from lftools_uv.jenkins import Jenkins

log = logging.getLogger(__name__)


def create(os_cloud: str, name: str, template_file: str, parameter_file: str, timeout: int = 900, tries: int = 2) -> None:
    """Create a heat stack from a template_file and a parameter_file."""
    cloud = openstack.connection.from_config(cloud=os_cloud)
    stack_success = False
    stack = None

    print(f"Creating stack {name}")
    for _attempt in range(tries):
        try:
            stack = cloud.create_stack(
                name, template_file=template_file, environment_files=[parameter_file], timeout=timeout, rollback=False
            )
        except OpenStackCloudHTTPError as e:
            if cloud.search_stacks(name):
                print(f"Stack with name {name} already exists.")
            else:
                print(e)
            sys.exit(1)

        stack_id = stack.id  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
        t_end = time.time() + timeout
        while time.time() < t_end:
            time.sleep(10)
            stack = cloud.get_stack(stack_id)

            if stack.status == "CREATE_IN_PROGRESS":  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
                print("Waiting to initialize infrastructure...")
            elif stack.status == "CREATE_COMPLETE":  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
                print("Stack initialization successful.")
                stack_success = True
                break
            elif stack.status == "CREATE_FAILED":  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
                print(f"WARN: Failed to initialize stack. Reason: {stack.status_reason}")  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]
                if delete(os_cloud, stack_id):
                    break
            else:
                print(f"Unexpected status: {stack.status}")  # pyright: ignore[reportOptionalMemberAccess, reportAttributeAccessIssue]

        if stack_success:
            break

    print("------------------------------------")
    print("Stack Details")
    print("------------------------------------")
    cloud.pprint(stack)
    print("------------------------------------")


def cost(os_cloud: str, stack_name: str, timeout: int = 60) -> None:
    """Get current cost info for the stack.

    Return the cost in dollars & cents (x.xx).

    Args:
        os_cloud: OpenStack cloud name from clouds.yaml
        stack_name: Name of the stack to calculate cost for
        timeout: Timeout in seconds for network operations (default: 60)
    """

    def get_server_cost(server_id: str) -> float:
        try:
            flavor, seconds = get_server_info(server_id)
            url = "https://pricing.vexxhost.net/v1/pricing/%s/cost?seconds=%d"
            with urllib.request.urlopen(url % (flavor, seconds), timeout=timeout) as response:  # nosec
                data = json.loads(response.read())
            return float(data["cost"])
        except (TimeoutError, urllib.error.URLError) as e:
            log.warning("Failed to get cost for server %s: %s", server_id, e)
            log.warning("Returning 0 cost for this server")
            return 0.0
        except Exception as e:
            log.error("Unexpected error getting cost for server %s: %s", server_id, e)
            return 0.0

    def parse_iso8601_time(time: str) -> datetime:
        return datetime.strptime(time, "%Y-%m-%dT%H:%M:%S.%f")

    def get_server_info(server_id: str) -> tuple[str, float]:
        server = cloud.compute.find_server(server_id)  # pyright: ignore[reportAttributeAccessIssue]
        diff = datetime.utcnow() - parse_iso8601_time(server.launched_at) # pyright: ignore[reportOptionalMemberAccess]
        return server.flavor["original_name"], diff.total_seconds() # pyright: ignore[reportOptionalMemberAccess]

    def get_server_ids(stack_name: str) -> list[str]:
        servers = get_resources_by_type(stack_name, "OS::Nova::Server")
        return [s["physical_resource_id"] for s in servers]

    def get_resources_by_type(stack_name: str, resource_type: str) -> list[Any]:
        resources = get_stack_resources(stack_name)
        return [r for r in resources if r.resource_type == resource_type]

    def get_stack_resources(stack_name: str) -> list[Any]:
        resources = []

        def _is_nested(resource: Any) -> bool:
            link_types = [link["rel"] for link in resource.links]
            if "nested" in link_types:
                return True
            return False

        for r in cloud.orchestration.resources(stack_name):  # pyright: ignore[reportAttributeAccessIssue]
            if _is_nested(r):
                resources += get_stack_resources(r.physical_resource_id)
                continue
            resources.append(r)
        return resources

    cloud = openstack.connect(os_cloud)

    try:
        total_cost = 0.0
        server_ids = get_server_ids(stack_name)

        if not server_ids:
            log.info("No servers found in stack %s", stack_name)
            print("total: 0.0")
            return

        for server in server_ids:
            total_cost += get_server_cost(server)
        print("total: " + str(total_cost))
    except Exception as e:
        log.error("Error calculating stack cost: %s", e)
        log.warning("Returning 0 total cost due to error")
        print("total: 0.0")


def delete(os_cloud: str, name_or_id: str, force: bool = False, timeout: int = 900) -> bool | None:
    """Delete a stack.

    Return True if delete was successful.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)
    print(f"Deleting stack {name_or_id}")
    cloud.delete_stack(name_or_id)

    t_end = time.time() + timeout
    while time.time() < t_end:
        time.sleep(10)
        stack = cloud.get_stack(name_or_id)

        if not stack or stack.status == "DELETE_COMPLETE":  # pyright: ignore[reportAttributeAccessIssue]
            print(f"Successfully deleted stack {name_or_id}")
            return True
        elif stack.status == "DELETE_IN_PROGRESS":  # pyright: ignore[reportAttributeAccessIssue]
            print("Waiting for stack to delete...")
        elif stack.status == "DELETE_FAILED":  # pyright: ignore[reportAttributeAccessIssue]
            print(f"WARN: Failed to delete $STACK_NAME. Reason: {stack.status_reason}")  # pyright: ignore[reportAttributeAccessIssue]
            print("Retrying delete...")
            cloud.delete_stack(name_or_id)
        else:
            print(f"WARN: Unexpected delete status: {stack.status}")  # pyright: ignore[reportAttributeAccessIssue]
            print("Retrying delete...")
            cloud.delete_stack(name_or_id)

    print(f"Failed to delete stack {name_or_id}")
    if not force:
        return False
    return None


def delete_stale(os_cloud: str, jenkins_servers: list[str]) -> None:
    """Search Jenkins and OpenStack for orphaned stacks and remove them.

    An orphaned stack is a stack that is not known in any of the Jenkins
    servers passed into this function.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)
    stacks = cloud.search_stacks()
    if not stacks:
        log.debug("No stacks to delete.")
        sys.exit(0)

    builds = []
    for server in jenkins_servers:
        jenkins = Jenkins(server)
        jenkins_url = jenkins.url.rstrip("/")
        silo_parts = jenkins_url.split("/")

        if len(silo_parts) == 4:  # https://jenkins.opendaylight.org/releng
            silo = silo_parts[3]
        elif len(silo_parts) == 3:  # https://jenkins.onap.org
            silo = "production"
        else:
            log.error("Unexpected URL pattern, could not detect silo.")
            sys.exit(1)

        log.debug(f"Fetching running builds from {jenkins_url}")
        running_builds = jenkins.server.get_running_builds()
        for build in running_builds:
            build_name = "{}-{}-{}".format(silo, build.get("name"), build.get("number"))
            log.debug(f"    {build_name}")
            builds.append(build_name)

    log.debug("Active stacks")
    for stack in stacks:
        if stack.status == "CREATE_COMPLETE" or stack.status == "CREATE_FAILED" or stack.status == "DELETE_FAILED":
            log.debug(f"    {stack.stack_name}")

            if stack.status == "DELETE_FAILED":
                cloud.pprint(stack)

            if stack.stack_name not in builds:
                log.debug("        >>>> Marked for deletion <<<<")
                delete(os_cloud, stack.stack_name)

        else:
            continue
