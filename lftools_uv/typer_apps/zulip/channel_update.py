# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip channel update`` and ``zulip channel topic-policy`` commands."""

from __future__ import annotations

from typing import cast

import typer

from lftools_uv.api.endpoints.zulip import ChannelType, IdMode, TopicPolicy, ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import channel_app
from lftools_uv.typer_apps.zulip.helpers import (
    _validate_single_channel_target,
    emit_error,
    emit_json,
    handle_zulip_error,
)


@channel_app.command("update")
def channel_update(  # noqa: PLR0913 - CLI parity with contract
    ctx: typer.Context,
    channel: str | None = typer.Argument(
        None,
        help="Channel name (optional if --channel-id is given).",
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        help="Target channel by numeric ID.",
    ),
    new_name: str | None = typer.Option(
        None,
        "--name",
        help="New channel name.",
    ),
    description: str | None = typer.Option(
        None,
        "--description",
        help="New channel description.",
    ),
    channel_type: str | None = typer.Option(
        None,
        "--type",
        help="New channel type: public, private, or web-public.",
    ),
    topic_policy: str | None = typer.Option(
        None,
        "--topic-policy",
        help="New topic policy: allow, deny, or follow-default.",
    ),
    subscribe: list[str] = typer.Option(
        [],
        "--subscribe",
        help="User identifier(s) to retain access on type-to-private (repeatable).",
    ),
    by_email: bool = typer.Option(False, "--by-email", help="Identify --subscribe users by email."),
    by_id: bool = typer.Option(False, "--by-id", help="Identify --subscribe users by numeric ID."),
    by_name: bool = typer.Option(False, "--by-name", help="Identify --subscribe users by full name."),
    allow_group: str | None = typer.Option(
        None,
        "--allow-group",
        help="Group(s) allowed to join. Comma-separated names; use 'id:NUM' for ID lookup.",
    ),
    can_remove_subscribers_group: str | None = typer.Option(
        None,
        "--can-remove-subscribers-group",
        help="Group(s) permitted to remove subscribers (group-setting syntax).",
    ),
    folder: str | None = typer.Option(
        None,
        "--folder",
        help="Folder name, 'id:NUM', or 'none' to clear the assignment.",
    ),
    folder_id: str | None = typer.Option(
        None,
        "--folder-id",
        help="Clear-only compatibility form; only 0 is accepted.",
    ),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Include archived channels when resolving the target.",
    ),
) -> None:
    """Update channel settings.

    Implements US8 (FR-004). Exactly one of ``[channel]`` or
    ``--channel-id`` must be supplied. The API layer
    (:func:`update_channel`) enforces the at-least-one-setting
    constraint and surfaces it as a :class:`ZulipValidationError`; this
    CLI layer validates flag-shape constraints (choice values, the
    ``--by-*`` mutex, and ``--subscribe`` requiring an id-mode) before
    contacting the server so that obvious errors are reported quickly.
    """
    _validate_single_channel_target(channel, channel_id)

    parsed_channel_id: int | None = None
    if channel_id is not None:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            emit_error("--channel-id must be a numeric channel ID.")
            raise typer.Exit(code=1) from None

    # Local at-least-one-setting check so the user-facing error is
    # presented before any network calls are made; the API layer also
    # enforces the same constraint as a defence-in-depth check.
    any_setting = any(
        v is not None
        for v in (
            new_name,
            description,
            channel_type,
            topic_policy,
            allow_group,
            can_remove_subscribers_group,
            folder,
            folder_id,
        )
    ) or bool(subscribe)
    if not any_setting:
        emit_error(
            "channel update requires at least one setting to change "
            "(--name, --description, --type, --topic-policy, --allow-group, "
            "--folder, --subscribe, or --can-remove-subscribers-group)"
        )
        raise typer.Exit(code=1)

    if folder is not None and folder_id is not None:
        emit_error("Specify only one of --folder or --folder-id")
        raise typer.Exit(code=1)

    parsed_folder_id: int | None = None
    folder_id_specified = False
    if folder_id is not None:
        try:
            parsed_clear_id = int(folder_id)
        except ValueError:
            emit_error("--folder-id must be 0 to clear the folder assignment; use --folder id:N to assign by ID")
            raise typer.Exit(code=1) from None
        if parsed_clear_id != 0:
            emit_error("--folder-id only accepts 0 to clear; use --folder id:N to assign a folder")
            raise typer.Exit(code=1)
        folder_id_specified = True

    # Validate --type choice locally so the error is presented before
    # any network calls are made.
    valid_types = {"public", "private", "web-public"}
    if channel_type is not None and channel_type not in valid_types:
        emit_error(f"Invalid --type {channel_type!r}; expected one of {', '.join(sorted(valid_types))}")
        raise typer.Exit(code=1)

    valid_policies = {"allow", "deny", "follow-default"}
    if topic_policy is not None and topic_policy not in valid_policies:
        emit_error(f"Invalid --topic-policy {topic_policy!r}; expected one of {', '.join(sorted(valid_policies))}")
        raise typer.Exit(code=1)

    # Validate --by-* mutex: at most one, and required when --subscribe
    # is used.
    by_count = sum(1 for v in (by_email, by_id, by_name) if v)
    if by_count > 1:
        emit_error("Specify only one of --by-email, --by-id, --by-name")
        raise typer.Exit(code=1)
    if subscribe and channel_type != "private":
        emit_error("--subscribe is only valid when using --type private")
        raise typer.Exit(code=1)
    if subscribe and by_count == 0:
        emit_error("--subscribe requires one of --by-email, --by-id, --by-name")
        raise typer.Exit(code=1)
    user_id_mode: str | None = None
    if by_email:
        user_id_mode = "email"
    elif by_id:
        user_id_mode = "id"
    elif by_name:
        user_id_mode = "name"

    options = ctx.obj or {}
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        if folder is not None:
            parsed_folder_id = zulip_cli.resolve_channel_folder_token(client, folder)
            folder_id_specified = True
        result = zulip_cli.update_channel(
            client,
            name=channel,
            channel_id=parsed_channel_id,
            new_name=new_name,
            description=description,
            channel_type=cast(ChannelType | None, channel_type),
            topic_policy=cast(TopicPolicy | None, topic_policy),
            subscribe_user_specs=list(subscribe) if subscribe else None,
            user_id_mode=cast(IdMode | None, user_id_mode),
            allow_group=allow_group,
            can_remove_subscribers_group=can_remove_subscribers_group,
            folder_id=parsed_folder_id,
            folder_id_specified=folder_id_specified,
            include_archived=include_archived,
        )
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        typer.echo(f"Updated channel '{result['channel_name']}' (id={result['channel_id']})")


