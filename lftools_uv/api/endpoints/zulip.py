# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Zulip REST API helpers for lftools-uv.

This module is the API/business-logic layer for the ``lftools-uv zulip``
command group. It is intentionally import-safe even when the optional
``zulip`` extra is not installed: the import of the upstream ``zulip``
Python package is wrapped so that callers can detect availability via
:func:`zulip_available` and surface a friendly install hint from the CLI
layer (FR-022).

Public surface:

* Configuration resolution — :class:`ZulipConfig`,
  :func:`resolve_config` (precedence per FR-011/FR-012).
* Client factory — :func:`get_client`.
* Feature-level detection — :func:`get_server_feature_level`,
  :func:`check_feature_level` (FR-019 canonical error format).
* Resolution helpers — :func:`resolve_channel`, :func:`resolve_users`,
  :func:`resolve_groups`.
* Domain exceptions — :class:`ZulipConfigError`, :class:`ZulipAPIError`,
  :class:`ZulipFeatureLevelError`, :class:`ZulipAmbiguityError`,
  :class:`ZulipLockoutError`, :class:`ZulipNotFoundError`,
  :class:`ZulipValidationError`.

See ``specs/001-zulip-channel-mgmt/`` for the full feature design.
"""

from __future__ import annotations

import configparser
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from lftools_uv import config as lf_config

try:  # pragma: no cover - import guard exercised by integration tests
    import zulip as _zulip_module
except ImportError:  # pragma: no cover - exercised when extra not installed
    _zulip_module = None

if TYPE_CHECKING:  # pragma: no cover
    import zulip as _zulip_module_type  # noqa: F401

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Domain exceptions
# ---------------------------------------------------------------------------


class ZulipError(Exception):
    """Base class for all Zulip-related errors raised by this module."""


class ZulipConfigError(ZulipError):
    """Raised when Zulip configuration cannot be located or parsed."""


class ZulipAPIError(ZulipError):
    """Raised when the Zulip server returns an error response."""


class ZulipFeatureLevelError(ZulipError):
    """Raised when the server lacks the required Zulip feature level.

    The string form follows the FR-019 canonical format
    ``This operation requires Zulip feature level X (server has Y)``.
    """

    def __init__(self, required: int, actual: int, feature_name: str = "") -> None:
        self.required = required
        self.actual = actual
        self.feature_name = feature_name
        message = f"This operation requires Zulip feature level {required} (server has {actual})"
        super().__init__(message)


class ZulipAmbiguityError(ZulipError):
    """Raised when a name lookup matches more than one entity."""

    def __init__(self, message: str, matches: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.matches = matches or []


class ZulipNotFoundError(ZulipError):
    """Raised when a channel/user/group cannot be located by name or id."""


class ZulipLockoutError(ZulipError):
    """Raised when an operation would lock all users out of a channel."""


class ZulipValidationError(ZulipError):
    """Raised for client-side validation failures (e.g. mutex flags)."""


# ---------------------------------------------------------------------------
# Optional-dependency detection
# ---------------------------------------------------------------------------


def zulip_available() -> bool:
    """Return ``True`` when the optional ``zulip`` package is importable."""
    return _zulip_module is not None


def _require_zulip() -> Any:
    """Return the imported ``zulip`` module or raise :class:`ZulipConfigError`.

    The CLI layer normally short-circuits before this is reached (it
    presents the canonical FR-022 install hint when the extra is
    missing); ``_require_zulip`` exists so that the API layer can be
    consumed programmatically with a clear error when the extra is not
    installed.
    """
    if _zulip_module is None:  # pragma: no cover - defensive
        raise ZulipConfigError(
            "The 'zulip' Python package is not installed. Install with: pip install \"lftools-uv[zulip]\""
        )
    return _zulip_module


# ---------------------------------------------------------------------------
# Configuration resolution (FR-011 / FR-012)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ZulipConfig:
    """Resolved Zulip API credentials.

    Either ``config_path`` (a path to a zuliprc-format file) OR the
    three credential fields will be populated, depending on which
    source produced the configuration. The :func:`get_client` factory
    handles both cases transparently.
    """

    email: str | None = None
    api_key: str | None = None
    site: str | None = None
    config_path: Path | None = None
    source: str = "unknown"


_ZULIPRC_API_SECTION = "api"
_LFTOOLS_ZULIP_SECTION = "zulip"


def _load_zuliprc(path: Path) -> ZulipConfig:
    """Validate a zuliprc-format file and return a :class:`ZulipConfig`.

    The file is not parsed here for credential extraction — the
    ``zulip.Client`` consumes the file directly. Parsing only validates
    that the file is readable and contains the expected ``[api]``
    section, producing a clear error otherwise.
    """
    parser = configparser.ConfigParser()
    try:
        with path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except OSError as exc:
        raise ZulipConfigError(f"Cannot read Zulip config file {path}: {exc}") from exc
    except configparser.Error as exc:
        raise ZulipConfigError(f"Malformed Zulip config file {path}: {exc}") from exc

    if not parser.has_section(_ZULIPRC_API_SECTION):
        raise ZulipConfigError(f"Zulip config file {path} is missing required [api] section")
    return ZulipConfig(config_path=path, source=str(path))


def _load_lftools_ini() -> ZulipConfig | None:
    """Return a :class:`ZulipConfig` synthesized from ``lftools.ini``.

    Returns ``None`` when the ``[zulip]`` section is absent.
    """
    if not lf_config.has_section(_LFTOOLS_ZULIP_SECTION):
        return None
    try:
        email = lf_config.get_setting(_LFTOOLS_ZULIP_SECTION, "email")
        api_key = lf_config.get_setting(_LFTOOLS_ZULIP_SECTION, "key")
        site = lf_config.get_setting(_LFTOOLS_ZULIP_SECTION, "site")
    except (configparser.NoOptionError, configparser.NoSectionError) as exc:
        raise ZulipConfigError(f"lftools.ini [zulip] section is incomplete: {exc}") from exc
    if not (isinstance(email, str) and isinstance(api_key, str) and isinstance(site, str)):
        raise ZulipConfigError("lftools.ini [zulip] section must define email, key, site")
    return ZulipConfig(
        email=email,
        api_key=api_key,
        site=site,
        source="lftools.ini[zulip]",
    )


def resolve_config(
    zuliprc: Path | None = None,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> ZulipConfig:
    """Resolve Zulip configuration using the FR-011/FR-012 precedence chain.

    Precedence (first match wins):

    1. ``zuliprc`` argument (from ``--zuliprc`` CLI flag).
    2. ``./zuliprc`` in the current working directory.
    3. ``[zulip]`` section in ``lftools.ini``.
    4. ``~/.zuliprc``.

    Parameters ``cwd`` and ``home`` allow tests to inject filesystem
    locations; defaults are ``Path.cwd()`` and ``Path.home()``.

    Raises :class:`ZulipConfigError` when no source resolves.
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()

    if zuliprc is not None:
        path = Path(zuliprc)
        if not path.exists():
            raise ZulipConfigError(f"--zuliprc path does not exist: {path}")
        return _load_zuliprc(path)

    cwd_candidate = cwd / "zuliprc"
    if cwd_candidate.exists():
        return _load_zuliprc(cwd_candidate)

    ini_config = _load_lftools_ini()
    if ini_config is not None:
        return ini_config

    home_candidate = home / ".zuliprc"
    if home_candidate.exists():
        return _load_zuliprc(home_candidate)

    raise ZulipConfigError(
        "No Zulip configuration found. Searched: --zuliprc flag, ./zuliprc, lftools.ini [zulip] section, ~/.zuliprc"
    )


