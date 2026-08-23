# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip channel archive`` and ``zulip channel unarchive`` commands."""

from __future__ import annotations

import typer

from lftools_uv.api.endpoints.zulip import ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import channel_app
from lftools_uv.typer_apps.zulip.helpers import (
    _validate_single_channel_target,
    emit_error,
    emit_json,
    handle_zulip_error,
)


@channel_app.command("archive")
def channel_archive(
    ctx: typer.Context,
    channel: str | None = typer.Argument(
        None,
        metavar="CHANNEL",
        help="Channel name (mutually exclusive with --channel-id).",
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        help="Target the channel by numeric stream ID.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="Confirm archival (required).",
    ),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Search archived channels when resolving the target.",
    ),
) -> None:
    """Archive (deactivate) a Zulip channel.

    Requires ``--yes`` to perform the destructive operation. Resolves
    the channel by name (positional) or by numeric ID (``--channel-id``)
    — exactly one must be supplied. Idempotent: an already-archived
    channel surfaced via ``--include-archived`` is reported as success
    without a redundant API call.
    """
    _validate_single_channel_target(channel, channel_id)
    channel_name = channel.strip() if isinstance(channel, str) else None

    # --yes is mandatory for this destructive operation.
    if not yes:
        emit_error("Refusing to archive without --yes. Re-run with --yes to confirm.")
        raise typer.Exit(code=1)

    options = ctx.obj or {}
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    target: str | int
    if channel_id is not None:
        try:
            target = int(channel_id)
        except ValueError:
            emit_error("--channel-id must be a numeric channel ID.")
            raise typer.Exit(code=1) from None
    else:
        assert channel_name is not None  # narrow for the type checker
        target = channel_name

    try:
        result = zulip_cli.archive_channel(client, target, include_archived=include_archived)
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        typer.echo(f"Archived channel '{result['channel_name']}' (id={result['channel_id']}).")


@channel_app.command("unarchive")
def channel_unarchive(
    ctx: typer.Context,
    channel: str | None = typer.Argument(
        None,
        help="Channel name (case-insensitive). Mutually exclusive with --channel-id.",
        show_default=False,
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        help="Target channel by numeric id. Mutually exclusive with the positional name.",
    ),
    yes: bool = typer.Option(
        False,
        "--yes",
        help="REQUIRED. Confirm reactivation of the channel.",
    ),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Search archived channels (typically required to locate a previously archived target).",
    ),
) -> None:
    """Reactivate (unarchive) a previously archived Zulip channel.

    Requires explicit ``--yes`` confirmation. When the target channel is
    archived you will typically also need ``--include-archived`` so that
    the name/ID resolves; without it the CLI emits a helpful FR-018
    message pointing at the flag.
    """
    _validate_single_channel_target(channel, channel_id)

    if not yes:
        emit_error("Refusing to unarchive without explicit confirmation. Re-run with --yes to proceed.")
        raise typer.Exit(code=1)

    parsed_channel_id: int | None = None
    if channel_id is not None:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            emit_error("--channel-id must be a numeric channel ID.")
            raise typer.Exit(code=1) from None

    options = ctx.obj or {}
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        payload = zulip_cli.unarchive_channel(
            client,
            channel=channel,
            channel_id=parsed_channel_id,
            include_archived=include_archived,
        )
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(payload)
        return

    typer.echo(f"Unarchived channel '{payload['channel_name']}' (id={payload['channel_id']}).")
