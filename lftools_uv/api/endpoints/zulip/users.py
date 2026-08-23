# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""User resolution and listing.

Resolution accepts email, numeric id or full name (the ``--by-*``
flags); listing projects raw ``members`` entries to the CLI shape.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any, Literal

from .errors import ZulipAmbiguityError, ZulipAPIError, ZulipNotFoundError, ZulipValidationError

IdMode = Literal["email", "id", "name"]


def _fetch_users(client: Any) -> list[dict[str, Any]]:
    """Return the raw user listing from the Zulip server."""
    try:
        response = client.get_members({"include_custom_profile_fields": False})
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to list users: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected users response: {response!r}")
    members = response.get("members", [])
    if not isinstance(members, list):
        raise ZulipAPIError(f"Malformed users payload: {response!r}")
    return members


def _resolve_single_user(
    ident: str,
    members: list[dict[str, Any]],
    *,
    mode: IdMode,
) -> dict[str, Any]:
    """Resolve a single user identifier against a pre-fetched member list.

    Factored out of :func:`resolve_users` so that callers needing
    per-identifier error handling (e.g. bulk mutations that report
    partial failures) can drive the loop themselves and capture
    failures one-by-one instead of aborting on the first bad entry.

    Raises :class:`ZulipValidationError` for malformed input,
    :class:`ZulipNotFoundError` when the identifier matches nothing,
    and :class:`ZulipAmbiguityError` when a lookup matches more than one
    user. Ambiguity is normally expected only for full-name lookups, but
    malformed member payloads can also duplicate email or ID matches.
    """
    ident = ident.strip()
    if not ident:
        raise ZulipValidationError("User identifier must not be empty")
    if mode == "email":
        matches = [u for u in members if u.get("delivery_email") == ident or u.get("email") == ident]
    elif mode == "id":
        try:
            wanted = int(ident)
        except ValueError as exc:
            raise ZulipValidationError(f"--by-id requires a numeric identifier, got {ident!r}") from exc
        matches = [u for u in members if u.get("user_id") == wanted]
    elif mode == "name":
        matches = [u for u in members if u.get("full_name") == ident]
    else:  # pragma: no cover - guarded by Literal
        raise ZulipValidationError(f"Unknown user id mode: {mode!r}")

    if not matches:
        raise ZulipNotFoundError(f"No user found matching {ident!r} (--by-{mode})")
    if len(matches) > 1:
        raise ZulipAmbiguityError(
            f"User name {ident!r} matched {len(matches)} users; use --by-email or --by-id to disambiguate",
            matches=[
                {
                    "user_id": m.get("user_id"),
                    "full_name": m.get("full_name"),
                    "email": m.get("delivery_email") or m.get("email"),
                }
                for m in matches
            ],
        )
    return matches[0]


def resolve_users(
    client: Any,
    identifiers: Iterable[str],
    *,
    mode: IdMode,
) -> list[dict[str, Any]]:
    """Resolve a list of user identifiers per the chosen ``mode``.

    Returns one user dict per identifier in input order. Raises
    :class:`ZulipNotFoundError` when an identifier resolves to nothing,
    or :class:`ZulipAmbiguityError` (mode ``name`` only) when a
    full-name lookup matches more than one user. Email and ID lookups
    are unique by construction.
    """
    members = _fetch_users(client)
    return [_resolve_single_user(ident, members, mode=mode) for ident in identifiers]


def _normalize_user(member: dict[str, Any]) -> dict[str, Any]:
    """Project a raw Zulip ``members`` entry to the CLI/JSON contract shape.

    Matches the schema documented in ``contracts/cli-commands.md`` for
    ``zulip user list``: ``user_id``, ``full_name``, ``email``,
    ``is_bot``, ``is_active``.

    Behavioural notes:

    * ``full_name`` / ``email`` are coerced via ``str(...)``; only an
      explicit ``None`` (or missing key) collapses to ``""`` so that
      legitimate falsy-but-stringifiable values are preserved.
    * ``user_id`` is required and validated to be an ``int``; the
      Zulip API guarantees this, so a missing or non-numeric value
      indicates a malformed payload and raises
      :class:`ZulipAPIError`.
    """
    user_id = member.get("user_id")
    if not isinstance(user_id, int):
        raise ZulipAPIError(f"Malformed user payload: missing/invalid user_id in {member!r}")
    full_name = member.get("full_name")
    email = member.get("email")
    return {
        "user_id": user_id,
        "full_name": "" if full_name is None else str(full_name),
        "email": "" if email is None else str(email),
        "is_bot": bool(member.get("is_bot", False)),
        "is_active": bool(member.get("is_active", True)),
    }


def list_users(
    client: Any,
    *,
    include_bots: bool = False,
    include_deactivated: bool = False,
) -> list[dict[str, Any]]:
    """List users on the Zulip server (US2).

    Defaults exclude bot accounts and deactivated users, matching the
    CLI's default behavior. Pass ``include_bots=True`` /
    ``include_deactivated=True`` to relax those filters independently.

    Returns a list of normalized user dicts in the order the server
    returned them. Raises :class:`ZulipAPIError` on transport / server
    errors.
    """
    members = _fetch_users(client)
    result: list[dict[str, Any]] = []
    for member in members:
        if not include_bots and member.get("is_bot", False):
            continue
        if not include_deactivated and not member.get("is_active", True):
            continue
        result.append(_normalize_user(member))
    return result
