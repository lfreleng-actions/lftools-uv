# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""``lftools-uv lfx committee inactive`` and the ``inactivecommitters`` console script.

The report says when each member of a committee last owned or reviewed
a change in Gerrit, so that inactive committers can be reviewed. It
replaces ``shell/inactivecommitters``, which read the group from LDAP.
"""

from __future__ import annotations

import calendar
import json
import re
from datetime import date
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, urlsplit

import requests
import typer

from lftools_uv.api.endpoints.lfx import (
    LfxClient,
    LfxError,
    count_without_username,
    get_committee_members,
    resolve_committee_uid,
    sort_members,
)
from lftools_uv.api.endpoints.lfx.members import full_name
from lftools_uv.gerrit_rest import GerritRestAPI
from lftools_uv.output import echo
from lftools_uv.typer_apps.lfx.apps import committee_app
from lftools_uv.typer_apps.lfx.committee import EXIT_ERROR, MEMBERS_FORBIDDEN_HINT, handle_lfx_error

if TYPE_CHECKING:
    from collections.abc import Iterator

#: How many months back a change still counts as recent activity.
DEFAULT_MONTHS = 12


class GerritQueryError(Exception):
    """A Gerrit change query failed, or answered something other than changes."""


class AccountNotFoundError(Exception):
    """Gerrit does not know the account a query named."""


def gerrit_base_url(url: str) -> str:
    """Return the Gerrit base URL, adding ``https://`` when ``url`` has no scheme.

    Any scheme other than ``https://`` is refused, so credentials from
    ``~/.netrc`` never travel in clear. So is a URL that carries a user
    name or password, which the report would print.
    """
    scheme, separator, rest = url.partition("://")
    if not separator:
        scheme, rest = "https", url
    if scheme.lower() != "https":
        msg = "must start with https://, or name no scheme"
        raise typer.BadParameter(msg, param_hint="'GERRIT_URL'")
    base = f"{scheme}://{rest.rstrip('/')}"
    if "@" in urlsplit(base).netloc:
        msg = "must not carry a user name or password; put Gerrit credentials in ~/.netrc"
        raise typer.BadParameter(msg, param_hint="'GERRIT_URL'")
    return base


def _refuse_redirect(response: requests.Response, *args: Any, **kwargs: Any) -> requests.Response:
    """Fail a Gerrit answer that redirects, before requests follows it.

    On a redirect requests reloads the ``~/.netrc`` credentials for the
    new URL, so following one from HTTPS to HTTP on the same host would
    send them in clear.
    """
    if response.is_redirect:
        msg = f"Gerrit answered HTTP {response.status_code}, a redirect, which is not followed"
        raise GerritQueryError(msg)
    return response


def gerrit_client(url: str) -> GerritRestAPI:
    """Return a Gerrit REST client for ``url`` that refuses to follow redirects."""
    rest = GerritRestAPI(gerrit_base_url(url))
    rest.session.hooks["response"].append(_refuse_redirect)
    return rest


def months_before(day: date, months: int) -> date:
    """Return the date ``months`` calendar months before ``day``.

    A day the earlier month lacks becomes its last day, so 31 May less
    three months is 28 or 29 February.
    """
    year, month = divmod(day.year * 12 + day.month - 1 - months, 12)
    month += 1
    return date(year, month, min(day.day, calendar.monthrange(year, month)[1]))


def _is_account_not_found(response: requests.Response, username: str) -> bool:
    """Return whether ``response`` is Gerrit's 400 ``Account '<username>' not found``."""
    if response.status_code != 400:
        return False
    pattern = rf"\baccount\s+['\"]?{re.escape(username)}['\"]?\s+not found\b"
    return re.search(pattern, response.text, re.IGNORECASE) is not None


def last_activity(rest: GerritRestAPI, username: str, since: date | None = None) -> date | None:
    """Return the day of the newest change ``username`` owns or reviewed.

    With ``since``, only changes updated after it count. Returns ``None``
    when no change matches.

    :raises AccountNotFoundError: Gerrit answered 400 ``Account ... not found``.
    :raises GerritQueryError: Any other failure.
    """
    query = f"(reviewedby:{username} OR owner:{username})"
    if since is not None:
        query += f" after:{since.isoformat()}"
    try:
        changes = rest.get(f"changes/?q={quote(query, safe='')}&n=1")
    except requests.HTTPError as exc:
        if exc.response is not None and _is_account_not_found(exc.response, username):
            raise AccountNotFoundError(username) from None
        raise GerritQueryError(str(exc)) from None
    except (requests.RequestException, ValueError) as exc:
        raise GerritQueryError(str(exc)) from None
    if not isinstance(changes, list):
        msg = "the change query answered something other than a JSON array"
        raise GerritQueryError(msg)
    if not changes:
        return None
    updated = changes[0].get("updated") if isinstance(changes[0], dict) else None
    try:
        return date.fromisoformat(str(updated).split(" ", 1)[0])
    except ValueError:
        msg = f"the newest change has no readable 'updated' date: {updated!r}"
        raise GerritQueryError(msg) from None