@channel_app.command("topic-policy")
def channel_topic_policy(
    ctx: typer.Context,
    channel: str | None = typer.Argument(
        None,
        help="Channel name (optional if --channel-id is given).",
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        help="Target channel by numeric ID.",
    ),
    policy: str | None = typer.Option(
        None,
        "--policy",
        help="Topic policy: allow, deny, or follow-default.",
    ),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Include archived channels when resolving the target.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of text.",
        hidden=True,
    ),
) -> None:
    """View or set a channel's topic editing policy."""
    _validate_single_channel_target(channel, channel_id)

    parsed_channel_id: int | None = None
    if channel_id is not None:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            emit_error("--channel-id must be a numeric channel ID.")
            raise typer.Exit(code=1) from None

    valid_policies = {"allow", "deny", "follow-default"}
    if policy is not None and policy not in valid_policies:
        emit_error(f"Invalid --policy {policy!r}; expected one of {', '.join(sorted(valid_policies))}")
        raise typer.Exit(code=1)

    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True

    target: str | int
    if parsed_channel_id is not None:
        target = parsed_channel_id
    else:
        assert channel is not None
        target = channel

    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        if policy is None:
            result = zulip_cli.get_topic_policy(client, target, include_archived=include_archived)
        else:
            result = zulip_cli.set_topic_policy(
                client,
                target,
                cast(TopicPolicy, policy),
                include_archived=include_archived,
            )
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    elif policy is None:
        typer.echo(result["topic_policy"])
    else:
        typer.echo(
            f"Updated topic policy for '{result['channel_name']}' "
            f"(id={result['channel_id']}) to {result['topic_policy']}"
        )
