# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Committee members from the LFX v2 API, and the formats lftools-uv prints.

Besides reading members, this module adds one, removes one and invites an
email address to a committee.

The formatters reproduce what ``lfidapi search-members``, ``ldap csv`` and
``shell/yaml4info`` printed for one group, except that CSV fields and
INFO.yaml values are quoted so a comma or an apostrophe in a name keeps
the output valid. :func:`format_info_yaml` is the one other modules call
to build the committers of an INFO.yaml file.
"""

from __future__ import annotations

import csv
import io
import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .committees import INVISIBLE_NOTE
from .errors import LfxAPIError, LfxNotFoundError

if TYPE_CHECKING:
    from collections.abc import Callable, Iterable

    from .client import LfxClient

#: What ``text`` prints in place of a missing username.
NO_USERNAME = "(no username)"

#: Usernames INFO.yaml never lists, as ``shell/yaml4info`` leaves them out.
INFO_YAML_EXCLUDED = frozenset({"lfservices_releng"})

#: The header that stops the committee service emailing the member about a change.
SKIP_NOTIFICATION_HEADER = "X-Skip-Notification"

# A local part is a run of ordinary characters or a quoted string, and a
# domain is a run of ordinary characters or an address literal in brackets.
# An apostrophe is ordinary in a local part except as its first character,
# so a message that wraps an address in single quotes keeps the opening one;
# a local part made of apostrophes alone is matched whole.
_EMAIL_ADDRESS = re.compile(
    r"""(?:"(?:[^"\\\r\n]|\\.)*"|[^\s@<>()\[\],;:'"][^\s@<>()\[\],;:"]*|'+)"""
    r"""@(?:\[[^\]\s]*\]|[^\s@<>()\[\],;:'"]+)"""
)


def _keep(value: str) -> str:
    return value


def get_committee_members(client: LfxClient, uid: str) -> list[dict[str, Any]]:
    """Return every member of the committee with ``uid``.

    ``GET /committees/{uid}/members`` answers the whole list without
    pages, from the committee service's own store. It needs the
    ``auditor`` relation on the committee.

    :raises LfxNotFoundError: The API answered 404.
    :raises LfxAPIError: Any other failure, 403 included.
    """
    path = _members_path(uid)
    try:
        body = client.get_json(path)
    except LfxAPIError as exc:
        if exc.status == 404:
            msg = f"{exc}; {INVISIBLE_NOTE}"
            raise LfxNotFoundError(msg) from None
        raise
    if not isinstance(body, list):
        msg = client.redact(f"GET {path} answered a body that is not a JSON array")
        raise LfxAPIError(msg)
    return [item for item in body if isinstance(item, dict)]


def _members_path(uid: str, member_uid: str | None = None) -> str:
    path = f"/committees/{quote(uid, safe='')}/members"
    return path if member_uid is None else f"{path}/{quote(member_uid, safe='')}"


def _notification_headers(notify: bool) -> dict[str, str]:
    return {} if notify else {SKIP_NOTIFICATION_HEADER: "true"}


def hide_emails(text: str) -> str:
    """Return ``text`` with every email address in it replaced by ``<email>``.

    Diagnostics pass through here, since a service message may quote the
    address a request carried.
    """
    return _EMAIL_ADDRESS.sub("<email>", text)


def add_committee_member(client: LfxClient, uid: str, body: dict[str, Any], *, notify: bool) -> dict[str, Any]:
    """Send ``POST /committees/{uid}/members`` with ``body`` and return the new member.

    The service sets the member's username itself, from the LF account
    that owns ``body["email"]``, and leaves it empty when none does. It
    emails the member unless ``notify`` is false. The token needs the
    ``writer`` relation on the committee.

    :raises LfxAPIError: The request failed or the API answered outside
        2xx, 409 for an address already a member included, or the answer
        is not a JSON object.
    """
    path = _members_path(uid)
    answer = client.post_json(path, body, headers=_notification_headers(notify))
    if not isinstance(answer, dict):
        msg = client.redact(f"POST {path} answered a body that is not a JSON object")
        raise LfxAPIError(msg)
    return answer


