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

from lftools_uv.api.endpoints.zulip import ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import user_app
from lftools_uv.typer_apps.zulip.helpers import emit_json, emit_table, handle_zulip_error


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
    """List users on the Zulip server (US2)."""
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
