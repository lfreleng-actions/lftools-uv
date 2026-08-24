# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Shared presentation and validation helpers for the Zulip CLI.

Holds the pieces every Zulip subcommand needs: zuliprc path
normalization, table/JSON output formatting, consistent error display,
the canonical mutation-result payloads, and the flag-shape validators
that several commands apply before contacting the server.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Sequence
from pathlib import Path
from typing import Any, Literal, cast

import typer
from tabulate import tabulate

from lftools_uv.api.endpoints.zulip import ZulipError

#: Canonical error message displayed when the ``zulip`` extra is missing
#: (FR-022). Matches the wording in ``contracts/cli-commands.md``.
MISSING_EXTRA_MESSAGE = 'Zulip support requires the zulip extra. Install with:\n  pip install "lftools-uv[zulip]"'


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


def _resolve_channel_target(channel: str | None, channel_id: str | None) -> None:
    """Validate that exactly one of ``channel``/``channel_id`` is supplied.

    Mirrors the mutual-exclusivity rule documented in
    ``contracts/cli-commands.md`` for ``channel subscribers``. Raises
    ``typer.Exit`` (after emitting the canonical error) when the rule is
    violated.
    """
    if (channel is None) == (channel_id is None):
        emit_error("Exactly one of [channel] (positional) or --channel-id must be supplied.")
        raise typer.Exit(code=1)


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


def _validate_single_channel_target(
    channel: str | None,
    channel_id: str | None,
) -> None:
    """Enforce FR-018: exactly one of [channel] or --channel-id."""
    if channel is None and channel_id is None:
        emit_error("Exactly one of [channel] or --channel-id is required")
        raise typer.Exit(code=1)
    if channel is not None and channel_id is not None:
        emit_error("Specify only one of [channel] or --channel-id, not both")
        raise typer.Exit(code=1)