# ---------------------------------------------------------------------------
# Client factory
# ---------------------------------------------------------------------------


def get_client(zuliprc: Path | None = None, *, config: ZulipConfig | None = None) -> Any:
    """Instantiate a ``zulip.Client`` from the resolved configuration.

    ``zuliprc`` and ``config`` are mutually exclusive; supply at most one.
    When neither is given, configuration is resolved via
    :func:`resolve_config`.
    """
    if zuliprc is not None and config is not None:
        raise ZulipValidationError("Pass either 'zuliprc' or 'config', not both")
    resolved = config or resolve_config(zuliprc)
    zulip_module = _require_zulip()
    if resolved.config_path is not None:
        return zulip_module.Client(config_file=str(resolved.config_path))
    # No zuliprc file — all three credential fields must be populated.
    missing: list[str] = []
    if not (isinstance(resolved.email, str) and resolved.email.strip()):
        missing.append("email")
    if not (isinstance(resolved.api_key, str) and resolved.api_key.strip()):
        missing.append("api_key")
    if not (isinstance(resolved.site, str) and resolved.site.strip()):
        missing.append("site")
    if missing:
        raise ZulipConfigError(f"Incomplete Zulip credentials from {resolved.source}: missing {', '.join(missing)}")
    return zulip_module.Client(
        email=resolved.email,
        api_key=resolved.api_key,
        site=resolved.site,
    )


