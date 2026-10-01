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
from lftools_uv.typer_apps.zulip.detail import render_detail_fields, render_group_sections
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


@group_app.command("show")
def group_show(
    ctx: typer.Context,
    group: str | None = typer.Argument(
        None,
        help="Group name shorthand for --group-name; numeric-looking values are names.",
    ),
    group_name: str | None = typer.Option(
        None,
        "--group-name",
        help="Target group by name (case-insensitive).",
    ),
    group_id: str | None = typer.Option(
        None,
        "--group-id",
        help="Target group by numeric ID.",
    ),
    no_resolve: bool = typer.Option(
        False,
        "--no-resolve",
        help="Skip extra lookup calls and render raw IDs where possible. Target lookup still runs as needed.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """Show complete details for one user group."""
    targets = sum(value is not None for value in (group, group_name, group_id))
    if targets != 1:
        emit_error("Exactly one group target is required")
        raise typer.Exit(code=1)
    effective_name = group if group is not None else group_name
    parsed_group_id: int | None = None
    if group_id is not None:
        try:
            parsed_group_id = int(group_id)
        except ValueError:
            emit_error("--group-id must be a numeric group ID.")
            raise typer.Exit(code=1) from None
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        detail = zulip_cli.get_group_detail(
            client,
            group_name=effective_name,
            group_id=parsed_group_id,
            resolve=not no_resolve,
        )
    except ZulipAmbiguityError as exc:
        emit_error(str(exc))
        for match in exc.matches:
            typer.echo(
                f"  - {match.get('name', '<unknown>')} (group_id={match.get('group_id', match.get('id'))})",
                err=True,
            )
        raise typer.Exit(code=1) from exc
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc
    if options.get("json_output"):
        emit_json(zulip_cli.public_detail_payload(detail))
        return
    render_detail_fields(detail, "group")
    render_group_sections(detail, resolve=not no_resolve)
