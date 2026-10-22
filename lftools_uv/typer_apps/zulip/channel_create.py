# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip channel create`` command (US4)."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import typer

from lftools_uv.api.endpoints.zulip import ZulipAmbiguityError, ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import channel_app
from lftools_uv.typer_apps.zulip.helpers import (
    _validate_id_mode_flags,
    emit_error,
    emit_json,
    emit_warning,
    handle_zulip_error,
)

_NAME = typer.Argument(..., help="Channel name")
_DESCRIPTION = typer.Option("", "--description", help="Channel description.")
_TYPE = typer.Option("public", "--type", help="Channel type: public, web-public, or private.")
_SUBSCRIBE = typer.Option(None, "--subscribe", help="User identifier(s) to subscribe on creation (repeatable).")
_BY_EMAIL = typer.Option(False, "--by-email", help="Identify users by email.")
_BY_ID = typer.Option(False, "--by-id", help="Identify users by numeric ID.")
_BY_NAME = typer.Option(False, "--by-name", help="Identify users by full name.")
_ALLOW_GROUP = typer.Option(
    None,
    "--allow-group",
    help="Comma-separated groups allowed to join; use 'id:NUM' for ID lookup.",
)
_CAN_REMOVE = typer.Option(
    None,
    "--can-remove-subscribers-group",
    help="Comma-separated groups that can remove subscribers; use 'id:NUM' for ID lookup.",
)
_CAN_ADD = typer.Option(
    None,
    "--can-add-subscribers-group",
    help="Comma-separated groups that can add subscribers; use 'id:NUM' for ID lookup.",
)
_CAN_ADMINISTER = typer.Option(
    None,
    "--can-administer-channel-group",
    help="Comma-separated groups that can administer the channel; use 'id:NUM' for ID lookup.",
)
_CAN_SEND = typer.Option(
    None,
    "--can-send-message-group",
    help="Comma-separated groups that can send messages; use 'id:NUM' for ID lookup.",
)
_FOLDER = typer.Option(None, "--folder", help="Folder name, 'id:NUM', or 'none' for no folder.")
_ANNOUNCE = typer.Option(False, "--announce", help="Post an announcement when creating the channel.")
_NO_ANNOUNCE = typer.Option(False, "--no-announce", help="Suppress announcement when creating the channel.")
_TOPIC_POLICY = typer.Option(None, "--topic-policy", help="Topic policy: allow, deny, or follow-default.")

# Group options in the order their feature levels are checked, with the
# key used for each in the resolved group-setting values.
_GATED_GROUP_FEATURES = (
    ("add", "can-add-subscribers-group"),
    ("administer", "can-administer-channel-group"),
    ("send", "can-send-message-group"),
)


@dataclass(frozen=True)
class _CreateInputs:
    """The validated ``channel create`` command line."""

    name: str
    description: str
    channel_type: str
    subscribe: list[str] | None
    id_mode: str | None
    groups: dict[str, str | None]
    folder: str | None
    announce: bool | None
    topic_policy: str | None


def _validate_flags(channel_type: str, announce: bool, no_announce: bool, topic_policy: str | None) -> None:
    """Reject flag values and combinations the command cannot act on."""
    if channel_type not in ("public", "private", "web-public"):
        emit_error(f"Invalid channel type: {channel_type!r}. Valid types: public, private, web-public")
        raise typer.Exit(code=1)

    if announce and no_announce:
        emit_error("--announce and --no-announce are mutually exclusive")
        raise typer.Exit(code=1)

    if topic_policy is not None and topic_policy not in ("allow", "deny", "follow-default"):
        emit_error(f"Invalid --topic-policy value: {topic_policy!r}. Valid values: allow, deny, follow-default")
        raise typer.Exit(code=1)


