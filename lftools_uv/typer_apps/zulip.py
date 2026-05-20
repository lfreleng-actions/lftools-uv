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
    ZulipAmbiguityError,
    ZulipError,
    ZulipNotFoundError,
    get_client,
    list_channels,
    list_groups,
    list_users,
    resolve_channel,
    subscribe_users,
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


def emit_warning(message: str) -> None:
    """Write a warning message to stderr.

    Used for partial failures where the primary operation succeeded but
    a secondary operation (like applying topic-policy) failed.
    """
    typer.echo(f"Warning: {message}", err=True)


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
# US4 — channel create (T035)
# ---------------------------------------------------------------------------


def _validate_id_mode_flags(
    by_email: bool,
    by_id: bool,
    by_name: bool,
    subscribe_users: list[str] | None,
) -> str | None:
    """Validate --by-email/--by-id/--by-name mutex and return the chosen mode.

    Returns the id_mode string (``email``, ``id``, ``name``) when one is
    selected and there are users to process, or ``None`` when no users are
    supplied (flags are optional in that case).

    Raises ``typer.Exit`` via ``emit_error`` when validation fails.
    """
    selected = sum([by_email, by_id, by_name])
    if subscribe_users and selected == 0:
        emit_error("--subscribe requires exactly one of --by-email, --by-id, or --by-name")
        raise typer.Exit(code=1)
    if selected > 1:
        emit_error("--by-email, --by-id, and --by-name are mutually exclusive")
        raise typer.Exit(code=1)
    if not subscribe_users:
        return None
    if by_email:
        return "email"
    if by_id:
        return "id"
    return "name"


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
        help="Comma-separated groups allowed to join the channel.",
    ),
    can_remove_subscribers_group: str | None = typer.Option(
        None,
        "--can-remove-subscribers-group",
        help="Comma-separated groups that can remove subscribers.",
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

    # Validate channel type
    if channel_type not in ("public", "private", "web-public"):
        emit_error(f"Invalid channel type: {channel_type!r}. Valid types: public, private, web-public")
        raise typer.Exit(code=1)

    # Validate announce mutex
    if announce and no_announce:
        emit_error("--announce and --no-announce are mutually exclusive")
        raise typer.Exit(code=1)

    # Validate topic-policy if provided
    if topic_policy is not None and topic_policy not in ("allow", "deny", "follow-default"):
        emit_error(f"Invalid --topic-policy value: {topic_policy!r}. Valid values: allow, deny, follow-default")
        raise typer.Exit(code=1)

    # Validate id mode flags
    id_mode = _validate_id_mode_flags(by_email, by_id, by_name, subscribe)

    # Determine announce value
    announce_value: bool | None = None
    if announce:
        announce_value = True
    elif no_announce:
        announce_value = False

    try:
        client = get_client(zuliprc=options.get("zuliprc"))

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
    help="List Zulip user groups.",
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
    Everyone, Nobody), including their display names and member counts.
    """
    options = ctx.obj or {}
    try:
        client = get_client(zuliprc=options.get("zuliprc"))
        groups = list_groups(
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

# T036 — `channel subscribe` CLI (US5)
# ---------------------------------------------------------------------------


def _resolve_id_mode(by_email: bool, by_id: bool, by_name: bool) -> Literal["email", "id", "name"]:
    """Return the canonical id_mode string for the trio of identifier flags.

    Emits a usage error and raises :class:`typer.Exit` with code ``1`` when
    zero or more than one flag is provided. We deliberately avoid
    :class:`typer.BadParameter` (which would exit with Click's default code
    ``2``) so the CLI honours the cli-commands.md contract of ``0`` /``1``
    exit codes only.
    """
    chosen = [name for name, val in (("email", by_email), ("id", by_id), ("name", by_name)) if val]
    if len(chosen) == 0:
        emit_error("Specify exactly one of --by-email, --by-id, or --by-name")
        raise typer.Exit(code=1)
    if len(chosen) > 1:
        emit_error("--by-email, --by-id, and --by-name are mutually exclusive")
        raise typer.Exit(code=1)
    return cast(Literal["email", "id", "name"], chosen[0])


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
    channel_id: int | None = typer.Option(
        None,
        "--channel-id",
        help="Target channel by numeric ID. When set, all positional arguments are interpreted as USER identifiers (no positional CHANNEL is accepted).",
    ),
    by_email: bool = typer.Option(False, "--by-email", help="Identify users by email."),
    by_id: bool = typer.Option(False, "--by-id", help="Identify users by numeric user ID."),
    by_name: bool = typer.Option(False, "--by-name", help="Identify users by full name."),
    include_archived: bool = typer.Option(False, "--include-archived", help="Permit operating on archived channels."),
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
        if not targets_list:
            emit_error("Provide at least one USER, or omit --channel-id and pass [CHANNEL] USER...")
            raise typer.Exit(code=1)
        channel_arg = channel_id
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

    options = ctx.obj or {}
    # Two-stage resolution so that --json error payloads can include
    # accurate channel context:
    #   Stage 1 — resolve the channel. If this fails, channel_id MUST be
    #             None per FR-008 / data-model.md.
    #   Stage 2 — call subscribe_users (which will re-resolve internally,
    #             but now we have authoritative channel context to thread
    #             into any --json error payload for failures that happen
    #             *after* the channel resolved).
    try:
        client = get_client(zuliprc=options.get("zuliprc"))
        if isinstance(channel_arg, int):
            stream = resolve_channel(client, channel_id=channel_arg, include_archived=include_archived)
        else:
            stream = resolve_channel(client, name=channel_arg, include_archived=include_archived)
    except ZulipNotFoundError as exc:
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
    except ZulipError as exc:
        raise handle_zulip_error(exc) from exc

    resolved_channel_id = stream.get("stream_id") if isinstance(stream, dict) else None
    resolved_channel_name = stream.get("name") if isinstance(stream, dict) else None

    try:
        result = subscribe_users(
            client,
            channel_arg,
            user_idents,
            id_mode=id_mode,
            include_archived=include_archived,
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
        raise handle_zulip_error(exc) from exc

    if options.get("json_output"):
        emit_json(result)
    else:
        rows = [(r["user"], r["status"]) for r in result.get("results", [])]
        for err in result.get("errors", []):
            rows.append((err["user"], f"error: {err.get('error', 'unknown')}"))
        emit_table(rows, headers=["user", "status"])
        if result.get("errors"):
            emit_error(f"{len(result['errors'])} user(s) could not be subscribed to '{result.get('channel_name')}'.")

    if result.get("status") != "success":
        raise typer.Exit(code=1)
