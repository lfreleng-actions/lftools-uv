# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip folder`` command group."""

from __future__ import annotations

from typing import Any, Literal

import typer

from lftools_uv.api.endpoints.zulip import ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import folder_app
from lftools_uv.typer_apps.zulip.helpers import (
    emit_error,
    emit_json,
    emit_table,
    handle_zulip_error,
)


@folder_app.command("list")
def folder_list(
    ctx: typer.Context,
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Include archived folders and show their status.",
    ),
    limit: int | None = typer.Option(
        None,
        "--limit",
        help="Limit the number of folders displayed.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """List channel folders visible to the authenticated user."""
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        folders = zulip_cli.list_channel_folders(client, include_archived=include_archived, limit=limit)
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json({"folders": folders})
        return

    headers = ["Folder ID", "Name", "Order", "Description"]
    if include_archived:
        headers.append("Status")
    rows: list[list[Any]] = []
    for folder in folders:
        row: list[Any] = [
            folder.get("id", ""),
            folder.get("name", ""),
            folder.get("order"),
            folder.get("description", ""),
        ]
        if include_archived:
            row.append("Archived" if folder.get("is_archived") else "Active")
        rows.append(row)
    emit_table(rows, headers)


@folder_app.command("create")
def folder_create(
    ctx: typer.Context,
    name: str = typer.Option(..., "--name", help="Folder name."),
    description: str = typer.Option(
        "",
        "--description",
        help="Folder description; defaults to empty.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of text.",
        hidden=True,
    ),
) -> None:
    """Create a channel folder; Zulip enforces admin permissions."""
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        result = zulip_cli.create_channel_folder(client, name=name, description=description)
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        typer.echo(f"Created folder '{result.get('folder_name') or name}' (ID: {result.get('folder_id')})")


@folder_app.command("update")
def folder_update(
    ctx: typer.Context,
    folder_id: int = typer.Option(..., "--folder-id", help="Target folder ID."),
    name: str | None = typer.Option(None, "--name", help="New folder name."),
    description: str | None = typer.Option(None, "--description", help="New folder description."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of text.",
        hidden=True,
    ),
) -> None:
    """Update a channel folder name and/or description."""
    if name is None and description is None:
        emit_error("folder update requires at least one of --name or --description")
        raise typer.Exit(code=1)
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        result = zulip_cli.update_channel_folder(client, folder_id=folder_id, name=name, description=description)
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        typer.echo(f"Updated folder {result.get('folder_id') or folder_id}")


def _folder_archive_common(
    ctx: typer.Context,
    *,
    folder_id: int,
    json_output: bool,
    archive: bool,
) -> None:
    """Shared implementation for folder archive/unarchive commands."""
    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        result = (
            zulip_cli.archive_channel_folder(client, folder_id)
            if archive
            else zulip_cli.unarchive_channel_folder(client, folder_id)
        )
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        verb = "Archived" if archive else "Unarchived"
        typer.echo(f"{verb} folder {result.get('folder_id') or folder_id}")


@folder_app.command("archive")
def folder_archive(
    ctx: typer.Context,
    folder_id: int = typer.Option(..., "--folder-id", help="Target folder ID."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of text.",
        hidden=True,
    ),
) -> None:
    """Archive a channel folder; Zulip exposes no hard delete."""
    _folder_archive_common(ctx, folder_id=folder_id, json_output=json_output, archive=True)


@folder_app.command("unarchive")
def folder_unarchive(
    ctx: typer.Context,
    folder_id: int = typer.Option(..., "--folder-id", help="Target folder ID."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of text.",
        hidden=True,
    ),
) -> None:
    """Reactivate an archived channel folder."""
    _folder_archive_common(ctx, folder_id=folder_id, json_output=json_output, archive=False)


def _current_folder_order(folders: list[dict[str, Any]]) -> list[int]:
    """Return folder IDs in the server's current order."""
    indexed: list[tuple[bool, int, int, int]] = []
    for index, folder in enumerate(folders):
        folder_id = folder.get("id")
        if not isinstance(folder_id, int) or isinstance(folder_id, bool):
            raise ValueError(f"Channel folder missing numeric id: {folder!r}")
        order = folder.get("order")
        if isinstance(order, int) and not isinstance(order, bool):
            indexed.append((False, order, index, folder_id))
        else:
            indexed.append((True, index, index, folder_id))
    return [folder_id for _missing, _order, _index, folder_id in sorted(indexed)]


@folder_app.command("move")
def folder_move(
    ctx: typer.Context,
    folder_id: int = typer.Option(..., "--folder-id", help="Folder ID to move."),
    before: str | None = typer.Option(None, "--before", help="Move before this folder name, id:NUM, or ID."),
    after: str | None = typer.Option(None, "--after", help="Move after this folder name, id:NUM, or ID."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of text.",
        hidden=True,
    ),
) -> None:
    """Move a channel folder before or after another folder."""
    if (before is None) == (after is None):
        emit_error("Exactly one of --before or --after is required")
        raise typer.Exit(code=1)

    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    position: Literal["before", "after"] = "before" if before is not None else "after"
    reference_token = before if before is not None else after
    assert reference_token is not None

    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        folders = zulip_cli.list_channel_folders(client, include_archived=True)
        reference_id = zulip_cli.resolve_channel_folder_reference(reference_token, folders)
        current_order = _current_folder_order(folders)
        new_order = zulip_cli.plan_folder_move(current_order, folder_id, reference_id, position)
        zulip_cli.reorder_channel_folders(client, new_order)
    except ValueError as exc:
        emit_error(str(exc))
        raise typer.Exit(code=1) from exc
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(
            {
                "status": "success",
                "operation": "move",
                "folder_id": folder_id,
                "reference_folder_id": reference_id,
                "position": position,
                "order": new_order,
            }
        )
    else:
        typer.echo(f"Moved folder {folder_id} {position} folder {reference_id}", err=True)
