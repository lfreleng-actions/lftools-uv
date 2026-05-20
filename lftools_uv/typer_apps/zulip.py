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

This module also exposes shared CLI helpers used by the per-command
modules added in later phases: zuliprc path normalization, table/JSON
output formatting, and consistent error display.

See ``specs/001-zulip-channel-mgmt/`` for the full feature design.
"""

from __future__ import annotations

import json
import logging
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any

import typer
from tabulate import tabulate

from lftools_uv.api.endpoints.zulip import (
    ZulipError,
    get_client,
    list_channels,
    list_groups,
    list_users,
    zulip_available,
)

log = logging.getLogger(__name__)


#: Canonical error message displayed when the ``zulip`` extra is missing
#: (FR-022). Matches the wording in ``contracts/cli-commands.md``.
MISSING_EXTRA_MESSAGE = 'Zulip support requires the zulip extra. Install with:\n  pip install "lftools-uv[zulip]"'


zulip_app = typer.Typer(
    name="zulip",
    help="Manage Zulip channels, users, and groups.",
    no_args_is_help=True,
)


# ---------------------------------------------------------------------------
# Shared option callbacks and helpers
# ---------------------------------------------------------------------------


def zuliprc_callback(value: Path | None) -> Path | None:
    """Validate the ``--zuliprc`` flag value.

    Returns the supplied path (or ``None``) unchanged so that the API
    layer can apply the FR-011 precedence chain via
    :func:`lftools_uv.api.endpoints.zulip.resolve_config`. The
    existence check is intentionally deferred to ``resolve_config`` so
    that callers see a single, consistent error message regardless of
    whether the path came from the flag or the default search order.
    """
    return value


def emit_error(message: str) -> None:
    """Write a Zulip error message to stderr.

    Centralizes the format so that all Zulip commands present errors
    identically. Always writes a trailing newline. Does NOT exit; the
    caller decides whether to raise ``typer.Exit``.
    """
    typer.echo(f"Error: {message}", err=True)


def handle_zulip_error(exc: ZulipError) -> typer.Exit:
    """Format a :class:`ZulipError` for the CLI and return ``typer.Exit``.

    Callers should ``raise`` the returned ``typer.Exit`` to abort. This
    function keeps the format consistent for every subcommand.
    """
    emit_error(str(exc))
    return typer.Exit(code=1)


def emit_table(rows: Sequence[Sequence[Any]], headers: Sequence[str]) -> None:
    """Print a human-readable table to stdout using ``tabulate``."""
    typer.echo(tabulate(list(rows), headers=list(headers)))


def emit_json(payload: Any) -> None:
    """Print a JSON payload to stdout with indent=2 (FR-008)."""
    typer.echo(json.dumps(payload, indent=2, sort_keys=False, default=str))


def mutation_result(
    *,
    status: str,
    operation: str,
    channel_id: int | None,
    channel_name: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build the standard mutation-result JSON payload.

    Schema matches ``data-model.md``: ``status``, ``channel_id``,
    ``channel_name``, ``operation`` — plus any ``extra`` fields the
    specific command needs (e.g. ``type`` for create).
    """
    payload: dict[str, Any] = {
        "status": status,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "operation": operation,
    }
    if extra:
        payload.update(extra)
    return payload


def bulk_mutation_result(
    *,
    operation: str,
    channel_id: int | None,
    channel_name: str,
    results: Iterable[dict[str, Any]],
    errors: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Build the standard bulk mutation-result JSON payload.

    Adds ``results`` and ``errors`` lists per ``contracts/cli-commands.md``.
    The overall ``status`` is derived from the contents: ``error`` when
    everything failed, ``partial`` when some succeeded and some failed,
    ``success`` otherwise.
    """
    results_list = list(results)
    errors_list = list(errors)
    if errors_list and not results_list:
        status = "error"
    elif errors_list:
        status = "partial"
    else:
        status = "success"
    return {
        "status": status,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "operation": operation,
        "results": results_list,
        "errors": errors_list,
    }


# ---------------------------------------------------------------------------
# Top-level callback (optional-dependency guard, FR-022)
# ---------------------------------------------------------------------------


@zulip_app.callback()
def zulip_callback(
    ctx: typer.Context,
    zuliprc: Path | None = typer.Option(
        None,
        "--zuliprc",
        help="Path to a zuliprc configuration file (FR-011 precedence applies).",
        callback=zuliprc_callback,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
) -> None:
    """Top-level callback for the Zulip command group.

    When the optional ``zulip`` extra is not installed, abort
    immediately with the canonical FR-022 error so that every
    subcommand presents the same guidance to the user.
    """
    ctx.obj = {
        **(ctx.obj or {}),
        "zuliprc": zuliprc,
        "json_output": json_output,
    }
    # Allow ``--help`` (including nested subcommand help) to render even
    # when the optional extra is missing. Typer sets resilient_parsing
    # while it is walking the command tree for help discovery.
    if ctx.resilient_parsing:
        return
    if ctx.invoked_subcommand is None:
        # Help / no-args path — let Typer print help without raising.
        return
    if not zulip_available():
        typer.echo(MISSING_EXTRA_MESSAGE, err=True)
        raise typer.Exit(code=1)


# ---------------------------------------------------------------------------
# US1 — channel list (T023)
# ---------------------------------------------------------------------------


channel_app = typer.Typer(
    name="channel",
    help="Manage Zulip channels.",
    no_args_is_help=True,
)
zulip_app.add_typer(channel_app, name="channel")


@channel_app.command("list")
def channel_list(
    ctx: typer.Context,
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Include archived channels in the output.",
    ),
) -> None:
    """List channels visible to the authenticated user (US1)."""
    options = ctx.obj or {}
    try:
        client = get_client(zuliprc=options.get("zuliprc"))
        channels = list_channels(client, include_archived=include_archived)
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json({"channels": channels})
        return

    headers = ["Name", "Description", "Type", "Subscribers"]
    if include_archived:
        headers.append("Status")
    rows: list[list[Any]] = []
    for c in channels:
        row: list[Any] = [
            c.get("name", ""),
            c.get("description", ""),
            c.get("type", ""),
            c.get("subscriber_count", 0),
        ]
        if include_archived:
            row.append("archived" if c.get("is_archived") else "active")
        rows.append(row)
    emit_table(rows, headers)


# ---------------------------------------------------------------------------
# US2 — user list (T024)
# ---------------------------------------------------------------------------


user_app = typer.Typer(
    name="user",
    help="Inspect Zulip users.",
    no_args_is_help=True,
)
zulip_app.add_typer(user_app, name="user")


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
) -> None:
    """List users on the Zulip server (US2)."""
    options = ctx.obj or {}
    try:
        client = get_client(zuliprc=options.get("zuliprc"))
        users = list_users(
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


# ---------------------------------------------------------------------------
# `zulip group` sub-app (US3)
# ---------------------------------------------------------------------------


group_app = typer.Typer(
    name="group",
    help="List and inspect Zulip user groups.",
    no_args_is_help=True,
)
zulip_app.add_typer(group_app, name="group")


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
) -> None:
    """List user groups on the Zulip server.

    Shows both custom user groups and built-in system role groups
    (Owners, Administrators, Moderators, Full Members, Members,
    Everyone, Nobody). All listed groups are valid inputs for the
    ``--allow-group`` and ``--can-remove-subscribers-group`` flags on
    channel create/update.
    """
    options = ctx.obj or {}
    try:
        client = get_client(zuliprc=options.get("zuliprc"))
        groups = list_groups(
            client,
            group_name=group_name,
            group_id=group_id,
        )
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
