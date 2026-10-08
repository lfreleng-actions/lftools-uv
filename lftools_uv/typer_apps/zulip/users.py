# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip user`` command group (US2)."""

from __future__ import annotations

from typing import Any

import typer

from lftools_uv.api.endpoints.zulip import ZulipAmbiguityError, ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import user_app
from lftools_uv.typer_apps.zulip.detail import render_detail_fields, render_user_sections
from lftools_uv.typer_apps.zulip.helpers import _resolve_id_mode, emit_error, emit_json, emit_table, handle_zulip_error


@user_app.command("list")
def user_list(
    ctx: typer.Context,
    include_bots: bool = typer.Option(
        False,
        "--include-bots",
        help="Include bot accounts in the output.",
    ),
    include_deactivated: bool = typer.Option(
        False,
        "--include-deactivated",
        help="Include deactivated user accounts in the output.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """List users on the Zulip server."""
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        users = zulip_cli.list_users(
            client,
            include_bots=include_bots,
            include_deactivated=include_deactivated,
        )
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json({"users": users})
        return

    headers = ["Full Name", "Email", "User ID"]
    if include_bots:
        headers.append("Bot")
    if include_deactivated:
        headers.append("Deactivated")
    rows: list[list[Any]] = []
    for user in users:
        row: list[Any] = [user["full_name"], user["email"], user["user_id"]]
        if include_bots:
            row.append("yes" if user["is_bot"] else "no")
        if include_deactivated:
            # The contract names the column "Deactivated" so that a
            # "yes" cell consistently flags the abnormal state.
            row.append("yes" if not user["is_active"] else "no")
        rows.append(row)
    emit_table(rows, headers)


@user_app.command("show")
def user_show(
    ctx: typer.Context,
    user: str | None = typer.Argument(None, help="Email, user ID, or full name according to the selected mode."),
    by_email: bool = typer.Option(False, "--by-email", help="Resolve USER by email."),
    by_id: bool = typer.Option(False, "--by-id", help="Resolve USER by numeric user ID."),
    by_name: bool = typer.Option(False, "--by-name", help="Resolve USER by full name."),
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
    """Show complete details for one user account."""
    if user is None:
        emit_error("USER is required")
        raise typer.Exit(code=1)
    mode = _resolve_id_mode(by_email, by_id, by_name)
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        detail = zulip_cli.get_user_detail(client, user, mode=mode, resolve=not no_resolve)
    except ZulipAmbiguityError as exc:
        emit_error(str(exc))
        for match in exc.matches:
            typer.echo(
                f"  - {match.get('full_name', '<unknown>')} "
                f"(user_id={match.get('user_id')}, email={match.get('email', '')})",
                err=True,
            )
        raise typer.Exit(code=1) from exc
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc
    if options.get("json_output"):
        emit_json(zulip_cli.public_detail_payload(detail))
        return
    render_detail_fields(detail, "user")
    render_user_sections(detail, resolve=not no_resolve)
