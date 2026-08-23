# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip group`` command group."""

from __future__ import annotations

import typer

from lftools_uv.api.endpoints.zulip import ZulipAmbiguityError, ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import group_app
from lftools_uv.typer_apps.zulip.helpers import emit_error, emit_json, emit_table, handle_zulip_error


@group_app.command("list")
def group_list(
    ctx: typer.Context,
    group_name: str | None = typer.Option(
        None,
        "--group-name",
        help="Filter by group name (case-insensitive).",
    ),
    group_id: int | None = typer.Option(
        None,
        "--group-id",
        help="Filter by numeric group ID.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """List user groups on the Zulip server.

    Shows both custom user groups and built-in system role groups
    (Owners, Administrators, Moderators, Full Members, Members,
    Everyone, Nobody), including their display names and member counts.
    """
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        groups = zulip_cli.list_groups(
            client,
            group_name=group_name,
            group_id=group_id,
        )
    except ZulipAmbiguityError as exc:
        # Render the per-spec listing of matches with IDs in addition to
        # the headline message so the user can pick one for --group-id.
        emit_error(str(exc))
        for match in exc.matches:
            typer.echo(
                f"  - {match.get('name', '<unknown>')} (group_id={match.get('group_id')})",
                err=True,
            )
        raise typer.Exit(code=1) from exc
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json({"groups": groups})
        return

    headers = ["Name", "Group ID", "Type", "Description", "Members"]
    rows = [
        [
            group.get("name", ""),
            group.get("group_id", ""),
            group.get("type", ""),
            group.get("description", ""),
            group.get("member_count", 0),
        ]
        for group in groups
    ]
    emit_table(rows, headers=headers)
