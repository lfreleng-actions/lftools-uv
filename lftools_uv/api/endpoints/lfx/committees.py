# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Committee lookup, reads and creation against the LFX v2 API.

Every ``lfx`` command that takes a committee resolves it through
:func:`resolve_committee_uid`, which accepts a UID or an SSO group name.
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any
from urllib.parse import quote

from .errors import LfxAmbiguityError, LfxAPIError, LfxNotFoundError

if TYPE_CHECKING:
    from .client import LfxClient

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)

#: The note every "not found" carries: the API hides what the caller may
#: not see, and serves a bad token as anonymous.
INVISIBLE_NOTE = "a committee the token cannot see looks the same as one that does not exist"


#: The values the committee service accepts for ``category``.
COMMITTEE_CATEGORIES = (
    "Ambassador",
    "Board",
    "Code of Conduct",
    "Committers",
    "Expert Group",
    "Finance Committee",
    "Government Advisory Council",
    "Legal Committee",
    "Maintainers",
    "Marketing Committee/Sub Committee",
    "Marketing Mailing List",
    "Marketing Oversight Committee/Marketing Advisory Committee",
    "Newsletter",
    "Other",
    "Product Security",
    "Special Interest Group",
    "Technical Advisory Committee",
    "Technical Mailing List",
    "Technical Oversight Committee",
    "Technical Steering Committee",
    "Working Group",
)

#: The values the committee service accepts for ``join_mode``.
JOIN_MODES = ("open", "invite_only", "application", "closed")


def is_uuid(value: str) -> bool:
    """Return ``True`` when ``value`` is a UUID in its hyphenated form."""
    return bool(_UUID_RE.match(value))


def query_resources(client: LfxClient, params: dict[str, str]) -> list[dict[str, Any]]:
    """Return every resource a query matches, across all pages.

    :raises LfxAPIError: A request failed or a page is malformed.
    """
    resources: list[dict[str, Any]] = []
    seen_tokens: set[str] = set()
    page_params = dict(params)
    while True:
        body = client.get_json("/query/resources", page_params)
        if not isinstance(body, dict) or not isinstance(body.get("resources"), list):
            msg = "GET /query/resources answered a body without a 'resources' list"
            raise LfxAPIError(msg)
        resources.extend(item for item in body["resources"] if isinstance(item, dict))
        page_token = body.get("page_token")
        if not page_token:
            return resources
        page_token = str(page_token)
        if page_token in seen_tokens:
            msg = "GET /query/resources repeated a page_token; stopping rather than looping"
            raise LfxAPIError(msg)
        seen_tokens.add(page_token)
        page_params = {**params, "page_token": page_token}


def find_committee_uids(client: LfxClient, sso_group_name: str) -> list[str]:
    """Return the UIDs of the committees whose SSO group name is exactly this one.

    :raises LfxNotFoundError: The query service answered 404.
    :raises LfxAPIError: Any other failure.
    """
    try:
        resources = query_resources(client, {"type": "committee", "tags": f"sso_group_name:{sso_group_name}"})
    except LfxAPIError as exc:
        if exc.status == 404:
            msg = f"{exc}; {INVISIBLE_NOTE}"
            raise LfxNotFoundError(msg) from None
        raise
    uids: list[str] = []
    for resource in resources:
        data = resource.get("data")
        if not isinstance(data, dict) or data.get("sso_group_name") != sso_group_name:
            continue
        uid = data.get("uid")
        if isinstance(uid, str) and uid and uid not in uids:
            uids.append(uid)
    return uids


def resolve_committee_uid(client: LfxClient, committee: str) -> str:
    """Return the UID of a committee named by UID or SSO group name.

    A UUID is taken as the UID without a request. Anything else is an
    SSO group name, which must match exactly one committee.

    :raises LfxNotFoundError: No visible committee has the name, or the
        query service answered 404.
    :raises LfxAmbiguityError: More than one committee has the name.
    """
    if is_uuid(committee):
        return committee.lower()
    uids = find_committee_uids(client, committee)
    # Redact before quoting: repr() would escape a backslash in the token,
    # and the escaped form would no longer match it.
    shown = client.redact(committee)
    if not uids:
        msg = f"no committee has the SSO group name {shown!r}; {INVISIBLE_NOTE}"
        raise LfxNotFoundError(msg)
    if len(uids) > 1:
        msg = f"{len(uids)} committees have the SSO group name {shown!r}: {client.redact(', '.join(uids))}"
        raise LfxAmbiguityError(msg)
    return uids[0]


