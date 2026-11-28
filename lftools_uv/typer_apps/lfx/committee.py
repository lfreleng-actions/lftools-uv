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
from typing import TYPE_CHECKING, Any

import typer

from lftools_uv.api.endpoints.lfx import (
    COMMITTEE_CATEGORIES,
    JOIN_MODES,
    NO_USERNAME,
    LfxAPIError,
    LfxClient,
    LfxError,
    LfxNotFoundError,
    add_committee_member,
    count_without_username,
    create_committee,
    find_members,
    find_project_uid,
    format_csv,
    format_info_yaml,
    format_text,
    get_committee,
    get_committee_members,
    hide_emails,
    invite_to_committee,
    list_project_committees,
    remove_committee_member,
    resolve_committee_uid,
    show_committee,
)
from lftools_uv.output import echo
from lftools_uv.typer_apps.lfx.apps import committee_app

if TYPE_CHECKING:
    from collections.abc import Callable

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

WRITER_FORBIDDEN_HINT = "the token may be missing or expired, or may not be a writer on the committee"

INVITER_FORBIDDEN_HINT = "the token may be missing or expired, or may not have the inviter relation on the committee"


class MemberFormat(enum.StrEnum):
    """Output formats of ``committee members``."""

    TEXT = "text"
    CSV = "csv"
    INFO_YAML = "info-yaml"


def handle_lfx_error(
    exc: LfxError,
    forbidden_hint: str = FORBIDDEN_HINT,
    http_404_exit: int = EXIT_NOT_FOUND,
    scrub: Callable[[str], str] | None = None,
) -> typer.Exit:
    """Report an LFX error on stderr and return the ``typer.Exit`` to raise.

    :arg forbidden_hint: What a 403 may mean, appended to its message.
    :arg http_404_exit: Exit status for an API answer of 404; a lookup
        that found nothing exits :data:`EXIT_NOT_FOUND` either way.
    :arg scrub: Applied to the error's message before it is printed.
    """
    message = str(exc) if scrub is None else scrub(str(exc))
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


def _membership_error(exc: LfxError, forbidden_hint: str, http_404_exit: int = EXIT_ERROR) -> typer.Exit:
    """Return :func:`handle_lfx_error` for a membership command, with email addresses hidden."""
    return handle_lfx_error(exc, forbidden_hint, http_404_exit, scrub=hide_emails)


def _fail(message: str) -> typer.Exit:
    """Print ``message`` as an error, with email addresses hidden, and return the exit to raise."""
    typer.echo(f"Error: {hide_emails(message)}", err=True)
    return typer.Exit(code=EXIT_ERROR)


def _string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def _quoted(client: LfxClient, username: str) -> str:
    # repr() doubles a backslash, after which neither the token nor an
    # address with an escaped quote matches, so redact and hide first.
    return repr(hide_emails(client.redact(username)))


def _described(client: LfxClient, username: str) -> str:
    return f"username {_quoted(client, username)}" if username else "no username"


def _report_existing_member(client: LfxClient, uid: str, email: str, username: str | None, conflict: LfxError) -> None:
    """Report the member an add found already there, and raise ``typer.Exit`` unless it is the one wanted."""
    try:
        matches = find_members(get_committee_members(client, uid), email=email)
    except LfxError as exc:
        raise _membership_error(exc, MEMBERS_FORBIDDEN_HINT) from None
    if not matches:
        raise _membership_error(conflict, WRITER_FORBIDDEN_HINT)
    existing = _string(matches[0].get("username"))
    member_uid = _string(matches[0].get("uid"))
    found = client.redact(f"already a member, with {_described(client, existing)}")
    if username is not None and existing.casefold() != username.casefold():
        raise _fail(client.redact(f"the address is {found}, not {_quoted(client, username)}; member UID {member_uid}"))
    typer.echo(hide_emails(client.redact(f"The address is {found}; member UID {member_uid}")), err=True)


def _undo_add(client: LfxClient, uid: str, member: dict[str, Any], username: str, *, notify: bool) -> typer.Exit:
    """Remove a member just added under the wrong username and return the exit to raise."""
    resolved = _string(member.get("username"))
    member_uid = _string(member.get("uid"))
    reason = client.redact(f"the address resolved to {_described(client, resolved)}, not {_quoted(client, username)}")
    if not member_uid:
        return _fail(f"{reason}; the answer carried no member UID, so the member could not be removed")
    try:
        remove_committee_member(client, uid, member_uid, notify=notify)
    except LfxError as exc:
        return _fail(client.redact(f"{reason}; removing it failed too, member UID {member_uid}: {exc}"))
    return _fail(f"{reason}; removed the member again")


