# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Read-only ``zulip channel`` commands: ``list`` and ``subscribers``."""

from __future__ import annotations

from typing import Any

import typer

from lftools_uv.api.endpoints.zulip import ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import channel_app
from lftools_uv.typer_apps.zulip.helpers import (
    _resolve_channel_target,
    emit_error,
    emit_json,
    emit_table,
    handle_zulip_error,
)


@channel_app.command("list")
def channel_list(
    ctx: typer.Context,
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Include archived channels in the output.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """List channels visible to the authenticated user (US1).

    The Channel ID column is the value to pass to ``--channel-id`` on
    other channel commands.
    """
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        channels = zulip_cli.list_channels(client, include_archived=include_archived)
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json({"channels": channels})
        return

    headers = ["Channel ID", "Name", "Description", "Type", "Subscribers"]
    if include_archived:
        headers.append("Status")
    rows: list[list[Any]] = []
    for c in channels:
        row: list[Any] = [
            c.get("stream_id", ""),
            c.get("name", ""),
            c.get("description", ""),
            c.get("type", ""),
            c.get("subscriber_count", 0),
        ]
        if include_archived:
            row.append("archived" if c.get("is_archived") else "active")
        rows.append(row)
    emit_table(rows, headers)


@channel_app.command("subscribers")
def channel_subscribers(
    ctx: typer.Context,
    channel: str | None = typer.Argument(
        None,
        help="Channel name (case-insensitive). Mutually exclusive with --channel-id.",
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        help="Target channel by numeric ID instead of name.",
    ),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Search archived channels in addition to active ones.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """List subscribers of a channel.

    Targets the channel by case-insensitive name (positional) or
    numeric ID (``--channel-id``); the two are mutually exclusive. The
    output is a table of Full Name, Email, and User ID, or — with
    ``--json`` — a payload of the form ``{"subscribers": [...]}`` per
    ``contracts/cli-commands.md``.
    """
    _resolve_channel_target(channel, channel_id)
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True

    parsed_channel_id: int | None = None
    if channel_id is not None:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            emit_error("--channel-id must be a numeric channel ID.")
            raise typer.Exit(code=1) from None

    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        subscribers = zulip_cli.list_subscribers(
            client,
            name=channel,
            channel_id=parsed_channel_id,
            include_archived=include_archived,
        )
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json({"subscribers": subscribers})
        return

    rows = [(sub.get("full_name") or "", sub.get("email") or "", sub.get("user_id")) for sub in subscribers]
    emit_table(rows, headers=("Full Name", "Email", "User ID"))