def get_committee(client: LfxClient, uid: str) -> dict[str, Any]:
    """Return the body of ``GET /committees/{uid}``.

    :raises LfxNotFoundError: The API answered 404.
    :raises LfxAPIError: Any other failure, 403 included.
    """
    path = f"/committees/{quote(uid, safe='')}"
    try:
        body = client.get_json(path)
    except LfxAPIError as exc:
        if exc.status == 404:
            msg = f"{exc}; {INVISIBLE_NOTE}"
            raise LfxNotFoundError(msg) from None
        raise
    if not isinstance(body, dict):
        msg = client.redact(f"GET {path} answered a body that is not a JSON object")
        raise LfxAPIError(msg)
    return body


def show_committee(client: LfxClient, committee: str) -> dict[str, Any]:
    """Resolve a committee by UID or SSO group name and read it."""
    return get_committee(client, resolve_committee_uid(client, committee))


def _query_or_not_found(client: LfxClient, params: dict[str, str], note: str) -> list[dict[str, Any]]:
    """Return :func:`query_resources`, raising :class:`LfxNotFoundError` on 404."""
    try:
        return query_resources(client, params)
    except LfxAPIError as exc:
        if exc.status == 404:
            msg = f"{exc}; {note}"
            raise LfxNotFoundError(msg) from None
        raise


def find_project_uid(client: LfxClient, slug: str) -> str:
    """Return the UID of the project whose slug is exactly ``slug``.

    :raises LfxNotFoundError: No visible project has the slug, or the
        query service answered 404.
    :raises LfxAmbiguityError: More than one project has the slug.
    """
    note = "a project the token cannot see looks the same as one that does not exist"
    resources = _query_or_not_found(client, {"type": "project", "filters": f"slug:{slug}"}, note)
    uids: list[str] = []
    for resource in resources:
        data = resource.get("data")
        if not isinstance(data, dict) or data.get("slug") != slug:
            continue
        uid = data.get("uid")
        if isinstance(uid, str) and uid and uid not in uids:
            uids.append(uid)
    shown = client.redact(slug)
    if not uids:
        msg = f"no project has the slug {shown!r}; {note}"
        raise LfxNotFoundError(msg)
    if len(uids) > 1:
        msg = f"{len(uids)} projects have the slug {shown!r}: {client.redact(', '.join(uids))}"
        raise LfxAmbiguityError(msg)
    return uids[0]


def _name_key(committee: dict[str, Any]) -> tuple[str, str, str]:
    name = committee.get("name")
    uid = committee.get("uid")
    name = name if isinstance(name, str) else ""
    return (name.casefold(), name, uid if isinstance(uid, str) else "")


def list_project_committees(client: LfxClient, slug: str) -> list[dict[str, Any]]:
    """Return the ``data`` of every committee of the project with ``slug``, sorted by name.

    The project must exist and be visible; its committees are those the
    token can see, so the list may be empty.

    :raises LfxNotFoundError: As :func:`find_project_uid`.
    :raises LfxAmbiguityError: As :func:`find_project_uid`.
    :raises LfxAPIError: Any other failure.
    """
    find_project_uid(client, slug)
    resources = _query_or_not_found(client, {"type": "committee", "tags": f"project_slug:{slug}"}, INVISIBLE_NOTE)
    committees: list[dict[str, Any]] = []
    seen: set[str] = set()
    for resource in resources:
        data = resource.get("data")
        if not isinstance(data, dict):
            continue
        uid = data.get("uid")
        if not isinstance(uid, str) or not uid or uid in seen:
            continue
        seen.add(uid)
        committees.append(data)
    return sorted(committees, key=_name_key)


def create_committee(client: LfxClient, body: dict[str, Any]) -> dict[str, Any]:
    """Send ``POST /committees`` with ``body`` and return the created committee.

    The caller checks ``category`` and ``join_mode`` against
    :data:`COMMITTEE_CATEGORIES` and :data:`JOIN_MODES` first.

    :raises LfxAPIError: The request failed or the API answered outside
        2xx, 409 for a name the project already uses included, or the
        answer is not a JSON object.
    """
    answer = client.post_json("/committees", body)
    if not isinstance(answer, dict):
        msg = "POST /committees answered a body that is not a JSON object"
        raise LfxAPIError(msg)
    return answer


__all__ = [
    "COMMITTEE_CATEGORIES",
    "INVISIBLE_NOTE",
    "JOIN_MODES",
    "create_committee",
    "find_committee_uids",
    "find_project_uid",
    "get_committee",
    "is_uuid",
    "list_project_committees",
    "query_resources",
    "resolve_committee_uid",
    "show_committee",
]
