# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""``lftools-uv lfx committee`` commands.

Results go to stdout; errors go to stderr. A committee that cannot be
found exits :data:`EXIT_NOT_FOUND`, matching the ``rtd`` read commands,
and any other failure exits :data:`EXIT_ERROR`.
"""

from __future__ import annotations

import json
from typing import Any

import typer

from lftools_uv.api.endpoints.lfx import (
    LfxAPIError,
    LfxClient,
    LfxError,
    LfxNotFoundError,
    show_committee,
)
from lftools_uv.output import echo
from lftools_uv.typer_apps.lfx.apps import committee_app

#: Exit status for any failure other than a missing committee.
EXIT_ERROR = 1

#: Exit status when no committee matches, as the ``rtd`` read commands use.
EXIT_NOT_FOUND = 3

#: The fields ``committee show`` prints, in order.
SHOW_FIELDS = (
    "uid",
    "name",
    "category",
    "project_uid",
    "project_name",
    "sso_group_enabled",
    "sso_group_name",
    "join_mode",
    "public",
    "total_members",
)

FORBIDDEN_HINT = "the token may be missing, expired or without access to this committee, or the committee may not exist"


def handle_lfx_error(exc: LfxError) -> typer.Exit:
    """Report an LFX error on stderr and return the ``typer.Exit`` to raise."""
    message = str(exc)
    code = EXIT_ERROR
    if isinstance(exc, LfxNotFoundError) or (isinstance(exc, LfxAPIError) and exc.status == 404):
        code = EXIT_NOT_FOUND
    elif isinstance(exc, LfxAPIError) and exc.status == 403:
        message = f"{message}; {FORBIDDEN_HINT}"
    typer.echo(f"Error: {message}", err=True)
    return typer.Exit(code=code)


def _format_value(value: Any) -> str:
    """Render a field value: strings as they are, anything else as JSON."""
    if isinstance(value, str):
        return value
    return json.dumps(value)


@committee_app.command("show")
def committee_show(
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
    json_output: bool = typer.Option(False, "--json", help="Print the API response body as JSON."),
) -> None:
    """Show one committee."""
    try:
        client = LfxClient()
        body = show_committee(client, committee)
    except LfxError as exc:
        raise handle_lfx_error(exc) from None

    if json_output:
        echo(json.dumps(client.redact_data(body), indent=2))
        return
    # Select each field from the body as the API sent it: redacting keys
    # first would lose a field whose name the token happens to match.
    for field in SHOW_FIELDS:
        value = _format_value(client.redact_data(body.get(field)))
        echo(client.redact(f"{field}: {value}"))
