# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""The ``zulip channel unsubscribe`` command.

The command orchestrates four steps — validate the flag shape, connect,
resolve the channel, then unsubscribe — and every failure along the way
has to be reported in the same shape: the canonical FR-008 payload under
``--json``, a plain message on stderr otherwise. The helpers below own
one step each so that shared reporting stays in one place.
"""

from __future__ import annotations

from typing import Any, cast

import typer

from lftools_uv.api.endpoints.zulip import IdMode, ZulipError
from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.apps import channel_app
from lftools_uv.typer_apps.zulip.helpers import (
    bulk_mutation_result,
    emit_error,
    emit_json,
    emit_table,
    handle_zulip_error,
)


def _error_payload(message: str, *, channel_id: int | None, channel_name: str) -> dict[str, Any]:
    """Build the canonical unsubscribe error payload (FR-008)."""
    return bulk_mutation_result(
        operation="unsubscribe",
        channel_id=channel_id,
        channel_name=channel_name,
        results=[],
        errors=[{"user": None, "error": message}],
    )


def _fail_validation(options: dict[str, Any], message: str, *, channel_name: str = "") -> None:
    """Report a flag-shape failure and abort with exit code 1."""
    if options.get("json_output"):
        emit_json(_error_payload(message, channel_id=None, channel_name=channel_name))
    else:
        emit_error(message)
    raise typer.Exit(code=1)


def _fail_request(
    options: dict[str, Any],
    exc: ZulipError,
    *,
    channel_id: int | None,
    channel_name: str,
) -> typer.Exit:
    """Return the ``typer.Exit`` to raise for a failed Zulip call."""
    if options.get("json_output"):
        emit_json(_error_payload(str(exc), channel_id=channel_id, channel_name=channel_name))
        return typer.Exit(code=1)
    return handle_zulip_error(exc)


def _parse_channel_id(channel_id: str | None, options: dict[str, Any]) -> int | None:
    """Parse ``--channel-id``, aborting when it is not numeric."""
    if channel_id is None:
        return None
    try:
        return int(channel_id)
    except ValueError:
        _fail_validation(options, "--channel-id must be a numeric channel ID.")
    return None


def _split_targets(
    targets: list[str] | None,
    parsed_channel_id: int | None,
    options: dict[str, Any],
) -> tuple[str | None, list[str]]:
    """Split the positional targets into a channel name and users.

    With ``--channel-id`` every positional value is a user; without it
    the first value is the channel name and the rest are users.
    """
    target_values = list(targets or [])
    if parsed_channel_id is not None:
        return None, target_values

    if len(target_values) < 2:
        channel_for_error = target_values[0] if target_values else ""
        _fail_validation(
            options,
            "Provide a channel name (or --channel-id) and at least one user",
            channel_name=channel_for_error,
        )
    channel_name, *users = target_values
    return channel_name, users


def _require_id_mode(
    by_email: bool,
    by_id: bool,
    by_name: bool,
    channel_name: str | None,
    options: dict[str, Any],
) -> IdMode:
    """Return the id-mode, requiring exactly one ``--by-*`` flag."""
    mode_flags = [
        ("email", by_email),
        ("id", by_id),
        ("name", by_name),
    ]
    chosen = [name for name, flag in mode_flags if flag]
    if len(chosen) != 1:
        _fail_validation(
            options,
            "Exactly one of --by-email/--by-id/--by-name is required",
            channel_name=channel_name or "",
        )
    return cast(IdMode, chosen[0])


def _connect(options: dict[str, Any], channel_name: str | None) -> Any:
    """Build the Zulip client for the command."""
    try:
        return zulip_cli.get_client(zuliprc=options.get("zuliprc"))
    except ZulipError as exc:
        # Configuration/connect failure happens before channel
        # resolution can even be attempted, so the error payload
        # cannot carry a resolved channel_id.
        raise _fail_request(options, exc, channel_id=None, channel_name=channel_name or "") from exc


def _resolved_identity(
    target: dict[str, Any],
    parsed_channel_id: int | None,
    channel_name: str | None,
) -> tuple[int | None, str]:
    """Return the channel id and name to quote in result payloads."""
    resolved_channel_id: int | None = parsed_channel_id
    raw_id = target.get("stream_id")
    if isinstance(raw_id, int):
        resolved_channel_id = raw_id
    resolved_channel_name = str(target.get("name", "")) or (channel_name or "")
    return resolved_channel_id, resolved_channel_name


def _emit_report(payload: dict[str, Any], options: dict[str, Any]) -> None:
    """Render the unsubscribe outcome as JSON or a table."""
    if options.get("json_output"):
        emit_json(payload)
        return
    rows = [(item["user"], item["status"]) for item in payload["results"]]
    rows.extend((item["user"], f"error: {item['error']}") for item in payload["errors"])
    emit_table(rows, headers=["User", "Status"])


@channel_app.command("unsubscribe")
def channel_unsubscribe(
    ctx: typer.Context,
    targets: list[str] | None = typer.Argument(
        None,
        metavar="[CHANNEL] USER [USER...]",
        help=(
            "When --channel-id is absent, the first value is the channel "
            "name and the rest are users. When --channel-id is supplied, "
            "all values are users."
        ),
    ),
    channel_id: str | None = typer.Option(
        None,
        "--channel-id",
        metavar="INT",
        help="Target the channel by numeric ID instead of name.",
    ),
    by_email: bool = typer.Option(False, "--by-email", help="Identify users by email address."),
    by_id: bool = typer.Option(False, "--by-id", help="Identify users by numeric user ID."),
    by_name: bool = typer.Option(False, "--by-name", help="Identify users by full name."),
    include_archived: bool = typer.Option(
        False,
        "--include-archived",
        help="Search archived channels when resolving the channel target.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
        hidden=True,
    ),
) -> None:
    """Unsubscribe one or more users from a channel."""
    # Import the endpoint module as a namespace so tests can monkeypatch
    # its helpers while keeping ``get_client`` patched on this module.
    from lftools_uv.api.endpoints import zulip as zulip_api

    options = {**(ctx.obj or {})}
    if json_output:
        options["json_output"] = True

    parsed_channel_id = _parse_channel_id(channel_id, options)
    channel_name, users = _split_targets(targets, parsed_channel_id, options)
    id_mode = _require_id_mode(by_email, by_id, by_name, channel_name, options)
    if not users:
        _fail_validation(options, "At least one user identifier is required", channel_name=channel_name or "")

    client = _connect(options, channel_name)

    # Pre-resolve the channel so that any failure inside
    # ``unsubscribe_users`` (e.g. the DELETE call returning an error
    # response) can still report the resolved channel_id/channel_name
    # in the --json error payload. The contract documents
    # ``channel_id: null`` only for the case where the channel itself
    # could not be resolved.
    try:
        target = zulip_api.resolve_channel(
            client,
            name=channel_name,
            channel_id=parsed_channel_id,
            include_archived=include_archived,
        )
    except ZulipError as exc:
        raise _fail_request(options, exc, channel_id=None, channel_name=channel_name or "") from exc

    resolved_channel_id, resolved_channel_name = _resolved_identity(target, parsed_channel_id, channel_name)

    try:
        payload = zulip_api.unsubscribe_users(
            client,
            users,
            id_mode=id_mode,
            include_archived=include_archived,
            resolved_channel=target,
        )
    except ZulipError as exc:
        # FR-008: mutation commands emit the canonical JSON schema even
        # on error. The channel was successfully resolved above, so we
        # report the resolved channel_id/name here (the failure is
        # downstream — e.g. the DELETE call itself returned an error).
        raise _fail_request(
            options,
            exc,
            channel_id=resolved_channel_id,
            channel_name=resolved_channel_name,
        ) from exc

    _emit_report(payload, options)

    # Per the CLI contract, exit non-zero on ANY error condition. A
    # ``partial`` status means some operations failed, so it must also
    # produce a non-zero exit code alongside ``error``.
    if payload["status"] in ("error", "partial"):
        raise typer.Exit(code=1)