def _member_etag(client: LfxClient, uid: str, member_uid: str) -> str:
    path = _members_path(uid, member_uid)
    etag = client.get_response(path).headers.get("ETag")
    if not etag:
        msg = client.redact(f"GET {path} answered no ETag header")
        raise LfxAPIError(msg)
    return etag


def remove_committee_member(client: LfxClient, uid: str, member_uid: str, *, notify: bool) -> None:
    """Remove the member with ``member_uid`` from the committee with ``uid``.

    Reads the member for its ``ETag`` and sends ``DELETE`` with that
    value, unchanged, in ``If-Match``. When the member changed in
    between and the service answers 409, it reads the member again and
    retries once. The service emails the member unless ``notify`` is
    false. The token needs the ``writer`` relation on the committee.

    :raises LfxAPIError: Any failure, 404 for no such member and 409 when
        the retry also met a change included.
    """
    path = _members_path(uid, member_uid)
    headers = _notification_headers(notify)
    for attempt in (1, 2):
        headers["If-Match"] = _member_etag(client, uid, member_uid)
        try:
            client.delete(path, headers=headers)
        except LfxAPIError as exc:
            if exc.status == 409 and attempt == 1:
                continue
            raise
        return


def invite_to_committee(client: LfxClient, uid: str, email: str) -> dict[str, Any]:
    """Send ``POST /committees/{uid}/invites`` for ``email`` and return the invite.

    The token needs the ``inviter`` relation on the committee.

    :raises LfxAPIError: The request failed or the API answered outside
        2xx, 409 for a pending invite or an existing member included, or
        the answer is not a JSON object.
    """
    path = f"/committees/{quote(uid, safe='')}/invites"
    answer = client.post_json(path, {"invitee_email": email})
    if not isinstance(answer, dict):
        msg = client.redact(f"POST {path} answered a body that is not a JSON object")
        raise LfxAPIError(msg)
    return answer


def find_members(
    members: Iterable[dict[str, Any]], *, username: str | None = None, email: str | None = None
) -> list[dict[str, Any]]:
    """Return the ``members`` whose username or email address is the one given, ignoring case.

    Give exactly one of ``username`` and ``email``. Email addresses are
    also compared without surrounding whitespace, as the service
    compares them when it refuses a duplicate member.
    """
    if username is not None:
        wanted = username.casefold()
        return [member for member in members if wanted and _text(member, "username").casefold() == wanted]
    wanted = (email or "").strip().casefold()
    return [member for member in members if wanted and _text(member, "email").strip().casefold() == wanted]


def _text(member: dict[str, Any], key: str) -> str:
    value = member.get(key)
    return value if isinstance(value, str) else ""