# ---------------------------------------------------------------------------
# Feature-level detection (FR-019)
# ---------------------------------------------------------------------------


#: Hardcoded feature-level thresholds determined by consulting the Zulip
#: changelog. Each name maps to the minimum ``zulip_feature_level`` that
#: a server must report before the corresponding capability is exposed.
#:
#: References (Zulip changelog,
#: https://zulip.com/api/changelog):
#:
#: * Feature level 1 — initial introduction of the
#:   ``zulip_feature_level`` field; all servers we target report >= 1.
#: * Feature level 12 — web-public streams and spectator access.
#: * Feature level 197 — group-based access control via
#:   ``can_access_group``.
#: * Feature level 161 — ``can_remove_subscribers_group`` permission.
#: * Feature level 334 — ``topic_policy`` per-channel field.
#: * Feature level 59 — stream reactivation (unarchive) endpoint.
FEATURE_LEVELS: dict[str, int] = {
    "web-public": 12,
    "can-access-group": 197,
    "can-remove-subscribers-group": 161,
    "topic-policy": 334,
    "unarchive": 59,
}


def get_server_feature_level(client: Any) -> int:
    """Return the server's reported ``zulip_feature_level``.

    The result is cached on the client instance as ``_lftools_feature_level``
    to avoid repeated HTTP calls within a single CLI invocation.
    """
    cached = getattr(client, "_lftools_feature_level", None)
    if isinstance(cached, int):
        return cached
    try:
        response = client.get_server_settings()
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to query server settings: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected server_settings response: {response!r}")
    level = response.get("zulip_feature_level")
    if not isinstance(level, int):
        # Some very old servers omit the field; treat as level 0.
        level = 0
    try:
        client._lftools_feature_level = level
    except AttributeError:  # pragma: no cover - defensive
        pass
    return level


def check_feature_level(
    client: Any,
    required_level: int,
    feature_name: str = "",
) -> None:
    """Raise :class:`ZulipFeatureLevelError` when server feature level is too low."""
    actual = get_server_feature_level(client)
    if actual < required_level:
        raise ZulipFeatureLevelError(
            required=required_level,
            actual=actual,
            feature_name=feature_name,
        )


# ---------------------------------------------------------------------------
# Channel resolution
# ---------------------------------------------------------------------------


def _fetch_streams(client: Any, include_archived: bool) -> list[dict[str, Any]]:
    """Return the raw stream listing from the Zulip server.

    Includes archived streams when ``include_archived`` is ``True``.
    """
    request: dict[str, Any] = {
        "include_public": True,
        "include_subscribed": True,
        "include_all_active": True,
    }
    if include_archived:
        request["include_archived"] = True
    try:
        response = client.call_endpoint(url="streams", method="GET", request=request)
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to list channels: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected streams response: {response!r}")
    streams = response.get("streams", [])
    if not isinstance(streams, list):
        raise ZulipAPIError(f"Malformed streams payload: {response!r}")
    return streams