def _activity(rest: GerritRestAPI, members: list[dict[str, Any]], months: int, today: date) -> Iterator[dict[str, Any]]:
    """Yield one report entry per member, querying Gerrit as it goes."""
    since = months_before(today, months)
    for member in members:
        username = member["username"]
        email = member.get("email")
        try:
            updated = last_activity(rest, username, since)
            status = "ok"
            if updated is None:
                updated = last_activity(rest, username)
                status = "no_activity" if updated is None else "inactive"
        except AccountNotFoundError:
            updated, status = None, "no_account"
        yield {
            "username": username,
            "name": full_name(member),
            "email": email if isinstance(email, str) else "",
            "status": status,
            "last_activity": updated.isoformat() if updated else None,
            "days_ago": (today - updated).days if updated else None,
        }


#: Every character :meth:`str.splitlines` breaks a line at, as an escape.
_LINE_BREAK_ESCAPES = str.maketrans(
    {
        "\n": "\\n",
        "\r": "\\r",
        "\v": "\\v",
        "\f": "\\f",
        "\x1c": "\\x1c",
        "\x1d": "\\x1d",
        "\x1e": "\\x1e",
        "\x85": "\\x85",
        "\u2028": "\\u2028",
        "\u2029": "\\u2029",
    }
)


def format_entry(entry: dict[str, Any]) -> str:
    """Return the report line ``shell/inactivecommitters`` printed for ``entry``.

    A line break in the username, name or email is escaped, so each
    member stays on one line.
    """
    fields = (entry["username"], entry["name"], entry["email"])
    who = ", ".join(str(field).translate(_LINE_BREAK_ESCAPES) for field in fields)
    status = entry["status"]
    if status == "ok":
        return f"  OK {who} last submission or review {entry['last_activity']}"
    if status == "inactive":
        return f"  WARNING {who} inactive since {entry['last_activity']} {entry['days_ago']} days ago"
    if status == "no_account":
        return f"  ERROR {who} has no Gerrit account"
    return f"  ERROR {who} has no activity"


@committee_app.command("inactive")
def committee_inactive(
    gerrit_url: str = typer.Argument(
        ..., help="Gerrit host and path, such as gerrit.example.org/r; https:// is optional."
    ),
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
    months: int = typer.Option(
        DEFAULT_MONTHS, "--months", min=1, help="How many months back a change counts as recent activity."
    ),
    json_output: bool = typer.Option(False, "--json", help="Print a JSON array of the report entries."),
) -> None:
    """Report when each committee member last owned or reviewed a Gerrit change.

    Prints one line per member with a username: OK when their newest
    change is within --months, WARNING with its date when it is older,
    and ERROR when they have no change or no Gerrit account.
    """
    rest = gerrit_client(gerrit_url)
    try:
        client = LfxClient()
        members = get_committee_members(client, resolve_committee_uid(client, committee))
    except LfxError as exc:
        raise handle_lfx_error(exc, MEMBERS_FORBIDDEN_HINT) from None

    skipped = count_without_username(members)
    if skipped:
        noun = "member" if skipped == 1 else "members"
        typer.echo(f"Skipped {skipped} {noun} without a username, which Gerrit cannot be asked about", err=True)
    with_username = [
        member for member in sort_members(members) if isinstance(member.get("username"), str) and member["username"]
    ]

    if not json_output:
        echo(client.redact(f"checking {gerrit_url} participation for group {committee}"))
        echo()
    report = []
    try:
        for entry in _activity(rest, with_username, months, date.today()):
            if json_output:
                report.append(entry)
            else:
                echo(client.redact(format_entry(entry)))
    except GerritQueryError as exc:
        typer.echo(client.redact(f"Error: could not query Gerrit at {rest.url}: {exc}"), err=True)
        raise typer.Exit(code=EXIT_ERROR) from None
    if json_output:
        echo(json.dumps(client.redact_data(report), indent=2))


def _console_script(
    gerrit_url: str = typer.Argument(..., help="Gerrit host and path, such as gerrit.example.org/r."),
    committee: str = typer.Argument(..., help="Committee UID, or its SSO group name."),
) -> None:
    """Report when each committee member last owned or reviewed a Gerrit change."""
    committee_inactive(gerrit_url, committee, months=DEFAULT_MONTHS, json_output=False)


def main() -> None:
    """Run ``inactivecommitters GERRIT_URL COMMITTEE``, the console script."""
    typer.run(_console_script)
