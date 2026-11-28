# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""``lftools-uv lfx committee`` commands.

Results go to stdout; errors and diagnostics go to stderr. A committee
or project that cannot be found exits :data:`EXIT_NOT_FOUND`, matching
the ``rtd`` read commands, and any other failure exits :data:`EXIT_ERROR`.
"""

from __future__ import annotations

import enum
import json
import logging
from typing import Any

import typer

from lftools_uv.api.endpoints.lfx import (
    COMMITTEE_CATEGORIES,
    JOIN_MODES,
    LfxAPIError,
    LfxClient,
    LfxError,
    LfxNotFoundError,
    count_without_username,
    create_committee,
    find_project_uid,
    format_csv,
    format_info_yaml,
    format_text,
    get_committee,
    get_committee_members,
    list_project_committees,
    resolve_committee_uid,
    show_committee,
)
from lftools_uv.output import echo
from lftools_uv.typer_apps.lfx.apps import committee_app

log = logging.getLogger(__name__)

#: Exit status for any failure other than a missing committee.
EXIT_ERROR = 1

#: Exit status when no committee or project matches, as the ``rtd`` read commands use.
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

MEMBERS_FORBIDDEN_HINT = (
    "reading members needs the auditor relation on the committee, which a committee writer has; "
    f"otherwise {FORBIDDEN_HINT}"
)

CREATE_FORBIDDEN_HINT = "the token may be missing or expired, or may not be a writer on the project"


class MemberFormat(enum.StrEnum):
    """Output formats of ``committee members``."""

    TEXT = "text"
    CSV = "csv"
    INFO_YAML = "info-yaml"


def handle_lfx_error(
    exc: LfxError, forbidden_hint: str = FORBIDDEN_HINT, http_404_exit: int = EXIT_NOT_FOUND
) -> typer.Exit:
    """Report an LFX error on stderr and return the ``typer.Exit`` to raise.

    :arg forbidden_hint: What a 403 may mean, appended to its message.
    :arg http_404_exit: Exit status for an API answer of 404; a lookup
        that found nothing exits :data:`EXIT_NOT_FOUND` either way.
    """
    message = str(exc)
    code = EXIT_ERROR
    if isinstance(exc, LfxNotFoundError):
        code = EXIT_NOT_FOUND
    elif isinstance(exc, LfxAPIError) and exc.status == 404:
        code = http_404_exit
    elif isinstance(exc, LfxAPIError) and exc.status == 403:
        message = f"{message}; {forbidden_hint}"
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


@committee_app.command("list")
def committee_list(
    project: str = typer.Option(..., "--project", help="Project slug."),
    sso_only: bool = typer.Option(False, "--sso-only", help="Keep the committees with an SSO group enabled."),
    json_output: bool = typer.Option(False, "--json", help="Print a JSON array of the committees."),
) -> None:
    """List a project's committees, sorted by name.

    Prints one line per committee: the SSO group name (empty when it has
    none), the UID and the name, separated by tabs.
    """
    try:
        client = LfxClient()
        committees = list_project_committees(client, project)
    except LfxError as exc:
        raise handle_lfx_error(exc) from None

    if sso_only:
        committees = [item for item in committees if item.get("sso_group_enabled") is True]
    if json_output:
        echo(json.dumps(client.redact_data(committees), indent=2))
    else:
        for item in committees:
            fields = (item.get("sso_group_name") or "", item.get("uid") or "", item.get("name") or "")
            echo(client.redact("\t".join(_format_value(field) for field in fields)))
    if not committees:
        kind = "committee with an SSO group enabled" if sso_only else "committee"
        log.info("Project %s has no %s the token can see", client.redact(project), kind)


@committee_app.command("members")
def committee_members(
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
    output_format: MemberFormat | None = typer.Option(
        None, "--format", help="Output format: text (the default), csv or info-yaml."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print the API's member array as JSON."),
) -> None:
    """List a committee's members, sorted by username.

    text prints each username and email address; csv prints the SSO
    group name, username, full name and email; info-yaml prints INFO.yaml
    committer entries, leaving out members without a username.
    """
    if json_output and output_format is not None:
        raise typer.BadParameter("cannot be combined with --json", param_hint="'--format'")
    output_format = output_format or MemberFormat.TEXT
    try:
        client = LfxClient()
        uid = resolve_committee_uid(client, committee)
        members = get_committee_members(client, uid)
        group = ""
        if output_format is MemberFormat.CSV:
            body = get_committee(client, uid)
            group = _format_value(body.get("sso_group_name") or body.get("name") or "")
    except LfxError as exc:
        raise handle_lfx_error(exc, MEMBERS_FORBIDDEN_HINT) from None

    if json_output:
        echo(json.dumps(client.redact_data(members), indent=2))
        return
    if output_format is MemberFormat.CSV:
        text = format_csv(members, group, client.redact)
    elif output_format is MemberFormat.INFO_YAML:
        text = format_info_yaml(members, client.redact)
        left_out = count_without_username(members)
        if left_out:
            noun = "member" if left_out == 1 else "members"
            log.warning("Left out %d %s without a username", left_out, noun)
    else:
        text = format_text(members, client.redact)
    if text:
        typer.echo(text, nl=False)


def _choice(allowed: tuple[str, ...]) -> Any:
    """Return an option callback that refuses a value outside ``allowed``."""

    def check(value: str) -> str:
        if value not in allowed:
            listed = ", ".join(repr(item) for item in allowed)
            msg = f"{value!r} is not one of {listed}."
            raise typer.BadParameter(msg)
        return value

    return check


@committee_app.command("create")
def committee_create(
    project: str = typer.Option(..., "--project", help="Slug of the project the committee belongs to."),
    name: str = typer.Option(..., "--name", help="Committee name; the SSO group name is built from it."),
    category: str = typer.Option(
        "Committers", "--category", callback=_choice(COMMITTEE_CATEGORIES), help="Committee category."
    ),
    description: str | None = typer.Option(None, "--description", help="Committee description."),
    join_mode: str = typer.Option(
        "closed",
        "--join-mode",
        callback=_choice(JOIN_MODES),
        help=f"Who may join: {', '.join(JOIN_MODES)}. 'closed' lets only a committee writer add members.",
    ),
    sso_group: bool = typer.Option(True, "--sso-group/--no-sso-group", help="Give the committee an SSO group."),
    public: bool = typer.Option(False, "--public/--private", help="Make the committee public."),
    json_output: bool = typer.Option(False, "--json", help="Print the API response body as JSON."),
) -> None:
    """Create a committee under a project.

    Prints the SSO group name the service gave the committee, empty when
    it gave none, and the committee UID, separated by a tab.
    """
    try:
        client = LfxClient()
        project_uid = find_project_uid(client, project)
    except LfxError as exc:
        raise handle_lfx_error(exc) from None

    request: dict[str, Any] = {
        "name": name,
        "category": category,
        "project_uid": project_uid,
        "join_mode": join_mode,
        "public": public,
        "sso_group_enabled": sso_group,
    }
    if description is not None:
        request["description"] = description
    try:
        body = create_committee(client, request)
    except LfxError as exc:
        raise handle_lfx_error(exc, forbidden_hint=CREATE_FORBIDDEN_HINT, http_404_exit=EXIT_ERROR) from None

    if json_output:
        echo(json.dumps(client.redact_data(body), indent=2))
        return
    fields = [body.get("sso_group_name"), body.get("uid")]
    echo(client.redact("\t".join(value if isinstance(value, str) else "" for value in fields)))
