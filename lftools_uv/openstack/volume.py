# -*- code: utf-8 -*-
# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""volume related sub-commands for openstack command."""

from __future__ import annotations

__author__ = "Thanh Ha"

import builtins
import logging
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

# aislop-ignore-file hallucinated-import -- the declared openstacksdk dependency provides the `openstack` import package
import openstack
import openstack.connection
from openstack.cloud.exc import OpenStackCloudException
from openstack.exceptions import NotFoundException

from lftools_uv.output import echo

log = logging.getLogger(__name__)

# openstacksdk waits for a volume to disappear with no time limit by
# default, so a volume stuck in error_deleting would hang the command.
VOLUME_DELETE_TIMEOUT_SECONDS = 600


def _filter_volumes(volumes: builtins.list[Any], days: int = 0) -> builtins.list[Any]:
    """Filter volume data and return list."""
    filtered = []
    for volume in volumes:
        if days and (
            datetime.strptime(volume.created_at, "%Y-%m-%dT%H:%M:%S.%f") >= datetime.now() - timedelta(days=days)
        ):
            continue

        filtered.append(volume)
    return filtered


def list(os_cloud: str, days: int = 0) -> None:
    """List volumes found according to parameters."""
    cloud = openstack.connection.from_config(cloud=os_cloud)
    volumes = cloud.list_volumes()

    filtered_volumes = _filter_volumes(volumes, days)
    for volume in filtered_volumes:
        echo(volume.name)


def cleanup(os_cloud: str, days: int = 0) -> None:
    """Remove volume from cloud.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg int days: Filter volumes that are older than number of days.

    A delete that fails is logged and the remaining volumes are still
    removed; the command then exits 1.
    """

    def _remove_volumes_from_cloud(volumes: builtins.list[Any], cloud: Any) -> builtins.list[str]:
        log.info("Removing %d volumes from %s.", len(volumes), cloud.config.name)
        failed: builtins.list[str] = []
        for volume in volumes:
            try:
                # Delete by id, not name. Names are not unique, and a duplicate
                # name made the lookup ambiguous, which skipped the volume on
                # every run.
                result = cloud.delete_volume(volume.id, timeout=VOLUME_DELETE_TIMEOUT_SECONDS)
            except OpenStackCloudException as e:
                # Deleting by id cannot raise these duplicate-name errors. The
                # branch stays as a safety net, so keep it and its tests.
                error_msg = str(e)
                if error_msg.startswith("Multiple matches found for") or error_msg.startswith(
                    "More than one Volume exists with the name"
                ):
                    log.warning("%s. Skipping volume...", error_msg)
                    continue
                log.error(
                    'Failed to remove "%s" (%s) from %s: %s', volume.name, volume.id, cloud.config.name, error_msg
                )
                failed.append(volume.id)
                continue

            if not result:
                log.warning(
                    'Failed to remove "%s" (%s) from %s. Possibly already deleted.',
                    volume.name,
                    volume.id,
                    cloud.config.name,
                )
            else:
                log.info('Removed "%s" (%s) from %s.', volume.name, volume.id, cloud.config.name)
        return failed

    cloud = openstack.connection.from_config(cloud=os_cloud)
    volumes = cloud.list_volumes()
    filtered_volumes = _filter_volumes(volumes, days)
    failed = _remove_volumes_from_cloud(filtered_volumes, cloud)
    if failed:
        log.error("Failed to remove %d volume(s): %s", len(failed), ", ".join(failed))
        sys.exit(1)


def remove(os_cloud: str, volume_id: str, minutes: int = 0) -> None:
    """Remove a volume from cloud.

    :arg str os_cloud: Cloud name as defined in OpenStack clouds.yaml.
    :arg str volume_id: Volume ID to delete
    :arg int minutes: Only delete volume if it is older than number of minutes.
    """
    cloud = openstack.connection.from_config(cloud=os_cloud)
    try:
        volume = cloud.get_volume_by_id(volume_id)
    except NotFoundException:
        volume = None

    if not volume:
        log.error("Volume %s not found.", volume_id)
        sys.exit(1)

    if datetime.strptime(volume.created_at, "%Y-%m-%dT%H:%M:%S.%f").replace(tzinfo=UTC) >= datetime.now(
        UTC
    ) - timedelta(minutes=minutes):
        log.warning('volume "%s" (%s) is not older than %d minutes.', volume.name, volume.id, minutes)
        return

    try:
        cloud.delete_volume(volume.id, timeout=VOLUME_DELETE_TIMEOUT_SECONDS)
    except OpenStackCloudException as e:
        log.error('Failed to remove volume "%s" (%s): %s', volume.name, volume.id, e)
        sys.exit(1)
