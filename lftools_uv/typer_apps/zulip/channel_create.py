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


@channel_app.command("create")
def channel_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Channel name"),
    description: str = typer.Option(
        "",
        "--description",
        help="Channel description.",
    ),
    channel_type: str = typer.Option(
        "public",
        "--type",
        help="Channel type: public, web-public, or private.",
    ),
    subscribe: list[str] | None = typer.Option(
        None,
        "--subscribe",
        help="User identifier(s) to subscribe on creation (repeatable).",
    ),
    by_email: bool = typer.Option(
        False,
        "--by-email",
        help="Identify users by email.",
    ),
    by_id: bool = typer.Option(
        False,
        "--by-id",
        help="Identify users by numeric ID.",
    ),
    by_name: bool = typer.Option(
        False,
        "--by-name",
        help="Identify users by full name.",
    ),
    allow_group: str | None = typer.Option(
        None,
        "--allow-group",
        help="Comma-separated groups allowed to join; use 'id:NUM' for ID lookup.",
    ),
    can_remove_subscribers_group: str | None = typer.Option(
        None,
        "--can-remove-subscribers-group",
        help="Comma-separated groups that can remove subscribers; use 'id:NUM' for ID lookup.",
    ),
    folder: str | None = typer.Option(
        None,
        "--folder",
        help="Folder name, 'id:NUM', or 'none' for no folder.",
    ),
    announce: bool = typer.Option(
        False,
        "--announce",
        help="Post an announcement when creating the channel.",
    ),
    no_announce: bool = typer.Option(
        False,
        "--no-announce",
        help="Suppress announcement when creating the channel.",
    ),
    topic_policy: str | None = typer.Option(
        None,
        "--topic-policy",
        help="Topic policy: allow, deny, or follow-default.",
    ),
) -> None:
    """Create a new Zulip channel (US4).

    Creates a channel with the specified name and options. Private channels
    require at least one --subscribe user or a non-Nobody --allow-group.
    """
    from lftools_uv.api.endpoints.zulip import (
        ZulipLockoutError,
        ZulipValidationError,
        create_channel,
        resolve_groups,
        resolve_users,
    )

    options = ctx.obj or {}

    if channel_type not in ("public", "private", "web-public"):
        emit_error(f"Invalid channel type: {channel_type!r}. Valid types: public, private, web-public")
        raise typer.Exit(code=1)

    if announce and no_announce:
        emit_error("--announce and --no-announce are mutually exclusive")
        raise typer.Exit(code=1)

    # Validate topic-policy if provided
    if topic_policy is not None and topic_policy not in ("allow", "deny", "follow-default"):
        emit_error(f"Invalid --topic-policy value: {topic_policy!r}. Valid values: allow, deny, follow-default")
        raise typer.Exit(code=1)

    id_mode = _validate_id_mode_flags(by_email, by_id, by_name, subscribe)

    # Determine announce value
    announce_value: bool | None = None
    if announce:
        announce_value = True
    elif no_announce:
        announce_value = False

    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))

        # Resolve users if --subscribe is provided
        subscribe_user_ids: list[int] | None = None
        if subscribe and id_mode:
            resolved_users = resolve_users(client, subscribe, mode=id_mode)  # type: ignore[arg-type]
            subscribe_user_ids = [u["user_id"] for u in resolved_users]

        # Resolve allow-group if provided
        # For private channels, resolve_groups with allow_nobody=False will raise
        # ZulipLockoutError if the only group is Nobody - this is the lockout check
        allow_group_value = None
        if allow_group:
            allow_nobody = channel_type != "private"
            _, allow_group_value = resolve_groups(client, allow_group, allow_nobody=allow_nobody)

        # Resolve can-remove-subscribers-group if provided
        can_remove_value = None
        if can_remove_subscribers_group:
            _, can_remove_value = resolve_groups(client, can_remove_subscribers_group)

        folder_id: int | None = None
        folder_id_specified = folder is not None
        if folder is not None:
            folder_id = zulip_cli.resolve_channel_folder_token(client, folder)

        result = create_channel(
            client,
            name=name,
            description=description,
            channel_type=channel_type,  # type: ignore[arg-type]
            subscribe_user_ids=subscribe_user_ids,
            allow_group_value=allow_group_value,
            can_remove_subscribers_group_value=can_remove_value,
            announce=announce_value,
            topic_policy=topic_policy,
            folder_id=folder_id,
            folder_id_specified=folder_id_specified,
        )
    except ZulipAmbiguityError as exc:
        emit_error(str(exc))
        for match in exc.matches:
            typer.echo(
                f"  - {match.get('full_name', match.get('name', '<unknown>'))} "
                f"(id={match.get('user_id', match.get('id', match.get('group_id')))})",
                err=True,
            )
        raise typer.Exit(code=1) from exc
    except (ZulipLockoutError, ZulipValidationError) as exc:
        emit_error(str(exc))
        raise typer.Exit(code=1) from exc
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
        # Exit with code 1 if partial failure
        if result.get("status") == "partial":
            raise typer.Exit(code=1)
        return

    typer.echo(f"Created {channel_type} channel '{name}' (ID: {result.get('channel_id')})")
    # Emit warnings if present
    if result.get("warnings"):
        for warning in result["warnings"]:
            emit_warning(warning)
        raise typer.Exit(code=1)