@committee_app.command("add-member")
def committee_add_member(
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
    email: str = typer.Option(
        ..., "--email", help="Email address of the person to add; the service finds their LF account by it."
    ),
    first_name: str | None = typer.Option(
        None, "--first-name", help="First name; the service takes it from the LF account when omitted."
    ),
    last_name: str | None = typer.Option(
        None, "--last-name", help="Last name; the service takes it from the LF account when omitted."
    ),
    organization: str | None = typer.Option(None, "--organization", help="Name of the member's organisation."),
    username: str | None = typer.Option(
        None, "--username", help="LFID the address must belong to; a member added under another is removed again."
    ),
    notify: bool = typer.Option(False, "--notify", help="Let the service email the member."),
    json_output: bool = typer.Option(False, "--json", help="Print the member object as JSON."),
) -> None:
    """Add a member to a committee by email address.

    Prints added, the username the service resolved from the address and
    the member UID, separated by tabs.
    """
    if username is not None and not username.strip():
        # An empty LFID would match a member the service gave no username.
        raise typer.BadParameter("must name an LFID, not be empty", param_hint="'--username'")
    try:
        client = LfxClient()
        uid = resolve_committee_uid(client, committee, scrub=hide_emails)
    except LfxError as exc:
        raise _membership_error(exc, WRITER_FORBIDDEN_HINT, EXIT_NOT_FOUND) from None

    request: dict[str, Any] = {"email": email}
    if first_name is not None:
        request["first_name"] = first_name
    if last_name is not None:
        request["last_name"] = last_name
    if organization is not None:
        request["organization"] = {"name": organization}
    try:
        member = add_committee_member(client, uid, request, notify=notify)
    except LfxAPIError as exc:
        if exc.status != 409:
            raise _membership_error(exc, WRITER_FORBIDDEN_HINT) from None
        _report_existing_member(client, uid, email, username, exc)
        return
    except LfxError as exc:
        raise _membership_error(exc, WRITER_FORBIDDEN_HINT) from None

    resolved = _string(member.get("username"))
    if username is not None and resolved.casefold() != username.casefold():
        raise _undo_add(client, uid, member, username, notify=notify)
    if not resolved:
        log.warning("The member has no username: no LF account owns the address yet")
    if json_output:
        echo(json.dumps(client.redact_data(member), indent=2))
        return
    echo(client.redact(f"added\t{resolved or NO_USERNAME}\t{_string(member.get('uid'))}"))


@committee_app.command("remove-member")
def committee_remove_member(
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
    username: str | None = typer.Option(None, "--username", help="Username (LFID) of the member to remove."),
    email: str | None = typer.Option(None, "--email", help="Email address of the member to remove."),
    member_uid: str | None = typer.Option(None, "--member-uid", help="UID of the member to remove."),
    notify: bool = typer.Option(False, "--notify", help="Let the service email the member."),
) -> None:
    """Remove a member from a committee.

    Name the member with exactly one of --username, --email and
    --member-uid. Prints removed and the member UID, separated by a tab.
    """
    if sum(value is not None for value in (username, email, member_uid)) != 1:
        msg = "give exactly one of --username, --email and --member-uid"
        raise typer.BadParameter(msg)
    try:
        client = LfxClient()
        uid = resolve_committee_uid(client, committee, scrub=hide_emails)
        members = [] if member_uid is not None else get_committee_members(client, uid)
    except LfxError as exc:
        raise _membership_error(exc, MEMBERS_FORBIDDEN_HINT, EXIT_NOT_FOUND) from None

    if member_uid is None:
        matches = find_members(members, username=username, email=email)
        what = f"the username {_quoted(client, username)}" if username is not None else "that email address"
        if not matches:
            typer.echo(hide_emails(client.redact(f"Error: no member of the committee has {what}")), err=True)
            raise typer.Exit(code=EXIT_NOT_FOUND)
        if len(matches) > 1:
            uids = ", ".join(sorted(_string(item.get("uid")) for item in matches))
            hint = f"{len(matches)} members have {what}: {uids}; name one with --member-uid"
            raise _fail(client.redact(hint))
        member_uid = _string(matches[0].get("uid"))
        if not member_uid:
            raise _fail(client.redact(f"the member with {what} carries no member UID"))

    try:
        remove_committee_member(client, uid, member_uid, notify=notify)
    except LfxError as exc:
        raise _membership_error(exc, WRITER_FORBIDDEN_HINT, EXIT_NOT_FOUND) from None
    echo(client.redact(f"removed\t{member_uid}"))


@committee_app.command("invite")
def committee_invite(
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
    email: str = typer.Argument(..., help="Email address to invite."),
    json_output: bool = typer.Option(False, "--json", help="Print the invite object as JSON."),
) -> None:
    """Invite an email address to join a committee.

    Prints the invite UID and its status, separated by a tab.
    """
    try:
        client = LfxClient()
        uid = resolve_committee_uid(client, committee, scrub=hide_emails)
    except LfxError as exc:
        raise _membership_error(exc, INVITER_FORBIDDEN_HINT, EXIT_NOT_FOUND) from None
    try:
        invite = invite_to_committee(client, uid, email)
    except LfxError as exc:
        raise _membership_error(exc, INVITER_FORBIDDEN_HINT) from None

    if json_output:
        echo(json.dumps(client.redact_data(invite), indent=2))
        return
    echo(client.redact(f"{_string(invite.get('uid'))}\t{_string(invite.get('status'))}"))
