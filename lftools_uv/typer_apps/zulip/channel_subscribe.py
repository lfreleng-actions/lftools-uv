# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip channel subscribe`` command (FR-005, US5)."""

from __future__ import annotations

from typing import Any

import typer

from lftools_uv.api.endpoints.zulip import ZulipAmbiguityError, ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import channel_app
from lftools_uv.typer_apps.zulip.helpers import (
    _resolve_id_mode,
    bulk_mutation_result,
    emit_error,
    emit_json,
    emit_table,
    handle_zulip_error,
)


@channel_app.command("subscribe")
def channel_subscribe(
    ctx: typer.Context,
    targets: list[str] | None = typer.Argument(
        None,
        metavar="[CHANNEL] USER [USER...]",
        help=(
            "Channel name (when --channel-id is absent) followed by one or "
            "more user identifiers. When --channel-id is provided, all "
            "positional arguments are user identifiers."
        ),
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        metavar="INT",
        help="Target channel by numeric ID. When set, all positional arguments are interpreted as USER identifiers (no positional CHANNEL is accepted).",
    ),
    by_email: bool = typer.Option(False, "--by-email", help="Identify users by email."),
    by_id: bool = typer.Option(False, "--by-id", help="Identify users by numeric user ID."),
    by_name: bool = typer.Option(False, "--by-name", help="Identify users by full name."),
    include_archived: bool = typer.Option(False, "--include-archived", help="Permit operating on archived channels."),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """Subscribe users to a channel (FR-005, US5)."""
    id_mode = _resolve_id_mode(by_email, by_id, by_name)

    # Split positional arguments per the contract:
    #   --channel-id present → all positionals are USERs.
    #   --channel-id absent  → first positional is channel name, rest are USERs.
    # ``targets`` is declared as an optional Typer argument (default ``None``)
    # rather than required (``...``) so we can validate "no arguments" cases
    # ourselves and exit with code 1, honouring the cli-commands.md contract
    # (Click's required-argument failure would otherwise exit 2).
    targets_list: list[str] = list(targets or [])
    channel_arg: str | int
    if channel_id is not None:
        try:
            parsed_channel_id = int(channel_id)
        except ValueError:
            emit_error("--channel-id must be a numeric channel ID.")
            raise typer.Exit(code=1) from None
        if not targets_list:
            emit_error("Provide at least one USER, or omit --channel-id and pass [CHANNEL] USER...")
            raise typer.Exit(code=1)
        channel_arg = parsed_channel_id
        user_idents = targets_list
    else:
        if len(targets_list) < 2:
            # Contract says exit code 0/1, not 2 — use Exit(1) rather than
            # typer.BadParameter (which would exit 2 via Click).
            emit_error("Provide [CHANNEL] followed by at least one USER, or use --channel-id.")
            raise typer.Exit(code=1)
        # Preserve the channel positional as a STRING — even if it looks
        # numeric (e.g. literally the channel named "123"). Callers that
        # want id-based resolution must use --channel-id.
        channel_arg = targets_list[0]
        user_idents = targets_list[1:]

    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True
    # Two-stage resolution so that --json error payloads can include
    # accurate channel context:
    #   Stage 1 — resolve the channel. If this fails, channel_id MUST be
    #             None per FR-008 / data-model.md.
    #   Stage 2 — call subscribe_users with _resolved_stream=stream so it
    #             skips the redundant internal resolve_channel call. We
    #             still wrap it in try/except to thread the resolved
    #             channel context into any --json error payload for
    #             failures that happen *after* the channel resolved
    #             (user resolution, ambiguity, server errors).
    try:
        client = zulip_cli.get_client(zuliprc=options.get("zuliprc"))
        if isinstance(channel_arg, int):
            stream = zulip_cli.resolve_channel(client, channel_id=channel_arg, include_archived=include_archived)
        else:
            stream = zulip_cli.resolve_channel(client, name=channel_arg, include_archived=include_archived)
    except ZulipError as exc:
        # Per FR-008, --json errors are structured. ``channel_id`` is
        # ``None`` because the channel never resolved (this includes
        # ZulipNotFoundError on the channel itself as well as any other
        # ZulipError raised during client setup or channel lookup).
        if options.get("json_output"):
            channel_name_str = channel_arg if isinstance(channel_arg, str) else ""
            error_payload = bulk_mutation_result(
                operation="subscribe",
                channel_id=None,
                channel_name=channel_name_str,
                results=[],
                errors=[{"error": str(exc)}],
            )
            emit_json(error_payload)
            raise typer.Exit(code=1) from exc
        raise handle_zulip_error(exc) from exc

    resolved_channel_id = stream.get("stream_id") if isinstance(stream, dict) else None
    resolved_channel_name = stream.get("name") if isinstance(stream, dict) else None

    try:
        result = zulip_cli.subscribe_users(
            client,
            channel_arg,
            user_idents,
            id_mode=id_mode,
            include_archived=include_archived,
            _resolved_stream=stream,
        )
    except ZulipError as exc:
        # Channel was successfully resolved above; thread that context
        # into the --json payload so consumers can correlate the error
        # with the target stream even when the failure was downstream
        # (e.g. user resolution, ambiguity, server error).
        if options.get("json_output"):
            err_entry: dict[str, Any] = {"error": str(exc)}
            if isinstance(exc, ZulipAmbiguityError) and exc.matches:
                # Surface the disambiguation candidates so --json consumers
                # can prompt the operator with concrete choices.
                err_entry["matches"] = exc.matches
            error_payload = bulk_mutation_result(
                operation="subscribe",
                channel_id=resolved_channel_id if isinstance(resolved_channel_id, int) else None,
                channel_name=resolved_channel_name if isinstance(resolved_channel_name, str) else "",
                results=[],
                errors=[err_entry],
            )
            emit_json(error_payload)
            raise typer.Exit(code=1) from exc
        # Non-JSON mode: render a normal error, but also surface the
        # ambiguity disambiguation candidates as a small table so the
        # operator can pick a concrete identifier and retry.
        if isinstance(exc, ZulipAmbiguityError) and exc.matches:
            emit_error(str(exc))
            match_rows = [
                (
                    str(m.get("user_id", "")),
                    str(m.get("email", "")),
                    str(m.get("full_name", "")),
                )
                for m in exc.matches
            ]
            emit_table(match_rows, headers=["User ID", "Email", "Full Name"])
            raise typer.Exit(code=1) from exc
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        rows = [(r["user"], r["status"]) for r in result.get("results", [])]
        for err in result.get("errors", []):
            rows.append((err["user"], f"error: {err.get('error', 'unknown')}"))
        emit_table(rows, headers=["User", "Status"])
        # Surface a one-line summary on stderr so humans see partial outcomes.
        if result.get("errors"):
            emit_error(f"{len(result['errors'])} user(s) could not be subscribed to '{result.get('channel_name')}'.")

    if result.get("status") != "success":
        raise typer.Exit(code=1)