def _create(options: dict[str, Any], inputs: _CreateInputs) -> dict[str, Any]:
    """Resolve users, groups and folder, then create the channel."""
    from lftools_uv.api.endpoints.zulip import (
        FEATURE_LEVELS,
        check_feature_level,
        create_channel,
        resolve_group_setting_specs,
        resolve_users,
    )

    client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))

    subscribe_user_ids: list[int] | None = None
    if inputs.subscribe and inputs.id_mode:
        resolved_users = resolve_users(client, inputs.subscribe, mode=inputs.id_mode)  # type: ignore[arg-type]
        subscribe_user_ids = [u["user_id"] for u in resolved_users]

    for key, feature in _GATED_GROUP_FEATURES:
        if inputs.groups[key] is not None:
            check_feature_level(client, FEATURE_LEVELS[feature], feature)

    allow_nobody = {"allow": inputs.channel_type != "private" or bool(subscribe_user_ids)}
    group_values = resolve_group_setting_specs(
        client,
        {key: (spec, allow_nobody.get(key, True)) for key, spec in inputs.groups.items()},
    )

    folder_id: int | None = None
    if inputs.folder is not None:
        folder_id = zulip_cli.resolve_channel_folder_token(client, inputs.folder)

    return create_channel(
        client,
        name=inputs.name,
        description=inputs.description,
        channel_type=inputs.channel_type,  # type: ignore[arg-type]
        subscribe_user_ids=subscribe_user_ids,
        allow_group_value=group_values["allow"][1],
        can_remove_subscribers_group_value=group_values["remove"][1],
        can_add_subscribers_group_value=group_values["add"][1],
        can_administer_channel_group_value=group_values["administer"][1],
        can_send_message_group_value=group_values["send"][1],
        announce=inputs.announce,
        topic_policy=inputs.topic_policy,
        folder_id=folder_id,
        folder_id_specified=inputs.folder is not None,
    )


def _report_failure(exc: ZulipError) -> typer.Exit:
    """Report a failed create and return the ``typer.Exit`` to raise."""
    from lftools_uv.api.endpoints.zulip import ZulipLockoutError, ZulipValidationError

    if isinstance(exc, ZulipAmbiguityError):
        emit_error(str(exc))
        for match in exc.matches:
            typer.echo(
                f"  - {match.get('full_name', match.get('name', '<unknown>'))} "
                f"(id={match.get('user_id', match.get('id', match.get('group_id')))})",
                err=True,
            )
        return typer.Exit(code=1)
    if isinstance(exc, (ZulipLockoutError, ZulipValidationError)):
        emit_error(str(exc))
        return typer.Exit(code=1)
    return handle_zulip_error(exc)


def _report_result(options: dict[str, Any], result: dict[str, Any], inputs: _CreateInputs) -> None:
    """Print the create outcome; a partial outcome exits 1."""
    if options.get("json_output"):
        emit_json(result)
        if result.get("status") == "partial":
            raise typer.Exit(code=1)
        return

    typer.echo(f"Created {inputs.channel_type} channel '{inputs.name}' (ID: {result.get('channel_id')})")
    if result.get("warnings"):
        for warning in result["warnings"]:
            emit_warning(warning)
        raise typer.Exit(code=1)


@channel_app.command("create")
def channel_create(
    ctx: typer.Context,
    name: str = _NAME,
    description: str = _DESCRIPTION,
    channel_type: str = _TYPE,
    subscribe: list[str] | None = _SUBSCRIBE,
    by_email: bool = _BY_EMAIL,
    by_id: bool = _BY_ID,
    by_name: bool = _BY_NAME,
    allow_group: str | None = _ALLOW_GROUP,
    can_remove_subscribers_group: str | None = _CAN_REMOVE,
    can_add_subscribers_group: str | None = _CAN_ADD,
    can_administer_channel_group: str | None = _CAN_ADMINISTER,
    can_send_message_group: str | None = _CAN_SEND,
    folder: str | None = _FOLDER,
    announce: bool = _ANNOUNCE,
    no_announce: bool = _NO_ANNOUNCE,
    topic_policy: str | None = _TOPIC_POLICY,
) -> None:
    """Create a new Zulip channel.

    Creates a channel with the specified name and options. Private channels
    require at least one --subscribe user or a non-Nobody --allow-group.
    """
    options = ctx.obj or {}
    _validate_flags(channel_type, announce, no_announce, topic_policy)
    inputs = _CreateInputs(
        name=name,
        description=description,
        channel_type=channel_type,
        subscribe=subscribe,
        id_mode=_validate_id_mode_flags(by_email, by_id, by_name, subscribe),
        groups={
            "allow": allow_group,
            "remove": can_remove_subscribers_group,
            "add": can_add_subscribers_group,
            "administer": can_administer_channel_group,
            "send": can_send_message_group,
        },
        folder=folder,
        announce=True if announce else (False if no_announce else None),
        topic_policy=topic_policy,
    )
    try:
        result = _create(options, inputs)
    except ZulipError as exc:
        raise _report_failure(exc) from exc
    _report_result(options, result, inputs)