def resolve_channel(
    client: Any,
    *,
    name: str | None = None,
    channel_id: int | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Resolve a channel by name (case-insensitive) or numeric ID.

    Returns the raw stream dict from the Zulip API. Raises
    :class:`ZulipNotFoundError` when no match exists. When the channel
    exists only in the archived set and ``include_archived`` is
    ``False``, the error message advises adding ``--include-archived``
    per FR-018.
    """
    if (name is None) == (channel_id is None):
        raise ZulipValidationError("resolve_channel requires exactly one of 'name' or 'channel_id'")
    active_streams = _fetch_streams(client, include_archived=include_archived)

    if channel_id is not None:
        for stream in active_streams:
            if stream.get("stream_id") == channel_id:
                return stream
        if not include_archived:
            archived_streams = _fetch_streams(client, include_archived=True)
            for stream in archived_streams:
                if stream.get("stream_id") == channel_id:
                    raise ZulipNotFoundError(
                        f"Channel id {channel_id} is archived. Use --include-archived to operate on archived channels."
                    )
        raise ZulipNotFoundError(f"No channel with id {channel_id}")

    assert name is not None  # for type narrowing
    target = name.casefold()
    for stream in active_streams:
        if str(stream.get("name", "")).casefold() == target:
            return stream
    if not include_archived:
        archived_streams = _fetch_streams(client, include_archived=True)
        for stream in archived_streams:
            if str(stream.get("name", "")).casefold() == target:
                raise ZulipNotFoundError(
                    f"Channel '{name}' is archived. Use --include-archived to operate on archived channels."
                )
    raise ZulipNotFoundError(f"Channel '{name}' not found")


# ---------------------------------------------------------------------------
# User resolution
# ---------------------------------------------------------------------------


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
    resolved: list[dict[str, Any]] = []
    for raw in identifiers:
        ident = raw.strip()
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
        resolved.append(matches[0])
    return resolved


# ---------------------------------------------------------------------------
# Group resolution
# ---------------------------------------------------------------------------


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


# ---------------------------------------------------------------------------
# US1 — List Channels (T022)
# ---------------------------------------------------------------------------


def _normalize_channel(stream: dict[str, Any]) -> dict[str, Any]:
    """Project a raw Zulip stream dict into the documented shape.

    Returns a stable subset of fields per ``data-model.md`` with a
    derived ``type`` of ``public``, ``private``, or ``web-public``.
    ``stream_id`` is required and validated as an ``int``;
    ``subscriber_count`` defaults to ``0`` when missing or not numeric
    so that downstream consumers can rely on it being an integer.
    """
    stream_id = stream.get("stream_id")
    if not isinstance(stream_id, int):
        raise ZulipAPIError(f"Stream object missing numeric stream_id: {stream!r}")
    if stream.get("is_web_public"):
        channel_type = "web-public"
    elif stream.get("invite_only"):
        channel_type = "private"
    else:
        channel_type = "public"
    raw_count = stream.get("subscriber_count")
    subscriber_count = raw_count if isinstance(raw_count, int) else 0
    raw_name = stream.get("name")
    raw_desc = stream.get("description")
    return {
        "stream_id": stream_id,
        "name": str(raw_name) if isinstance(raw_name, str) else "",
        "description": str(raw_desc) if isinstance(raw_desc, str) else "",
        "type": channel_type,
        "subscriber_count": subscriber_count,
        "is_archived": bool(stream.get("is_archived", False)),
    }


def list_channels(client: Any, *, include_archived: bool = False) -> list[dict[str, Any]]:
    """Return a normalized list of channels visible to the authenticated user.

    When ``include_archived`` is ``False`` (the default), only active
    streams are returned. When ``True``, the server's streams endpoint
    is queried with ``include_archived=True`` so that the response
    already contains both active and archived streams in a single call.

    Each entry is the dict produced by :func:`_normalize_channel`.
    """
    streams = _fetch_streams(client, include_archived=include_archived)
    return [_normalize_channel(s) for s in streams]


# ---------------------------------------------------------------------------
# User listing (US2)
# ---------------------------------------------------------------------------


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
