# -*- code: utf-8 -*-
# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Server related sub-commands for openstack command."""

__author__ = "Anil Belur"

import sys
from datetime import UTC, datetime, timedelta

# aislop-ignore-file hallucinated-import -- the declared openstacksdk dependency provides the `openstack` import package
import openstack
import openstack.connection
from openstack.cloud.exc import OpenStackCloudException


def _filter_servers(servers, days=0):
    """Filter server data and return list."""
    filtered = []
    for server in servers:
        if days and (
            datetime.strptime(server.created_at, "%Y-%m-%dT%H:%M:%SZ") >= datetime.now() - timedelta(days=days)
        ):
            continue

        filtered.append(server)
    return filtered


def list(os_cloud, days=0):
    """List servers found according to parameters."""
    cloud = openstack.connection.from_config(cloud=os_cloud)
    servers = cloud.list_servers()

    filtered_servers = _filter_servers(servers, days)
    for server in filtered_servers:
        print(server.name)


def cleanup(os_cloud, days=0):
    """Remove server from cloud.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg int days: Filter servers that are older than number of days.
    """

    def _remove_servers_from_cloud(servers, cloud):
        print(f"Removing {len(servers)} servers from {cloud.cloud_config.name}.")
        for server in servers:
            try:
                # Delete by id, not name. Names are not unique, and a duplicate
                # name made the lookup ambiguous, which skipped the server on
                # every run.
                result = cloud.delete_server(server.id)
            except OpenStackCloudException as e:
                # Deleting by id cannot raise these duplicate-name errors. The
                # branch stays as a safety net, so keep it and its tests.
                error_msg = str(e)
                if error_msg.startswith("Multiple matches found for") or error_msg.startswith(
                    "More than one Server exists with the name"
                ):
                    print(f"WARNING: {error_msg}. Skipping server...")
                    continue
                else:
                    print(f"ERROR: Unexpected exception: {error_msg}")
                    raise

            if not result:
                print(
                    f'WARNING: Failed to remove "{server.name}" from {cloud.cloud_config.name}. Possibly already deleted.'
                )
            else:
                print(f'Removed "{server.name}" from {cloud.cloud_config.name}.')

    cloud = openstack.connection.from_config(cloud=os_cloud)
    servers = cloud.list_servers()
    filtered_servers = _filter_servers(servers, days)
    _remove_servers_from_cloud(filtered_servers, cloud)


def remove(os_cloud, server_name, minutes=0):
    """Remove a server from cloud.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg int minutes: Only delete server if it is older than number of minutes.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)
    server = cloud.get_server(server_name)

    if not server:
        print("ERROR: Server not found.")
        sys.exit(1)

    if datetime.strptime(server.created_at, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC) >= datetime.now(UTC) - timedelta(
        minutes=minutes
    ):
        print(f'WARN: Server "{server.name}" is not older than {minutes} minutes.')
    else:
        cloud.delete_server(server.id)
