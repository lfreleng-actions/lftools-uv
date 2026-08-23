# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""User-group resolution and listing.

Covers the built-in ``role:`` system groups, resolution of the
comma-separated group specs accepted by ``--allow-group`` and
``--can-remove-subscribers-group``, and the ``group list``
projection.
"""

from __future__ import annotations

from typing import Any

from .errors import (
    ZulipAmbiguityError,
    ZulipAPIError,
    ZulipLockoutError,
    ZulipNotFoundError,
    ZulipValidationError,
)

#: Display-name → API name mapping for built-in system role groups.
SYSTEM_ROLE_GROUPS: dict[str, str] = {
    "owners": "role:owners",
    "administrators": "role:administrators",
    "moderators": "role:moderators",
    "full members": "role:fullmembers",
    "members": "role:members",
    "everyone": "role:everyone",
    "nobody": "role:nobody",
}


#: Reverse of :data:`SYSTEM_ROLE_GROUPS`: maps the Zulip ``role:`` API name
#: to the human-facing display name presented in ``group list`` output and
#: accepted by ``--allow-group``/``--can-remove-subscribers-group``.
#:
#: Derived from :data:`SYSTEM_ROLE_GROUPS` to avoid drift — display names
#: are Title Case versions of the lowercase keys, with the historical
#: ``Full Members`` two-word form preserved.
def _build_system_role_display_names() -> dict[str, str]:
    overrides = {"full members": "Full Members"}
    return {
        api_name: overrides.get(display.lower(), display.title()) for display, api_name in SYSTEM_ROLE_GROUPS.items()
    }


SYSTEM_ROLE_DISPLAY_NAMES: dict[str, str] = _build_system_role_display_names()


def _fetch_groups(client: Any) -> list[dict[str, Any]]:
    """Return the raw user_groups listing from the Zulip server."""
    try:
        response = client.call_endpoint(url="user_groups", method="GET")
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to list user groups: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected user_groups response: {response!r}")
    groups = response.get("user_groups", [])
    if not isinstance(groups, list):
        raise ZulipAPIError(f"Malformed user_groups payload: {response!r}")
    return groups


def _resolve_single_group_token(token: str, groups: list[dict[str, Any]]) -> dict[str, Any]:
    """Resolve a single comma-item token to a group dict.

    Supports the ``id:NUM`` prefix and the system-role display-name
    mapping. The caller is expected to have stripped and filtered the
    input so ``token`` is always non-empty.

    Raises :class:`ZulipAmbiguityError`, :class:`ZulipNotFoundError`,
    or :class:`ZulipValidationError` as appropriate.
    """
    # ``resolve_groups`` filters empty/whitespace tokens before calling
    # this helper, so by construction ``token`` is non-empty here.
    if token.lower().startswith("id:"):
        suffix = token[3:].strip()
        try:
            wanted = int(suffix)
        except ValueError as exc:
            raise ZulipValidationError(f"id: prefix requires a numeric identifier, got {suffix!r}") from exc
        for grp in groups:
            if grp.get("id") == wanted:
                return grp
        raise ZulipNotFoundError(f"No user group with id {wanted}")

    api_name = SYSTEM_ROLE_GROUPS.get(token.casefold())
    if api_name is not None:
        for grp in groups:
            if grp.get("name") == api_name:
                return grp
        raise ZulipNotFoundError(f"System role group '{token}' not found on server")

    target = token.casefold()
    matches = [
        grp for grp in groups if str(grp.get("name", "")).casefold() == target and not grp.get("is_system_group", False)
    ]
    if not matches:
        if token.isdigit():
            raise ZulipNotFoundError(
                f"No user group named {token!r}. If you meant a numeric group ID, use 'id:{token}'."
            )
        raise ZulipNotFoundError(f"No user group named {token!r}")
    if len(matches) > 1:
        raise ZulipAmbiguityError(
            f"Group name {token!r} matched {len(matches)} groups; use the id:NUM prefix to disambiguate",
            matches=[{"id": g.get("id"), "name": g.get("name")} for g in matches],
        )
    return matches[0]


GroupSettingValue = int | dict[str, list[int]]


def _build_group_setting_value(group_ids: list[int]) -> GroupSettingValue:
    """Translate resolved group IDs into a Zulip group-setting value.

    Single group → simple int. Multiple groups → complex object with
    ``direct_members`` empty and ``direct_subgroups`` populated.
    """
    if len(group_ids) == 1:
        return group_ids[0]
    return {"direct_members": [], "direct_subgroups": group_ids}


def resolve_groups(
    client: Any,
    spec: str,
    *,
    allow_nobody: bool = True,
) -> tuple[list[dict[str, Any]], GroupSettingValue]:
    """Resolve a comma-separated ``--allow-group``-style argument.

    Returns a tuple ``(group_dicts, group_setting_value)`` suitable for
    sending to either the POST (raw value) or PATCH (wrapped under
    ``{"new": ...}``) endpoints. The caller is responsible for applying
    the PATCH wrapper.

    When ``allow_nobody`` is ``False`` (e.g. for lockout-prevention
    checks on private channel create/update), the helper raises
    :class:`ZulipLockoutError` if the resolved set is exactly the single
    ``Nobody`` system group.

    Empty / whitespace-only segments inside the comma-separated value
    are tolerated and stripped (so ``"design, , foo"`` is equivalent
    to ``"design, foo"``). A spec containing only empty segments is
    still rejected with :class:`ZulipValidationError`.
    """
    tokens = [t for t in (part.strip() for part in spec.split(",")) if t]
    if not tokens:
        raise ZulipValidationError("Group specification must not be empty")
    groups = _fetch_groups(client)
    resolved = [_resolve_single_group_token(tok, groups) for tok in tokens]
    if not allow_nobody and len(resolved) == 1 and resolved[0].get("name") == "role:nobody":
        raise ZulipLockoutError(
            "'Nobody' does not satisfy lockout prevention — it disables "
            "the permission entirely. Specify --subscribe users or a "
            "non-Nobody --allow-group."
        )
    group_ids: list[int] = []
    for grp in resolved:
        gid = grp.get("id")
        if not isinstance(gid, int):
            raise ZulipAPIError(f"Group object missing numeric id: {grp!r}")
        group_ids.append(gid)
    return resolved, _build_group_setting_value(group_ids)


def _normalize_group(raw: dict[str, Any]) -> dict[str, Any]:
    """Normalize a raw ``user_groups`` API entry to the lftools schema.

    Maps system role groups to their display names per
    :data:`SYSTEM_ROLE_DISPLAY_NAMES`; custom group names pass through
    unchanged. ``member_count`` is derived from the ``members`` array
    length, or ``0`` when the server omits ``members``.

    Raises :class:`ZulipAPIError` when required fields are missing or
    have unexpected types — ``id`` must be an int, ``name`` must be a
    non-empty string, ``members`` must be a list when present, and
    ``is_system_group`` (when present) must be a ``bool``. The
    ``description`` field is coerced to a string (Zulip historically
    returns an empty string when not set, but ``None`` is also
    tolerated).
    """
    raw_id = raw.get("id")
    if not isinstance(raw_id, int):
        raise ZulipAPIError(f"Group object missing numeric 'id': {raw!r}")
    api_name = raw.get("name")
    if not isinstance(api_name, str) or not api_name:
        raise ZulipAPIError(f"Group object missing string 'name': {raw!r}")
    members = raw.get("members", [])
    if not isinstance(members, list):
        raise ZulipAPIError(f"Group object has non-list 'members': {raw!r}")
    is_system_raw = raw.get("is_system_group", False)
    if not isinstance(is_system_raw, bool):
        raise ZulipAPIError(f"Group object has non-boolean 'is_system_group': {raw!r}")
    if is_system_raw:
        display = SYSTEM_ROLE_DISPLAY_NAMES.get(api_name, api_name)
    else:
        display = api_name
    description = raw.get("description")
    return {
        "group_id": raw_id,
        "name": display,
        "description": "" if description is None else str(description),
        "member_count": len(members),
        "type": "system" if is_system_raw else "custom",
    }


def list_groups(
    client: Any,
    *,
    group_name: str | None = None,
    group_id: int | None = None,
) -> list[dict[str, Any]]:
    """List Zulip user groups (custom and system role groups).

    Returns a list of normalized group dicts with keys ``group_id``,
    ``name``, ``description``, ``member_count``, and ``type`` (either
    ``"custom"`` or ``"system"``). System role groups are returned with
    their human display name (e.g. ``"Administrators"``) rather than
    the internal ``role:administrators`` API name.

    ``group_name`` and ``group_id`` are mutually exclusive filters.
    ``group_name`` matching is case-insensitive against the display
    name and applies after the system-role name mapping; a collision
    that resolves to more than one group raises
    :class:`ZulipAmbiguityError` with the matches listed.
    """
    if group_name is not None and group_id is not None:
        raise ZulipValidationError("Specify only one of --group-name or --group-id, not both")
    raw_groups = _fetch_groups(client)
    normalized: list[dict[str, Any]] = []
    for raw in raw_groups:
        if not isinstance(raw, dict):
            raise ZulipAPIError(f"Malformed user_groups entry (not a dict): {raw!r}")
        normalized.append(_normalize_group(raw))

    if group_id is not None:
        return [g for g in normalized if g["group_id"] == group_id]

    if group_name is not None:
        target = group_name.casefold()
        matches = [g for g in normalized if str(g["name"]).casefold() == target]
        if len(matches) > 1:
            raise ZulipAmbiguityError(
                f"Group name {group_name!r} matched {len(matches)} groups; use --group-id to disambiguate",
                matches=[{"group_id": m["group_id"], "name": m["name"]} for m in matches],
            )
        return matches

    return normalized
