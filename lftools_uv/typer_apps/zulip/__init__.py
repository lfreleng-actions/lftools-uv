# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer CLI app for Zulip channel management.

The ``zulip`` command group is always registered with the root CLI even
when the optional ``zulip`` extra is not installed. When the extra is
missing, any subcommand invocation produces the canonical FR-022 error
message directing the user to install the extra.

This package composes the command tree: :mod:`.apps` owns the Typer
objects, :mod:`.helpers` owns the shared output and validation helpers,
and one module per command group registers the commands themselves. The
order in which the command modules are imported below is the order the
commands appear in ``--help``, so it is pinned with ``isort`` disabled.

This module is also the namespace the API layer is reached through: the
command modules call ``zulip_cli.get_client(...)`` and friends rather
than binding those functions at import time, so that patching a name
here (as the test suite does) is observed by every command.

See ``specs/001-zulip-channel-mgmt/`` for the full feature design.
"""

from __future__ import annotations

import logging

from lftools_uv.api.endpoints.zulip import (
    ChannelType,
    IdMode,
    TopicPolicy,
    ZulipAmbiguityError,
    ZulipError,
    archive_channel,
    archive_channel_folder,
    create_channel_folder,
    get_client,
    get_topic_policy,
    list_channel_folders,
    list_channels,
    list_groups,
    list_subscribers,
    list_users,
    plan_folder_move,
    reorder_channel_folders,
    resolve_channel,
    resolve_channel_folder_reference,
    resolve_channel_folder_token,
    set_topic_policy,
    subscribe_users,
    unarchive_channel,
    unarchive_channel_folder,
    update_channel,
    update_channel_folder,
    zulip_available,
)
from lftools_uv.typer_apps.zulip.apps import (
    channel_app,
    folder_app,
    group_app,
    user_app,
    zulip_app,
    zulip_callback,
)
from lftools_uv.typer_apps.zulip.helpers import (
    MISSING_EXTRA_MESSAGE,
    _resolve_channel_target,
    _resolve_id_mode,
    _validate_id_mode_flags,
    _validate_single_channel_target,
    bulk_mutation_result,
    emit_error,
    emit_json,
    emit_table,
    emit_warning,
    handle_zulip_error,
    mutation_result,
    zuliprc_callback,
)

# isort: off
# Import order fixes the order commands are registered in, and therefore
# the order they are listed in ``--help``. Keep it stable.
from lftools_uv.typer_apps.zulip.channel_read import channel_list, channel_subscribers
from lftools_uv.typer_apps.zulip.channel_create import channel_create
from lftools_uv.typer_apps.zulip.channel_subscribe import channel_subscribe
from lftools_uv.typer_apps.zulip.channel_unsubscribe import channel_unsubscribe
from lftools_uv.typer_apps.zulip.channel_update import channel_topic_policy, channel_update
from lftools_uv.typer_apps.zulip.channel_archive import channel_archive, channel_unarchive
from lftools_uv.typer_apps.zulip.folders import (
    _current_folder_order,
    _folder_archive_common,
    folder_archive,
    folder_create,
    folder_list,
    folder_move,
    folder_unarchive,
    folder_update,
)
from lftools_uv.typer_apps.zulip.users import user_list
from lftools_uv.typer_apps.zulip.groups import group_list

# isort: on

log = logging.getLogger(__name__)

__all__ = [
    "MISSING_EXTRA_MESSAGE",
    "ChannelType",
    "IdMode",
    "TopicPolicy",
    "ZulipAmbiguityError",
    "ZulipError",
    "archive_channel",
    "archive_channel_folder",
    "bulk_mutation_result",
    "channel_app",
    "channel_archive",
    "channel_create",
    "channel_list",
    "channel_subscribe",
    "channel_subscribers",
    "channel_topic_policy",
    "channel_unarchive",
    "channel_unsubscribe",
    "channel_update",
    "create_channel_folder",
    "emit_error",
    "emit_json",
    "emit_table",
    "emit_warning",
    "folder_app",
    "folder_archive",
    "folder_create",
    "folder_list",
    "folder_move",
    "folder_unarchive",
    "folder_update",
    "get_client",
    "get_topic_policy",
    "group_app",
    "group_list",
    "handle_zulip_error",
    "list_channel_folders",
    "list_channels",
    "list_groups",
    "list_subscribers",
    "list_users",
    "log",
    "mutation_result",
    "plan_folder_move",
    "reorder_channel_folders",
    "resolve_channel",
    "resolve_channel_folder_reference",
    "resolve_channel_folder_token",
    "set_topic_policy",
    "subscribe_users",
    "unarchive_channel",
    "unarchive_channel_folder",
    "update_channel",
    "update_channel_folder",
    "user_app",
    "user_list",
    "zulip_app",
    "zulip_available",
    "zulip_callback",
    "zuliprc_callback",
]