def sort_members(members: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return ``members`` sorted by username, case-insensitively.

    Members without a username come last, sorted by email address.
    """

    def key(member: dict[str, Any]) -> tuple[bool, str, str, str]:
        username = _text(member, "username")
        return (not username, username.casefold(), username, _text(member, "email").casefold())

    return sorted(members, key=key)


def count_without_username(members: Iterable[dict[str, Any]]) -> int:
    """Return how many of ``members`` have no username."""
    return sum(1 for member in members if not _text(member, "username"))


def full_name(member: dict[str, Any]) -> str:
    """Return the member's first and last names, separated by a space."""
    return " ".join(part for part in (_text(member, "first_name"), _text(member, "last_name")) if part)


def company(member: dict[str, Any]) -> str:
    """Return the member's organisation name, or one derived from the email address.

    The derived name is the email domain without its last label, as
    ``shell/yaml4info`` derives it: ``jdoe@example.org`` gives ``example``.
    """
    organization = member.get("organization")
    if isinstance(organization, dict):
        name = organization.get("name")
        if isinstance(name, str) and name:
            return name
    domain = _text(member, "email").split("@", 1)[-1]
    return domain.rsplit(".", 1)[0]


def format_text(members: Iterable[dict[str, Any]], redact: Callable[[str], str] = _keep) -> str:
    """Return ``username <email>`` lines, as ``lfidapi search-members`` printed."""
    lines = [
        f"{redact(_text(member, 'username')) or NO_USERNAME} <{redact(_text(member, 'email'))}>"
        for member in sort_members(members)
    ]
    return "".join(f"{line}\n" for line in lines)


def format_csv(members: Iterable[dict[str, Any]], group: str, redact: Callable[[str], str] = _keep) -> str:
    """Return CSV rows of group, username, full name and email, as ``ldap csv`` printed.

    There is no header row. ``group`` is the committee's SSO group name,
    or its name when it has none.
    """
    # Older Python releases, 3.11.5 and 3.12.0 among them, quote a line break
    # under minimal quoting only when the line terminator holds it, so a bare
    # CR in a field would go out unquoted with "\n". Write each row with
    # "\r\n", which quotes both, and end it with "\n" as ldap csv did.
    buffer = io.StringIO()
    writer = csv.writer(buffer, lineterminator="\r\n")
    rows = []
    for member in sort_members(members):
        buffer.seek(0)
        buffer.truncate()
        fields = (group, _text(member, "username"), full_name(member), _text(member, "email"))
        writer.writerow([redact(field) for field in fields])
        rows.append(buffer.getvalue().removesuffix("\r\n") + "\n")
    return "".join(rows)


_YAML_ESCAPES = {
    "\0": "\\0",
    "\a": "\\a",
    "\b": "\\b",
    "\t": "\\t",
    "\n": "\\n",
    "\v": "\\v",
    "\f": "\\f",
    "\r": "\\r",
    "\x1b": "\\e",
    '"': '\\"',
    "\\": "\\\\",
    "\x85": "\\N",
    "\u2028": "\\L",
    "\u2029": "\\P",
}


def _yaml_plain_char(char: str) -> bool:
    # YAML's printable set, less tab, the line breaks YAML 1.1 adds and the BOM.
    code = ord(char)
    return (
        0x20 <= code <= 0x7E
        or 0xA0 <= code <= 0xD7FF
        or (0xE000 <= code <= 0xFFFD and code != 0xFEFF)
        or code >= 0x10000
    ) and char not in "\u2028\u2029"


def _yaml_escape(char: str) -> str:
    if char in _YAML_ESCAPES:
        return _YAML_ESCAPES[char]
    if _yaml_plain_char(char):
        return char
    code = ord(char)
    if code <= 0xFF:
        return f"\\x{code:02X}"
    return f"\\u{code:04X}"


def _yaml_quote(value: str) -> str:
    """Return ``value`` as a YAML scalar that stays on one line.

    Single quotes suit any value of printable characters. A value holding
    a line break or another control character takes double quotes and
    escapes instead, since a single-quoted scalar folds a line break into
    a space and would continue at column zero.
    """
    if all(_yaml_plain_char(char) for char in value):
        return "'" + value.replace("'", "''") + "'"
    return '"' + "".join(_yaml_escape(char) for char in value) + '"'


def format_info_yaml(members: Iterable[dict[str, Any]], redact: Callable[[str], str] = _keep) -> str:
    """Return one INFO.yaml committer entry per member, as ``shell/yaml4info`` printed.

    Members without a username, and those in :data:`INFO_YAML_EXCLUDED`,
    are left out. Every value is single-quoted with any ``'`` doubled,
    except one holding a line break or another control character, which
    is double-quoted with that character escaped.
    """
    entries: list[str] = []
    for member in sort_members(members):
        username = _text(member, "username")
        if not username or username in INFO_YAML_EXCLUDED:
            continue
        fields = (
            ("name", full_name(member)),
            ("email", _text(member, "email")),
            ("company", company(member)),
            ("id", username),
        )
        lines = [f"      {key}: {_yaml_quote(redact(value))}" for key, value in fields]
        lines[0] = "    - " + lines[0].lstrip()
        lines.append("      timezone: 'Unknown/Unknown'")
        entries.append("".join(f"{line}\n" for line in lines))
    return "".join(entries)


__all__ = [
    "INFO_YAML_EXCLUDED",
    "NO_USERNAME",
    "SKIP_NOTIFICATION_HEADER",
    "add_committee_member",
    "company",
    "count_without_username",
    "find_members",
    "format_csv",
    "format_info_yaml",
    "format_text",
    "full_name",
    "get_committee_members",
    "hide_emails",
    "invite_to_committee",
    "remove_committee_member",
    "sort_members",
]
