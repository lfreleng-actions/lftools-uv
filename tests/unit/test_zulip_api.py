# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Unit tests for the Zulip API endpoint helpers.

Covers the foundational tasks T016–T019:

* T016 — feature-level detection
* T017 — channel target resolution
* T018 — group resolution
* T019 — user resolution
"""

from __future__ import annotations

import json as _json
from typing import Any
from unittest import mock

import pytest

from lftools_uv.api.endpoints.zulip import (
    FEATURE_LEVELS,
    SYSTEM_ROLE_GROUPS,
    ZulipAmbiguityError,
    ZulipAPIError,
    ZulipConfig,
    ZulipConfigError,
    ZulipFeatureLevelError,
    ZulipLockoutError,
    ZulipNotFoundError,
    ZulipValidationError,
    check_feature_level,
    get_client,
    get_server_feature_level,
    list_channels,
    list_groups,
    list_users,
    resolve_channel,
    resolve_groups,
    resolve_users,
    subscribe_users,
    unsubscribe_users,
)

# ---------------------------------------------------------------------------
# T016 — Feature-level detection
# ---------------------------------------------------------------------------


def _make_client(**responses: Any) -> Any:
    """Return a mock client with attribute-style API call stubs."""
    client = mock.MagicMock()
    if "server_settings" in responses:
        client.get_server_settings.return_value = responses["server_settings"]
    if "streams" in responses:
        client.call_endpoint.side_effect = None
        client.call_endpoint.return_value = responses["streams"]
    if "members" in responses:
        client.get_members.return_value = responses["members"]
    return client


def test_feature_level_caches_per_client() -> None:
    """``get_server_feature_level`` caches the value on the client."""
    client = _make_client(
        server_settings={"result": "success", "zulip_feature_level": 200},
    )
    assert get_server_feature_level(client) == 200
    assert get_server_feature_level(client) == 200
    assert client.get_server_settings.call_count == 1


def test_check_feature_level_passes_when_sufficient() -> None:
    """No error is raised when the server level meets the requirement."""
    client = _make_client(
        server_settings={"result": "success", "zulip_feature_level": 200},
    )
    check_feature_level(client, required_level=100, feature_name="topic-policy")


def test_check_feature_level_raises_canonical_error() -> None:
    """FR-019 canonical error string is produced when level too low."""
    client = _make_client(
        server_settings={"result": "success", "zulip_feature_level": 50},
    )
    with pytest.raises(ZulipFeatureLevelError) as exc_info:
        check_feature_level(client, required_level=161, feature_name="x")
    assert str(exc_info.value) == ("This operation requires Zulip feature level 161 (server has 50)")
    assert exc_info.value.required == 161
    assert exc_info.value.actual == 50


def test_feature_level_table_contains_expected_keys() -> None:
    """The hardcoded threshold table covers every feature the spec mentions."""
    for key in (
        "web-public",
        "can-access-group",
        "can-remove-subscribers-group",
        "topic-policy",
        "unarchive",
    ):
        assert key in FEATURE_LEVELS
        assert isinstance(FEATURE_LEVELS[key], int)
        assert FEATURE_LEVELS[key] >= 0


# ---------------------------------------------------------------------------
# T017 — Channel target resolution
# ---------------------------------------------------------------------------


ACTIVE_STREAMS = [
    {"stream_id": 1, "name": "general", "description": "g", "is_archived": False},
    {"stream_id": 2, "name": "Engineering", "description": "e", "is_archived": False},
]
ARCHIVED_STREAMS = ACTIVE_STREAMS + [
    {"stream_id": 99, "name": "old-channel", "description": "", "is_archived": True},
]


def _streams_client(active: list[dict[str, Any]], archived: list[dict[str, Any]]) -> Any:
    """Return a client whose ``streams`` endpoint returns the given lists.

    The first call (without ``include_archived``) returns ``active``;
    subsequent calls (with ``include_archived`` true) return ``archived``.
    """
    client = mock.MagicMock()

    def side_effect(*, url: str, method: str, request: dict[str, Any] | None = None) -> Any:
        assert url == "streams"
        assert method == "GET"
        if request and request.get("include_archived"):
            return {"result": "success", "streams": archived}
        return {"result": "success", "streams": active}

    client.call_endpoint.side_effect = side_effect
    return client


def test_resolve_channel_by_name_case_insensitive() -> None:
    """Channel name matching ignores case per FR-018."""
    client = _streams_client(ACTIVE_STREAMS, ARCHIVED_STREAMS)
    result = resolve_channel(client, name="GENERAL")
    assert result["stream_id"] == 1


def test_resolve_channel_by_id() -> None:
    """Channel id lookup returns the matching stream dict."""
    client = _streams_client(ACTIVE_STREAMS, ARCHIVED_STREAMS)
    result = resolve_channel(client, channel_id=2)
    assert result["name"] == "Engineering"


def test_resolve_channel_not_found_suggests_include_archived() -> None:
    """The not-found error mentions --include-archived for archived hits."""
    client = _streams_client(ACTIVE_STREAMS, ARCHIVED_STREAMS)
    with pytest.raises(ZulipNotFoundError, match="--include-archived"):
        _ = resolve_channel(client, name="old-channel")


def test_resolve_channel_genuinely_missing() -> None:
    """A non-existent channel produces a plain not-found error."""
    client = _streams_client(ACTIVE_STREAMS, ARCHIVED_STREAMS)
    with pytest.raises(ZulipNotFoundError, match="not found"):
        _ = resolve_channel(client, name="never-existed")


def test_resolve_channel_include_archived_returns_archived() -> None:
    """When ``include_archived`` is True, archived channels match directly."""
    client = _streams_client(ACTIVE_STREAMS, ARCHIVED_STREAMS)
    result = resolve_channel(client, name="old-channel", include_archived=True)
    assert result["stream_id"] == 99


def test_resolve_channel_rejects_missing_target() -> None:
    """Exactly one of name/channel_id must be supplied."""
    client = _streams_client(ACTIVE_STREAMS, ARCHIVED_STREAMS)
    with pytest.raises(ZulipValidationError):
        _ = resolve_channel(client)
    with pytest.raises(ZulipValidationError):
        _ = resolve_channel(client, name="x", channel_id=1)


# ---------------------------------------------------------------------------
# T018 — Group resolution
# ---------------------------------------------------------------------------


GROUPS = [
    {"id": 10, "name": "engineering", "is_system_group": False},
    {"id": 11, "name": "Engineering", "is_system_group": False},
    {"id": 20, "name": "role:administrators", "is_system_group": True},
    {"id": 21, "name": "role:nobody", "is_system_group": True},
    {"id": 22, "name": "role:members", "is_system_group": True},
    {"id": 30, "name": "design", "is_system_group": False},
]


def _groups_client(groups: list[dict[str, Any]]) -> Any:
    client = mock.MagicMock()
    client.call_endpoint.return_value = {
        "result": "success",
        "user_groups": groups,
    }
    return client


def test_resolve_groups_single_custom_group_returns_int() -> None:
    """A single custom group resolves to a simple integer setting value."""
    client = _groups_client(GROUPS)
    _, value = resolve_groups(client, "design")
    assert value == 30


def test_resolve_groups_multiple_groups_returns_complex_form() -> None:
    """Multiple groups produce the direct_subgroups complex form."""
    client = _groups_client(GROUPS)
    _, value = resolve_groups(client, "design, id:10")
    assert value == {"direct_members": [], "direct_subgroups": [30, 10]}


def test_resolve_groups_id_prefix() -> None:
    """The ``id:NUM`` prefix forces ID-based lookup."""
    client = _groups_client(GROUPS)
    resolved, value = resolve_groups(client, "id:11")
    assert resolved[0]["id"] == 11
    assert value == 11


def test_resolve_groups_system_role_display_name() -> None:
    """System role display names map to their internal ``role:`` API name."""
    client = _groups_client(GROUPS)
    resolved, value = resolve_groups(client, "Administrators")
    assert resolved[0]["name"] == "role:administrators"
    assert value == 20
    # Mapping table covers every role per spec.
    assert "owners" in SYSTEM_ROLE_GROUPS
    assert SYSTEM_ROLE_GROUPS["owners"] == "role:owners"


def test_resolve_groups_ambiguity_raises() -> None:
    """A case-insensitive collision between custom groups raises ambiguity."""
    client = _groups_client(GROUPS)
    with pytest.raises(ZulipAmbiguityError) as exc:
        _ = resolve_groups(client, "engineering")
    assert exc.value.matches  # listing populated
    assert {m["id"] for m in exc.value.matches} == {10, 11}


def test_resolve_groups_nobody_rejected_when_not_allowed() -> None:
    """``Nobody`` alone fails lockout prevention when ``allow_nobody=False``."""
    client = _groups_client(GROUPS)
    with pytest.raises(ZulipLockoutError):
        _ = resolve_groups(client, "Nobody", allow_nobody=False)


def test_resolve_groups_nobody_allowed_by_default() -> None:
    """``Nobody`` is allowed by default (e.g. for ``channel update``)."""
    client = _groups_client(GROUPS)
    _, value = resolve_groups(client, "Nobody")
    assert value == 21


def test_resolve_groups_empty_spec_rejected() -> None:
    """An empty or whitespace-only spec is rejected with a clear error."""
    client = _groups_client(GROUPS)
    with pytest.raises(ZulipValidationError):
        _ = resolve_groups(client, "  ,  ")


def test_resolve_groups_tolerates_extra_commas() -> None:
    """Empty inner segments are stripped (lenient parsing, documented)."""
    client = _groups_client(GROUPS)
    resolved, value = resolve_groups(client, "design, , id:11")
    assert [g["id"] for g in resolved] == [30, 11]
    assert value == {"direct_members": [], "direct_subgroups": [30, 11]}


# ---------------------------------------------------------------------------
# T019 — User resolution
# ---------------------------------------------------------------------------


MEMBERS = [
    {
        "user_id": 100,
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "delivery_email": "alice@example.com",
        "is_bot": False,
        "is_active": True,
    },
    {
        "user_id": 101,
        "full_name": "Alice Smith",
        "email": "alice2@example.com",
        "delivery_email": "alice2@example.com",
        "is_bot": False,
        "is_active": True,
    },
    {
        "user_id": 200,
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "delivery_email": "bob@example.com",
        "is_bot": False,
        "is_active": True,
    },
]


def _members_client(members: list[dict[str, Any]]) -> Any:
    client = mock.MagicMock()
    client.get_members.return_value = {"result": "success", "members": members}
    return client


def test_resolve_users_by_email() -> None:
    """Email lookup is unique and case-sensitive (Zulip rule)."""
    client = _members_client(MEMBERS)
    users = resolve_users(client, ["bob@example.com"], mode="email")
    assert [u["user_id"] for u in users] == [200]


def test_resolve_users_by_id() -> None:
    """Numeric ID lookup parses ints from the CLI string."""
    client = _members_client(MEMBERS)
    users = resolve_users(client, ["101"], mode="id")
    assert users[0]["full_name"] == "Alice Smith"


def test_resolve_users_by_name_ambiguous_raises() -> None:
    """Full name collisions raise :class:`ZulipAmbiguityError`."""
    client = _members_client(MEMBERS)
    with pytest.raises(ZulipAmbiguityError) as exc:
        _ = resolve_users(client, ["Alice Smith"], mode="name")
    assert {m["user_id"] for m in exc.value.matches} == {100, 101}


def test_resolve_users_by_name_unique() -> None:
    """A unique full-name match resolves successfully."""
    client = _members_client(MEMBERS)
    users = resolve_users(client, ["Bob Jones"], mode="name")
    assert users[0]["user_id"] == 200


def test_resolve_users_not_found() -> None:
    """An unknown identifier produces :class:`ZulipNotFoundError`."""
    client = _members_client(MEMBERS)
    with pytest.raises(ZulipNotFoundError):
        _ = resolve_users(client, ["nobody@example.com"], mode="email")


def test_resolve_users_id_mode_requires_numeric() -> None:
    """--by-id rejects non-numeric identifiers with a clear error."""
    client = _members_client(MEMBERS)
    with pytest.raises(ZulipValidationError):
        _ = resolve_users(client, ["not-a-number"], mode="id")


# ---------------------------------------------------------------------------
# Client factory — credential validation
# ---------------------------------------------------------------------------


def test_get_client_rejects_incomplete_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """``get_client`` errors clearly when synthesized creds are incomplete."""
    monkeypatch.setattr("lftools_uv.api.endpoints.zulip._zulip_module", mock.MagicMock())
    config = ZulipConfig(email="bot@example.com", source="lftools.ini[zulip]")
    with pytest.raises(ZulipConfigError, match="missing api_key, site"):
        _ = get_client(config=config)


def test_get_client_rejects_both_inputs() -> None:
    """``zuliprc`` and ``config`` are mutually exclusive inputs."""
    config = ZulipConfig(
        email="bot@example.com",
        api_key="k",
        site="https://z",
        source="lftools.ini[zulip]",
    )
    with pytest.raises(ZulipValidationError):
        _ = get_client(zuliprc=mock.MagicMock(), config=config)


# ---------------------------------------------------------------------------
# T021 — list_channels()
# ---------------------------------------------------------------------------


LIST_ACTIVE = [
    {
        "stream_id": 1,
        "name": "general",
        "description": "General discussion",
        "invite_only": False,
        "is_web_public": False,
        "is_archived": False,
        "subscriber_count": 42,
    },
    {
        "stream_id": 2,
        "name": "secret",
        "description": "private",
        "invite_only": True,
        "is_web_public": False,
        "is_archived": False,
        "subscriber_count": 5,
    },
    {
        "stream_id": 3,
        "name": "announce",
        "description": "",
        "invite_only": False,
        "is_web_public": True,
        "is_archived": False,
        "subscriber_count": 100,
    },
]

LIST_ARCHIVED = LIST_ACTIVE + [
    {
        "stream_id": 99,
        "name": "old",
        "description": "",
        "invite_only": False,
        "is_web_public": False,
        "is_archived": True,
        "subscriber_count": 0,
    },
]


def test_list_channels_active_only_by_default() -> None:
    """Without ``include_archived``, only active streams are returned."""
    client = _streams_client(LIST_ACTIVE, LIST_ARCHIVED)
    channels = list_channels(client)
    assert [c["stream_id"] for c in channels] == [1, 2, 3]
    assert all(not c["is_archived"] for c in channels)


def test_list_channels_normalizes_type() -> None:
    """Each stream maps to one of public / private / web-public."""
    client = _streams_client(LIST_ACTIVE, LIST_ARCHIVED)
    by_id = {c["stream_id"]: c for c in list_channels(client)}
    assert by_id[1]["type"] == "public"
    assert by_id[2]["type"] == "private"
    assert by_id[3]["type"] == "web-public"


def test_list_channels_include_archived_returns_all() -> None:
    """``include_archived=True`` returns the archived superset."""
    client = _streams_client(LIST_ACTIVE, LIST_ARCHIVED)
    channels = list_channels(client, include_archived=True)
    assert {c["stream_id"] for c in channels} == {1, 2, 3, 99}


def test_list_channels_empty_list() -> None:
    """An empty server returns an empty list, not an error."""
    client = _streams_client([], [])
    assert list_channels(client) == []


def test_list_channels_propagates_api_error() -> None:
    """API failures bubble up as ``ZulipAPIError``."""
    client = mock.MagicMock()
    client.call_endpoint.return_value = {"result": "error", "msg": "boom"}
    with pytest.raises(ZulipAPIError):
        _ = list_channels(client)


def test_list_channels_keeps_description_and_count() -> None:
    """The returned dict carries description and subscriber_count."""
    client = _streams_client(LIST_ACTIVE, LIST_ARCHIVED)
    by_id = {c["stream_id"]: c for c in list_channels(client)}
    assert by_id[1]["description"] == "General discussion"
    assert by_id[1]["subscriber_count"] == 42
    assert by_id[1]["name"] == "general"


def test_list_channels_defaults_missing_subscriber_count_to_zero() -> None:
    """A stream without ``subscriber_count`` normalizes to 0, not None."""
    streams = [
        {
            "stream_id": 7,
            "name": "no-count",
            "description": "",
            "invite_only": False,
            "is_web_public": False,
            "is_archived": False,
            # no subscriber_count
        },
    ]
    client = _streams_client(streams, streams)
    out = list_channels(client)
    assert out[0]["subscriber_count"] == 0


def test_list_channels_rejects_missing_stream_id() -> None:
    """A stream lacking a numeric stream_id raises ``ZulipAPIError``."""
    bad = [{"name": "no-id", "description": "", "invite_only": False}]
    client = _streams_client(bad, bad)
    with pytest.raises(ZulipAPIError):
        _ = list_channels(client)


# ---------------------------------------------------------------------------
# T045 — list_subscribers (US7)
# ---------------------------------------------------------------------------


def _subscribers_client(
    streams_active: list[dict[str, Any]],
    streams_archived: list[dict[str, Any]],
    subscribers_by_stream: dict[int, list[int]],
    members: list[dict[str, Any]],
) -> Any:
    """Return a mock client that serves streams, subscribers, and members.

    ``streams_active`` is returned for unfiltered streams requests, and
    ``streams_archived`` for ``include_archived=True``. The
    ``streams/{id}/members`` endpoint returns ``subscribers_by_stream``.
    """
    client = mock.MagicMock()

    def side_effect(*, url: str, method: str, request: dict[str, Any] | None = None) -> Any:
        if url == "streams" and method == "GET":
            if request and request.get("include_archived"):
                return {"result": "success", "streams": streams_archived}
            return {"result": "success", "streams": streams_active}
        if url.startswith("streams/") and url.endswith("/members") and method == "GET":
            stream_id = int(url.split("/")[1])
            ids = subscribers_by_stream.get(stream_id, [])
            return {"result": "success", "subscribers": list(ids)}
        raise AssertionError(f"unexpected endpoint: {method} {url}")

    client.call_endpoint.side_effect = side_effect
    client.get_members.return_value = {"result": "success", "members": members}
    return client


SUBS_STREAMS = [
    {"stream_id": 1, "name": "general", "description": "g", "is_archived": False},
]
SUBS_STREAMS_ARCHIVED = SUBS_STREAMS + [
    {"stream_id": 99, "name": "old-channel", "description": "", "is_archived": True},
]
SUBS_MEMBERS = [
    {
        "user_id": 10,
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "delivery_email": "alice@example.com",
    },
    {
        "user_id": 20,
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "delivery_email": "bob-priv@example.com",
    },
]


def test_list_subscribers_returns_enriched_dicts() -> None:
    """Happy path: subscriber IDs are enriched with full_name and email."""
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = _subscribers_client(
        streams_active=SUBS_STREAMS,
        streams_archived=SUBS_STREAMS_ARCHIVED,
        subscribers_by_stream={1: [10, 20]},
        members=SUBS_MEMBERS,
    )
    subs = list_subscribers(client, name="general")
    assert subs == [
        {"user_id": 10, "full_name": "Alice Smith", "email": "alice@example.com"},
        {"user_id": 20, "full_name": "Bob Jones", "email": "bob-priv@example.com"},
    ]


def test_list_subscribers_by_channel_id() -> None:
    """Resolution by channel_id works the same way."""
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = _subscribers_client(
        streams_active=SUBS_STREAMS,
        streams_archived=SUBS_STREAMS_ARCHIVED,
        subscribers_by_stream={1: [10]},
        members=SUBS_MEMBERS,
    )
    subs = list_subscribers(client, channel_id=1)
    assert [s["user_id"] for s in subs] == [10]


def test_list_subscribers_channel_not_found() -> None:
    """A missing channel surfaces :class:`ZulipNotFoundError`."""
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = _subscribers_client(
        streams_active=SUBS_STREAMS,
        streams_archived=SUBS_STREAMS_ARCHIVED,
        subscribers_by_stream={},
        members=SUBS_MEMBERS,
    )
    with pytest.raises(ZulipNotFoundError):
        _ = list_subscribers(client, name="does-not-exist")


def test_list_subscribers_include_archived() -> None:
    """``include_archived=True`` propagates to channel resolution."""
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = _subscribers_client(
        streams_active=SUBS_STREAMS,
        streams_archived=SUBS_STREAMS_ARCHIVED,
        subscribers_by_stream={99: [10]},
        members=SUBS_MEMBERS,
    )
    subs = list_subscribers(client, name="old-channel", include_archived=True)
    assert [s["user_id"] for s in subs] == [10]


def test_list_subscribers_handles_missing_user_metadata() -> None:
    """Subscriber IDs absent from the members listing still surface.

    The Zulip server may include deactivated or otherwise hidden users
    in a stream's subscriber list. The helper should not raise; missing
    metadata is reported as ``None`` so callers can decide how to
    render it.
    """
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = _subscribers_client(
        streams_active=SUBS_STREAMS,
        streams_archived=SUBS_STREAMS_ARCHIVED,
        subscribers_by_stream={1: [10, 999]},
        members=SUBS_MEMBERS,
    )
    subs = list_subscribers(client, name="general")
    assert subs[0]["user_id"] == 10
    assert subs[1] == {"user_id": 999, "full_name": None, "email": None}


def test_list_subscribers_requires_one_target() -> None:
    """Exactly one of name/channel_id must be supplied."""
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = _subscribers_client(
        streams_active=SUBS_STREAMS,
        streams_archived=SUBS_STREAMS_ARCHIVED,
        subscribers_by_stream={1: [10]},
        members=SUBS_MEMBERS,
    )
    with pytest.raises(ZulipValidationError):
        _ = list_subscribers(client)
    with pytest.raises(ZulipValidationError):
        _ = list_subscribers(client, name="general", channel_id=1)

def test_list_subscribers_rejects_non_numeric_id() -> None:
    """Non-integer subscriber ids must raise ZulipAPIError, not be skipped."""
    from lftools_uv.api.endpoints.zulip import list_subscribers

    client = mock.MagicMock()

    def side_effect(*, url: str, method: str, request: dict[str, Any] | None = None) -> Any:
        if url == "streams" and method == "GET":
            return {"result": "success", "streams": SUBS_STREAMS}
        if url == "streams/1/members" and method == "GET":
            return {"result": "success", "subscribers": [10, "not-a-number", 20]}
        raise AssertionError(f"unexpected endpoint: {method} {url}")

    client.call_endpoint.side_effect = side_effect
    client.get_members.return_value = {"result": "success", "members": SUBS_MEMBERS}

    with pytest.raises(ZulipAPIError, match="Malformed subscriber id"):
        _ = list_subscribers(client, name="general")

# ---------------------------------------------------------------------------
# T025 — list_users API
# ---------------------------------------------------------------------------


LIST_USERS_MEMBERS = [
    {
        "user_id": 10,
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "is_bot": False,
        "is_active": True,
    },
    {
        "user_id": 11,
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "is_bot": False,
        "is_active": False,
    },
    {
        "user_id": 12,
        "full_name": "Welcome Bot",
        "email": "welcome-bot@example.com",
        "is_bot": True,
        "is_active": True,
    },
    {
        "user_id": 13,
        "full_name": "Old Bot",
        "email": "old-bot@example.com",
        "is_bot": True,
        "is_active": False,
    },
]


def test_list_users_default_filters_bots_and_deactivated() -> None:
    """Defaults exclude bots and deactivated users, matching the CLI defaults."""
    client = _members_client(LIST_USERS_MEMBERS)
    users = list_users(client)
    assert [u["user_id"] for u in users] == [10]
    user = users[0]
    assert set(user.keys()) == {"user_id", "full_name", "email", "is_bot", "is_active"}
    assert user["full_name"] == "Alice Smith"
    assert user["email"] == "alice@example.com"
    assert user["is_bot"] is False
    assert user["is_active"] is True


def test_list_users_include_bots() -> None:
    """``include_bots=True`` retains bot accounts (still active-only)."""
    client = _members_client(LIST_USERS_MEMBERS)
    users = list_users(client, include_bots=True)
    assert sorted(u["user_id"] for u in users) == [10, 12]


def test_list_users_include_deactivated() -> None:
    """``include_deactivated=True`` retains deactivated humans (no bots by default)."""
    client = _members_client(LIST_USERS_MEMBERS)
    users = list_users(client, include_deactivated=True)
    assert sorted(u["user_id"] for u in users) == [10, 11]


def test_list_users_include_both() -> None:
    """Both flags together return the full member list (normalized)."""
    client = _members_client(LIST_USERS_MEMBERS)
    users = list_users(client, include_bots=True, include_deactivated=True)
    assert sorted(u["user_id"] for u in users) == [10, 11, 12, 13]


def test_list_users_empty_list() -> None:
    """An empty members response yields an empty list."""
    client = _members_client([])
    assert list_users(client) == []


def test_list_users_coerces_str_fields() -> None:
    """``None`` ``full_name``/``email`` values collapse to ``""``."""
    members = [
        {
            "user_id": 1,
            "full_name": None,
            "email": None,
            "is_bot": False,
            "is_active": True,
        },
    ]
    client = _members_client(members)
    users = list_users(client)
    assert users[0]["full_name"] == ""
    assert users[0]["email"] == ""


def test_list_users_preserves_str_zero_like_values() -> None:
    """Falsy-but-stringifiable values (e.g. ``"0"``) survive normalization."""
    members = [
        {
            "user_id": 7,
            "full_name": "0",
            "email": "0",
            "is_bot": False,
            "is_active": True,
        },
    ]
    client = _members_client(members)
    users = list_users(client)
    assert users[0]["full_name"] == "0"
    assert users[0]["email"] == "0"


def test_list_users_rejects_missing_user_id() -> None:
    """Members without a numeric ``user_id`` are a malformed payload."""
    members = [{"full_name": "Mystery", "email": "m@x.example", "is_bot": False, "is_active": True}]
    client = _members_client(members)
    with pytest.raises(ZulipAPIError, match="user_id"):
        _ = list_users(client)


def test_list_users_propagates_api_errors() -> None:
    """Server errors during ``_fetch_users`` surface as :class:`ZulipAPIError`."""
    client = mock.MagicMock()
    client.get_members.return_value = {"result": "error", "msg": "boom"}
    with pytest.raises(ZulipAPIError):
        _ = list_users(client)


# ---------------------------------------------------------------------------
# T029 — list_groups (US3)
# ---------------------------------------------------------------------------


LIST_GROUPS = [
    {
        "id": 10,
        "name": "engineering",
        "description": "Engineering team",
        "members": [1, 2, 3],
        "is_system_group": False,
    },
    {
        "id": 11,
        "name": "design",
        "description": "Designers",
        "members": [4, 5],
        "is_system_group": False,
    },
    {
        "id": 12,
        "name": "Design",
        "description": "Duplicate design (case collision)",
        "members": [6],
        "is_system_group": False,
    },
    {
        "id": 20,
        "name": "role:owners",
        "description": "Owners of this organization",
        "members": [1],
        "is_system_group": True,
    },
    {
        "id": 21,
        "name": "role:administrators",
        "description": "Administrators of this organization",
        "members": [1, 2],
        "is_system_group": True,
    },
    {
        "id": 22,
        "name": "role:fullmembers",
        "description": "Full members",
        "members": [1, 2, 3, 4],
        "is_system_group": True,
    },
    {
        "id": 23,
        "name": "role:nobody",
        "description": "Nobody",
        "members": [],
        "is_system_group": True,
    },
]


def _list_groups_client(groups: list[dict[str, Any]]) -> Any:
    """Return a mock client whose ``user_groups`` endpoint returns ``groups``."""
    client = mock.MagicMock()
    client.call_endpoint.return_value = {
        "result": "success",
        "user_groups": groups,
    }
    return client


def test_list_groups_returns_custom_and_system() -> None:
    """All custom and system role groups are returned with normalized fields."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client)
    # Verify the helper hit the user_groups endpoint.
    client.call_endpoint.assert_called_once()
    args, kwargs = client.call_endpoint.call_args
    call = {**kwargs, **dict(zip(["url", "method"], args, strict=False))}
    assert call.get("url") == "user_groups"
    assert call.get("method") == "GET"
    # Custom and system groups both present.
    types = {g["type"] for g in groups}
    assert types == {"custom", "system"}
    # Every group has the standard shape.
    for group in groups:
        assert set(group.keys()) >= {
            "group_id",
            "name",
            "description",
            "member_count",
            "type",
        }
        assert isinstance(group["group_id"], int)
        assert isinstance(group["member_count"], int)


def test_list_groups_system_groups_use_display_names() -> None:
    """System role groups appear with their display names, not ``role:`` API names."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client)
    system_names = {g["name"] for g in groups if g["type"] == "system"}
    # No internal ``role:`` strings leak to the caller.
    assert not any(n.startswith("role:") for n in system_names)
    # Expected display names from the spec mapping appear.
    assert {"Owners", "Administrators", "Full Members", "Nobody"} <= system_names


def test_list_groups_member_counts() -> None:
    """``member_count`` is derived from the ``members`` array length."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client)
    by_id = {g["group_id"]: g for g in groups}
    assert by_id[10]["member_count"] == 3
    assert by_id[20]["member_count"] == 1
    assert by_id[23]["member_count"] == 0


def test_list_groups_preserves_falsy_descriptions() -> None:
    """Falsy non-None descriptions are coerced with ``str(...)``."""
    client = _list_groups_client(
        [{"id": 1, "name": "zero", "description": 0, "members": []}],
    )
    assert list_groups(client)[0]["description"] == "0"


def test_list_groups_filter_by_group_id() -> None:
    """``group_id`` filter narrows the result to exactly one group."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client, group_id=21)
    assert len(groups) == 1
    assert groups[0]["group_id"] == 21
    assert groups[0]["name"] == "Administrators"
    assert groups[0]["type"] == "system"


def test_list_groups_filter_by_group_id_not_found() -> None:
    """An unknown ``group_id`` returns an empty list (no error)."""
    client = _list_groups_client(LIST_GROUPS)
    assert list_groups(client, group_id=9999) == []


def test_list_groups_filter_by_group_name_custom() -> None:
    """``group_name`` filter matches custom groups case-insensitively."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client, group_name="ENGINEERING")
    assert len(groups) == 1
    assert groups[0]["group_id"] == 10
    assert groups[0]["type"] == "custom"


def test_list_groups_filter_by_group_name_system() -> None:
    """``group_name`` filter matches system role display names."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client, group_name="administrators")
    assert len(groups) == 1
    assert groups[0]["group_id"] == 21
    assert groups[0]["name"] == "Administrators"


def test_list_groups_filter_by_group_name_not_found() -> None:
    """An unmatched ``group_name`` returns an empty list (no error)."""
    client = _list_groups_client(LIST_GROUPS)
    assert list_groups(client, group_name="nonesuch") == []


def test_list_groups_ambiguous_group_name_raises() -> None:
    """A case-insensitive collision under ``group_name`` raises ambiguity."""
    client = _list_groups_client(LIST_GROUPS)
    with pytest.raises(ZulipAmbiguityError) as exc:
        _ = list_groups(client, group_name="design")
    assert {m["group_id"] for m in exc.value.matches} == {11, 12}


def test_list_groups_mutually_exclusive_filters() -> None:
    """``group_name`` and ``group_id`` cannot be combined."""
    client = _list_groups_client(LIST_GROUPS)
    with pytest.raises(ZulipValidationError):
        _ = list_groups(client, group_name="design", group_id=11)


def test_list_groups_api_error_on_unexpected_response() -> None:
    """A malformed Zulip response surfaces as :class:`ZulipAPIError`."""
    client = mock.MagicMock()
    client.call_endpoint.return_value = {"result": "error", "msg": "boom"}
    with pytest.raises(ZulipAPIError):
        _ = list_groups(client)


def test_list_groups_uses_known_system_role_mapping() -> None:
    """The SYSTEM_ROLE_GROUPS table is the canonical mapping source."""
    client = _list_groups_client(LIST_GROUPS)
    groups = list_groups(client)
    for group in groups:
        if group["type"] == "system":
            # Display name (lowercased) must round-trip via SYSTEM_ROLE_GROUPS.
            display = group["name"].casefold()
            assert display in SYSTEM_ROLE_GROUPS


def test_list_groups_rejects_malformed_entry() -> None:
    """A non-dict entry in the user_groups payload raises ZulipAPIError."""
    client = mock.MagicMock()
    client.call_endpoint.return_value = {
        "result": "success",
        "user_groups": [{"id": 1, "name": "ok"}, "not-a-dict"],
    }
    with pytest.raises(ZulipAPIError):
        _ = list_groups(client)


def test_list_groups_rejects_missing_id() -> None:
    """A group object lacking a numeric ``id`` raises ZulipAPIError."""
    client = mock.MagicMock()
    client.call_endpoint.return_value = {
        "result": "success",
        "user_groups": [{"name": "no-id"}],
    }
    with pytest.raises(ZulipAPIError, match="numeric 'id'"):
        _ = list_groups(client)


def test_system_role_display_names_round_trip() -> None:
    """SYSTEM_ROLE_DISPLAY_NAMES is consistent with SYSTEM_ROLE_GROUPS."""
    from lftools_uv.api.endpoints.zulip import SYSTEM_ROLE_DISPLAY_NAMES

    assert set(SYSTEM_ROLE_DISPLAY_NAMES.keys()) == set(SYSTEM_ROLE_GROUPS.values())
    # Every display name folds back to a key in SYSTEM_ROLE_GROUPS.
    for display in SYSTEM_ROLE_DISPLAY_NAMES.values():
        assert display.casefold() in SYSTEM_ROLE_GROUPS


# ---------------------------------------------------------------------------
# T033 — create_channel API (US4)
# ---------------------------------------------------------------------------


CREATE_GROUPS = [
    {"id": 10, "name": "engineering", "is_system_group": False},
    {"id": 20, "name": "role:administrators", "is_system_group": True},
    {"id": 21, "name": "role:nobody", "is_system_group": True},
    {"id": 22, "name": "role:members", "is_system_group": True},
]

CREATE_ACTIVE_STREAMS = [
    {"stream_id": 100, "name": "new-channel", "description": "", "is_archived": False},
]


def _create_channel_client(
    *,
    feature_level: int = 400,
    subscribe_response: dict[str, Any] | None = None,
    streams_response: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
    patch_response: dict[str, Any] | None = None,
) -> Any:
    """Return a mock client for create_channel tests."""
    client = mock.MagicMock()
    client.get_server_settings.return_value = {
        "result": "success",
        "zulip_feature_level": feature_level,
    }

    def call_endpoint_side_effect(*, url: str, method: str, request: Any = None) -> Any:
        if url == "users/me/subscriptions" and method == "POST":
            return subscribe_response or {"result": "success", "subscribed": {}}
        if url == "streams" and method == "GET":
            streams = CREATE_ACTIVE_STREAMS if streams_response is None else streams_response
            return {"result": "success", "streams": streams}
        if url == "user_groups" and method == "GET":
            return {"result": "success", "user_groups": groups or CREATE_GROUPS}
        if url.startswith("streams/") and method == "PATCH":
            return patch_response or {"result": "success"}
        return {"result": "error", "msg": f"unexpected endpoint: {url}"}

    client.call_endpoint.side_effect = call_endpoint_side_effect
    return client


def test_create_channel_public_success() -> None:
    """Public channel creation succeeds with minimal parameters."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    result = create_channel(client, name="new-channel")
    assert result["status"] == "success"
    assert result["channel_name"] == "new-channel"
    assert result["operation"] == "create"
    assert result["type"] == "public"
    assert result["channel_id"] == 100


def test_create_channel_private_with_subscribers() -> None:
    """Private channel with subscribers succeeds (lockout prevention met)."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    result = create_channel(
        client,
        name="new-channel",
        channel_type="private",
        subscribe_user_ids=[1, 2],
    )
    assert result["status"] == "success"
    assert result["type"] == "private"


def test_create_channel_private_without_subscribers_raises_lockout() -> None:
    """Private channel without subscribers or allow-group raises lockout error."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    with pytest.raises(ZulipLockoutError, match="lockout"):
        create_channel(client, name="private-no-subs", channel_type="private")


def test_create_channel_private_no_subscribers_no_group_raises_lockout() -> None:
    """Private channel without subscribers or allow-group raises lockout error."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    with pytest.raises(ZulipLockoutError, match="lockout"):
        create_channel(
            client,
            name="private-locked",
            channel_type="private",
            # No subscribers, no allow_group_value
        )


def test_create_channel_private_with_allow_group_succeeds() -> None:
    """Private channel with allow-group succeeds."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    result = create_channel(
        client,
        name="new-channel",
        channel_type="private",
        allow_group_value=10,  # engineering group
    )
    assert result["status"] == "success"
    assert result["type"] == "private"


def test_create_channel_web_public_checks_feature_level() -> None:
    """Web-public channels require sufficient feature level."""
    from lftools_uv.api.endpoints.zulip import create_channel

    # Feature level below web-public threshold (12)
    client = _create_channel_client(feature_level=10)
    with pytest.raises(ZulipFeatureLevelError) as exc:
        create_channel(client, name="public-channel", channel_type="web-public")
    assert exc.value.required == FEATURE_LEVELS["web-public"]
    assert exc.value.actual == 10


def test_create_channel_topic_policy_checks_feature_level() -> None:
    """topic-policy requires sufficient feature level."""
    from lftools_uv.api.endpoints.zulip import create_channel

    # Feature level below topic-policy threshold (334)
    client = _create_channel_client(feature_level=300)
    with pytest.raises(ZulipFeatureLevelError) as exc:
        create_channel(client, name="with-policy", topic_policy="deny")
    assert exc.value.required == FEATURE_LEVELS["topic-policy"]


def test_create_channel_can_remove_subscribers_group_checks_feature_level() -> None:
    """can-remove-subscribers-group requires sufficient feature level."""
    from lftools_uv.api.endpoints.zulip import create_channel

    # Feature level below threshold (161)
    client = _create_channel_client(feature_level=100)
    with pytest.raises(ZulipFeatureLevelError) as exc:
        create_channel(
            client,
            name="with-removal-perm",
            can_remove_subscribers_group_value=10,
        )
    assert exc.value.required == FEATURE_LEVELS["can-remove-subscribers-group"]


def test_create_channel_can_access_group_checks_feature_level() -> None:
    """can-access-group requires sufficient feature level."""
    from lftools_uv.api.endpoints.zulip import create_channel

    # Feature level below threshold (197)
    client = _create_channel_client(feature_level=100)
    with pytest.raises(ZulipFeatureLevelError) as exc:
        create_channel(
            client,
            name="with-access-group",
            allow_group_value=10,
        )
    assert exc.value.required == FEATURE_LEVELS["can-access-group"]


def test_create_channel_invalid_topic_policy_rejected() -> None:
    """Invalid topic-policy value raises validation error."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    with pytest.raises(ZulipValidationError, match="Invalid topic-policy"):
        create_channel(client, name="bad-policy", topic_policy="invalid")


def test_create_channel_with_description() -> None:
    """Channel description is included in the request."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    result = create_channel(client, name="new-channel", description="Test description")
    assert result["status"] == "success"
    # Verify the subscription request included the description
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    assert len(calls) == 1
    request = calls[0].kwargs.get("request", {})
    assert request["subscriptions"][0]["description"] == "Test description"


def test_create_channel_with_announce_true() -> None:
    """announce=True is passed to the API."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    create_channel(client, name="new-channel", announce=True)
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    request = calls[0].kwargs.get("request", {})
    assert request.get("announce") is True


def test_create_channel_with_announce_false() -> None:
    """announce=False is passed to the API."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    create_channel(client, name="new-channel", announce=False)
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    request = calls[0].kwargs.get("request", {})
    assert request.get("announce") is False


def test_create_channel_passes_group_setting_value_simple() -> None:
    """Single group produces simple integer value in request."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    create_channel(
        client,
        name="new-channel",
        allow_group_value=42,
    )
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    request = calls[0].kwargs.get("request", {})
    assert request.get("can_access_group") == 42


def test_create_channel_passes_group_setting_value_complex() -> None:
    """Multiple groups produce complex object in request."""
    from lftools_uv.api.endpoints.zulip import create_channel

    complex_value = {"direct_members": [], "direct_subgroups": [10, 20]}
    client = _create_channel_client()
    create_channel(
        client,
        name="new-channel",
        allow_group_value=complex_value,
    )
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    request = calls[0].kwargs.get("request", {})
    assert request.get("can_access_group") == complex_value


def test_create_channel_passes_can_remove_subscribers_group() -> None:
    """can_remove_subscribers_group is passed to the API."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    create_channel(
        client,
        name="new-channel",
        can_remove_subscribers_group_value=22,
    )
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    request = calls[0].kwargs.get("request", {})
    assert request.get("can_remove_subscribers_group") == 22


def test_create_channel_api_error_handled() -> None:
    """API errors are raised as ZulipAPIError."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client(subscribe_response={"result": "error", "msg": "name already taken"})
    with pytest.raises(ZulipAPIError, match="name already taken"):
        create_channel(client, name="duplicate")


def test_create_channel_valid_topic_policies() -> None:
    """All valid topic-policy values are accepted."""
    from lftools_uv.api.endpoints.zulip import VALID_TOPIC_POLICIES, create_channel

    for policy in VALID_TOPIC_POLICIES:
        client = _create_channel_client()
        result = create_channel(client, name="new-channel", topic_policy=policy)
        assert result["status"] == "success"


def test_create_channel_topic_policy_patch_failure_returns_partial() -> None:
    """When topic_policy PATCH fails, result status is 'partial' with warnings."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client(patch_response={"result": "error", "msg": "permission denied"})
    result = create_channel(client, name="new-channel", topic_policy="deny")
    assert result["status"] == "partial"
    assert result["topic_policy_applied"] is False
    assert "warnings" in result
    assert any("permission denied" in w for w in result["warnings"])


def test_create_channel_topic_policy_applied_true_on_success() -> None:
    """When topic_policy PATCH succeeds, topic_policy_applied is True."""
    from lftools_uv.api.endpoints.zulip import create_channel

    client = _create_channel_client()
    result = create_channel(client, name="new-channel", topic_policy="allow")
    assert result["status"] == "success"
    assert result["topic_policy_applied"] is True
    assert "warnings" not in result


def test_create_channel_stream_not_found_with_topic_policy_partial() -> None:
    """When channel can't be found and topic_policy requested, return partial."""
    from lftools_uv.api.endpoints.zulip import create_channel

    # Empty streams list means resolve_channel will fail
    client = _create_channel_client(streams_response=[])
    result = create_channel(client, name="new-channel", topic_policy="deny")
    assert result["status"] == "partial"
    assert result["channel_id"] is None
    assert "warnings" in result
    assert any("could not locate" in w for w in result["warnings"])


# ---------------------------------------------------------------------------
# T037 — Subscribe users (US5)
# ---------------------------------------------------------------------------


_SUBSCRIBE_STREAMS = [
    {
        "stream_id": 42,
        "name": "general",
        "description": "",
        "invite_only": False,
        "is_archived": False,
    },
    {
        "stream_id": 99,
        "name": "123",
        "description": "Numeric-name channel",
        "invite_only": False,
        "is_archived": False,
    },
]


def _subscribe_client(
    streams: list[dict[str, Any]],
    members: list[dict[str, Any]],
    subscribe_response: dict[str, Any],
) -> Any:
    """Mock client wiring streams, members, and the subscribe endpoint."""
    client = mock.MagicMock()
    client.get_members.return_value = {"result": "success", "members": members}

    def _call_endpoint(*, url: str, method: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        if url == "streams" and method == "GET":
            return {"result": "success", "streams": streams}
        if url == "users/me/subscriptions" and method == "POST":
            client._last_subscribe_request = request
            return subscribe_response
        raise AssertionError(f"Unexpected endpoint call: {method} {url}")

    client.call_endpoint.side_effect = _call_endpoint
    return client


def test_subscribe_users_single_email_success() -> None:
    """Subscribing a single user by email returns a success bulk result."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {"general": ["bob@example.com"]},
            "already_subscribed": {},
            "unauthorized": [],
        },
    )
    result = subscribe_users(
        client,
        "general",
        ["bob@example.com"],
        id_mode="email",
    )
    assert result["status"] == "success"
    assert result["channel_id"] == 42
    assert result["channel_name"] == "general"
    assert result["operation"] == "subscribe"
    assert result["results"] == [{"user": "bob@example.com", "status": "subscribed"}]
    assert result["errors"] == []
    # Verify the request payload encodes the resolved channel name and
    # the resolved user email exactly per the API contract.
    req = client._last_subscribe_request
    import json as _json

    subs = _json.loads(req["subscriptions"])
    principals = _json.loads(req["principals"])
    assert subs == [{"name": "general"}]
    assert principals == ["bob@example.com"]


def test_subscribe_users_bulk_mixed_outcomes() -> None:
    """Bulk subscribe with mixed subscribed/already_subscribed returns success."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {"general": ["alice@example.com"]},
            "already_subscribed": {"general": ["bob@example.com"]},
            "unauthorized": [],
        },
    )
    result = subscribe_users(
        client,
        "general",
        ["alice@example.com", "bob@example.com"],
        id_mode="email",
    )
    assert result["status"] == "success"
    statuses = {r["user"]: r["status"] for r in result["results"]}
    assert statuses["alice@example.com"] == "subscribed"
    assert statuses["bob@example.com"] == "already_subscribed"
    assert result["errors"] == []


def test_subscribe_users_already_subscribed_only() -> None:
    """All already-subscribed users still produce status=success (no-op)."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {},
            "already_subscribed": {"general": ["bob@example.com"]},
            "unauthorized": [],
        },
    )
    result = subscribe_users(
        client,
        "general",
        ["bob@example.com"],
        id_mode="email",
    )
    assert result["status"] == "success"
    assert result["results"][0]["status"] == "already_subscribed"
    assert result["errors"] == []


def test_subscribe_users_partial_unauthorized() -> None:
    """Unauthorized users are reported in errors with overall status=partial."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {"general": ["alice@example.com"]},
            "already_subscribed": {},
            "unauthorized": ["bob@example.com"],
        },
    )
    result = subscribe_users(
        client,
        "general",
        ["alice@example.com", "bob@example.com"],
        id_mode="email",
    )
    assert result["status"] == "partial"
    by_user = {r["user"]: r for r in result["results"]}
    assert by_user["alice@example.com"]["status"] == "subscribed"
    error_users = {e["user"] for e in result["errors"]}
    assert "bob@example.com" in error_users


def test_subscribe_users_by_id_resolves_to_email_principals() -> None:
    """``id_mode='id'`` resolves numeric IDs to user emails before send.

    Zulip's stable identifier is the delivery_email, so even when the
    caller supplies numeric user IDs, ``subscribe_users`` looks up the
    resolved user object and sends its email as the principal. This
    test asserts the actual JSON-encoded ``principals`` payload to
    pin the contract down.
    """
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {"general": ["bob@example.com"]},
            "already_subscribed": {},
            "unauthorized": [],
        },
    )
    result = subscribe_users(client, "general", ["200"], id_mode="id")
    assert result["status"] == "success"

    import json as _json

    principals = _json.loads(client._last_subscribe_request["principals"])
    # User id 200 in MEMBERS maps to bob@example.com.
    assert principals == ["bob@example.com"]


def test_subscribe_users_invalid_user_raises() -> None:
    """An unknown user identifier raises before the subscribe call."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {"result": "success", "subscribed": {}, "already_subscribed": {}, "unauthorized": []},
    )
    with pytest.raises(ZulipNotFoundError):
        _ = subscribe_users(client, "general", ["ghost@example.com"], id_mode="email")


def test_subscribe_users_caps_at_50() -> None:
    """Per-spec cap of 50 users per invocation is enforced client-side."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {"result": "success", "subscribed": {}, "already_subscribed": {}, "unauthorized": []},
    )
    too_many = [f"user{i}@example.com" for i in range(51)]
    with pytest.raises(ZulipValidationError, match="50"):
        _ = subscribe_users(client, "general", too_many, id_mode="email")


def test_subscribe_users_empty_users_rejected() -> None:
    """At least one user identifier must be provided."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {"result": "success", "subscribed": {}, "already_subscribed": {}, "unauthorized": []},
    )
    with pytest.raises(ZulipValidationError):
        _ = subscribe_users(client, "general", [], id_mode="email")


def test_subscribe_users_by_channel_id() -> None:
    """Passing an int channel argument resolves via stream_id."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {"general": ["bob@example.com"]},
            "already_subscribed": {},
            "unauthorized": [],
        },
    )
    result = subscribe_users(client, 42, ["bob@example.com"], id_mode="email")
    assert result["channel_id"] == 42
    assert result["channel_name"] == "general"


def test_subscribe_users_channel_name_numeric_string() -> None:
    """A string channel argument that looks numeric still resolves by name."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {
            "result": "success",
            "subscribed": {"123": ["bob@example.com"]},
            "already_subscribed": {},
            "unauthorized": [],
        },
    )
    result = subscribe_users(client, "123", ["bob@example.com"], id_mode="email")
    assert result["channel_id"] == 99
    assert result["channel_name"] == "123"


def test_subscribe_users_api_error_response() -> None:
    """A non-success response from the subscribe endpoint raises ZulipAPIError."""
    client = _subscribe_client(
        _SUBSCRIBE_STREAMS,
        MEMBERS,
        {"result": "error", "msg": "Invalid request"},
    )
    with pytest.raises(ZulipAPIError):
        _ = subscribe_users(client, "general", ["bob@example.com"], id_mode="email")


def test_subscribe_users_skips_resolve_channel_when_stream_supplied() -> None:
    """`_resolved_stream=...` bypasses the internal resolve_channel call.

    The CLI layer pre-resolves the channel so that ``--json`` error
    payloads can include accurate channel context. Passing the already-
    resolved stream into ``subscribe_users()`` MUST skip the duplicate
    ``GET /streams`` round-trip that would otherwise occur.
    """
    from unittest import mock

    from lftools_uv.api.endpoints.zulip import subscribe_users

    client = mock.MagicMock()
    client.get_members.return_value = {
        "result": "success",
        "members": [
            {"user_id": 7, "email": "bob@example.com", "delivery_email": "bob@example.com", "full_name": "Bob"}
        ],
    }
    client.call_endpoint.return_value = {
        "result": "success",
        "subscribed": {"general": ["bob@example.com"]},
        "already_subscribed": {},
        "unauthorized": [],
    }

    with mock.patch("lftools_uv.api.endpoints.zulip.resolve_channel") as resolve_chan:
        result = subscribe_users(
            client,
            "general",
            ["bob@example.com"],
            id_mode="email",
            _resolved_stream={"stream_id": 42, "name": "general"},
        )

    # resolve_channel MUST NOT be called when _resolved_stream is supplied.
    resolve_chan.assert_not_called()
    assert result["status"] == "success"
    assert result["channel_id"] == 42
    assert result["channel_name"] == "general"


def test_subscribe_users_rejects_malformed_subscribed_field() -> None:
    """A non-dict ``subscribed`` field is treated as a server contract error.

    Defensive: protects against silent partial-failure attribution when
    a server-side regression or proxy reshapes the response.
    """
    from unittest import mock

    from lftools_uv.api.endpoints.zulip import (
        ZulipAPIError,
        subscribe_users,
    )

    client = mock.MagicMock()
    client.get_members.return_value = {
        "result": "success",
        "members": [
            {"user_id": 7, "email": "bob@example.com", "delivery_email": "bob@example.com", "full_name": "Bob"}
        ],
    }
    client.call_endpoint.return_value = {
        "result": "success",
        "subscribed": ["bob@example.com"],  # WRONG: should be a dict
        "already_subscribed": {},
        "unauthorized": [],
    }

    import pytest

    with pytest.raises(ZulipAPIError, match="'subscribed' must be a dict"):
        subscribe_users(
            client,
            "general",
            ["bob@example.com"],
            id_mode="email",
            _resolved_stream={"stream_id": 42, "name": "general"},
        )


def test_subscribe_users_rejects_malformed_unauthorized_field() -> None:
    """A non-list ``unauthorized`` field is rejected as a contract error."""
    from unittest import mock

    from lftools_uv.api.endpoints.zulip import (
        ZulipAPIError,
        subscribe_users,
    )

    client = mock.MagicMock()
    client.get_members.return_value = {
        "result": "success",
        "members": [
            {"user_id": 7, "email": "bob@example.com", "delivery_email": "bob@example.com", "full_name": "Bob"}
        ],
    }
    client.call_endpoint.return_value = {
        "result": "success",
        "subscribed": {"general": ["bob@example.com"]},
        "already_subscribed": {},
        "unauthorized": {"bob@example.com": "denied"},  # WRONG: should be a list
    }

    import pytest

    with pytest.raises(ZulipAPIError, match="'unauthorized' must be a list"):
        subscribe_users(
            client,
            "general",
            ["bob@example.com"],
            id_mode="email",
            _resolved_stream={"stream_id": 42, "name": "general"},
        )


# T041 — Unsubscribe users (US6)
# ---------------------------------------------------------------------------


def _unsubscribe_client(
    streams: list[dict[str, Any]],
    members: list[dict[str, Any]],
    *,
    removed: list[Any] | None = None,
    not_removed: list[Any] | None = None,
    result: str = "success",
    msg: str = "",
) -> Any:
    """Build a mock client supporting streams + members + unsubscribe.

    The first ``streams`` call returns the active streams. The
    ``DELETE users/me/subscriptions`` call returns the configured
    ``removed`` / ``not_removed`` payload.
    """
    client = mock.MagicMock()

    def call_endpoint(*, url: str, method: str, request: dict[str, Any] | None = None) -> Any:
        if url == "streams" and method == "GET":
            return {"result": "success", "streams": streams}
        if url == "users/me/subscriptions" and method == "DELETE":
            request = request or {}
            subscriptions = _json.loads(request.get("subscriptions", "[]"))
            principals = _json.loads(request.get("principals", "[]"))
            subscription = (subscriptions or [""])[0]
            principal = (principals or [None])[0]
            removed_streams = [subscription] if principal in (removed or []) else []
            not_removed_streams = [subscription] if principal in (not_removed or []) else []
            return {
                "result": result,
                "msg": msg,
                "removed": removed_streams,
                "not_removed": not_removed_streams,
            }
        raise AssertionError(f"Unexpected endpoint call: {method} {url}")

    client.call_endpoint.side_effect = call_endpoint
    client.get_members.return_value = {"result": "success", "members": members}
    return client


def test_unsubscribe_users_single_success() -> None:
    """A single user successfully unsubscribed returns success bulk result."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=["bob@example.com"],
        not_removed=[],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["bob@example.com"],
        id_mode="email",
    )
    assert payload["status"] == "success"
    assert payload["operation"] == "unsubscribe"
    assert payload["channel_id"] == 1
    assert payload["channel_name"] == "general"
    assert payload["results"] == [{"user": "bob@example.com", "status": "unsubscribed"}]
    assert payload["errors"] == []


def test_unsubscribe_users_bulk_success() -> None:
    """Bulk unsubscribe returns one result entry per requested user."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=["alice@example.com", "bob@example.com"],
        not_removed=[],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["alice@example.com", "bob@example.com"],
        id_mode="email",
    )
    assert payload["status"] == "success"
    assert {r["user"] for r in payload["results"]} == {
        "alice@example.com",
        "bob@example.com",
    }
    assert all(r["status"] == "unsubscribed" for r in payload["results"])


def test_unsubscribe_users_not_subscribed_noop() -> None:
    """Users not subscribed appear as ``not_subscribed`` no-ops, still success."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=[],
        not_removed=["bob@example.com"],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["bob@example.com"],
        id_mode="email",
    )
    assert payload["status"] == "success"
    assert payload["results"] == [{"user": "bob@example.com", "status": "not_subscribed"}]
    assert payload["errors"] == []


def test_unsubscribe_users_mixed_removed_and_not_removed_is_success() -> None:
    """A mix of removed + not_removed (no errors) is overall success."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=["alice@example.com"],
        not_removed=["bob@example.com"],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["alice@example.com", "bob@example.com"],
        id_mode="email",
    )
    # Both finished cleanly with no errors -> overall success.
    assert payload["status"] == "success"
    statuses = {r["user"]: r["status"] for r in payload["results"]}
    assert statuses == {
        "alice@example.com": "unsubscribed",
        "bob@example.com": "not_subscribed",
    }
    assert payload["errors"] == []


def test_unsubscribe_users_partial() -> None:
    """A mix of resolvable users + an unknown identifier yields partial.

    The unknown identifier is captured into ``errors`` instead of
    aborting the whole call, while the resolvable user is still sent
    to the server. Overall status is ``partial`` because we have both
    a successful result and an error.
    """
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=["bob@example.com"],
        not_removed=[],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["bob@example.com", "ghost@example.com"],
        id_mode="email",
    )
    assert payload["status"] == "partial"
    assert payload["results"] == [
        {"user": "bob@example.com", "status": "unsubscribed"},
    ]
    assert len(payload["errors"]) == 1
    err = payload["errors"][0]
    assert err["user"] == "ghost@example.com"
    assert "ghost@example.com" in err["error"]

    # The server-side DELETE call must only include the principal for
    # the successfully-resolved user.
    delete_calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    assert delete_calls, "expected an unsubscribe DELETE call"
    assert _json.loads(delete_calls[0].kwargs["request"]["principals"]) == ["bob@example.com"]


def test_unsubscribe_users_all_unknown_is_error() -> None:
    """When every identifier fails to resolve, status is ``error`` and the
    DELETE endpoint is never called.
    """
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=[],
        not_removed=[],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["ghost@example.com", "phantom@example.com"],
        id_mode="email",
    )
    assert payload["status"] == "error"
    assert payload["results"] == []
    assert {e["user"] for e in payload["errors"]} == {
        "ghost@example.com",
        "phantom@example.com",
    }
    # No DELETE call should have been issued because no user resolved.
    delete_calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    assert not delete_calls, "DELETE should not be called when no user resolved"


def test_unsubscribe_users_name_ambiguity_lists_matches() -> None:
    """Ambiguous --by-name errors include user IDs and emails."""
    client = _unsubscribe_client(ACTIVE_STREAMS, MEMBERS, removed=[], not_removed=[])
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["Alice Smith"],
        id_mode="name",
    )
    assert payload["status"] == "error"
    error = payload["errors"][0]
    assert error["matches"] == [
        {"user_id": 100, "full_name": "Alice Smith", "email": "alice@example.com"},
        {"user_id": 101, "full_name": "Alice Smith", "email": "alice2@example.com"},
    ]
    assert "alice@example.com" in error["error"]
    assert "id: 100" in error["error"]


def test_unsubscribe_users_rejects_resolved_user_without_email() -> None:
    """Name/email modes require a usable email principal per resolved user."""
    members = [{"user_id": 300, "full_name": "No Email", "is_bot": False, "is_active": True}]
    client = _unsubscribe_client(ACTIVE_STREAMS, members, removed=[], not_removed=[])
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["No Email"],
        id_mode="name",
    )
    assert payload["status"] == "error"
    assert payload["results"] == []
    assert "missing email" in payload["errors"][0]["error"]
    delete_calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    assert not delete_calls


def test_unsubscribe_users_by_id_passes_principals_as_ints() -> None:
    """When id_mode='id', principals sent to Zulip are integer user ids."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=[200],
        not_removed=[],
    )
    payload = unsubscribe_users(
        client,
        channel="general",
        users=["200"],
        id_mode="id",
    )
    assert payload["status"] == "success"
    # Inspect the DELETE call arguments.
    calls = [c for c in client.call_endpoint.call_args_list if c.kwargs.get("url") == "users/me/subscriptions"]
    assert calls, "expected an unsubscribe DELETE call"
    request = calls[0].kwargs["request"]
    assert _json.loads(request["subscriptions"]) == ["general"]
    assert _json.loads(request["principals"]) == [200]


def test_unsubscribe_users_by_channel_id() -> None:
    """``channel_id`` may target the channel instead of by name."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=["bob@example.com"],
        not_removed=[],
    )
    payload = unsubscribe_users(
        client,
        channel_id=2,
        users=["bob@example.com"],
        id_mode="email",
    )
    assert payload["channel_id"] == 2
    assert payload["channel_name"] == "Engineering"
    assert payload["status"] == "success"


def test_unsubscribe_users_requires_one_channel_target() -> None:
    """Exactly one of ``channel`` or ``channel_id`` must be supplied."""
    client = _unsubscribe_client(ACTIVE_STREAMS, MEMBERS)
    with pytest.raises(ZulipValidationError):
        _ = unsubscribe_users(client, users=["x"], id_mode="email")
    with pytest.raises(ZulipValidationError):
        _ = unsubscribe_users(
            client,
            channel="general",
            channel_id=1,
            users=["x"],
            id_mode="email",
        )


def test_unsubscribe_users_requires_at_least_one_user() -> None:
    """An empty user list is a programmer error."""
    client = _unsubscribe_client(ACTIVE_STREAMS, MEMBERS)
    with pytest.raises(ZulipValidationError):
        _ = unsubscribe_users(client, channel="general", users=[], id_mode="email")


def test_unsubscribe_users_rejects_more_than_fifty_users() -> None:
    """Bulk unsubscribe enforces the shared 50-user invocation limit."""
    client = _unsubscribe_client(ACTIVE_STREAMS, MEMBERS)
    with pytest.raises(ZulipValidationError, match="at most 50 users"):
        _ = unsubscribe_users(
            client,
            channel="general",
            users=[f"user{i}@example.com" for i in range(51)],
            id_mode="email",
        )


def test_unsubscribe_users_api_error_raises() -> None:
    """A non-success Zulip response surfaces as :class:`ZulipAPIError`."""
    client = _unsubscribe_client(
        ACTIVE_STREAMS,
        MEMBERS,
        removed=[],
        not_removed=[],
        result="error",
        msg="Boom",
    )
    with pytest.raises(ZulipAPIError, match="Boom"):
        _ = unsubscribe_users(
            client,
            channel="general",
            users=["bob@example.com"],
            id_mode="email",
        )


def test_unsubscribe_users_resolved_channel_skips_resolution() -> None:
    """A caller-supplied ``resolved_channel`` skips ``GET /streams``.

    Pinning this behavior prevents the CLI from incurring two streams
    round-trips per ``zulip channel unsubscribe`` invocation: the CLI
    pre-resolves the channel to capture the resolved id/name for its
    ``--json`` error payload contract and then forwards the result
    here.
    """
    client = mock.MagicMock()

    def call_endpoint(*, url: str, method: str, request: dict[str, Any] | None = None) -> Any:
        if url == "streams":
            raise AssertionError("unsubscribe_users must not call GET /streams when resolved_channel is supplied")
        if url == "users/me/subscriptions" and method == "DELETE":
            return {
                "result": "success",
                "msg": "",
                "removed": ["general"],
                "not_removed": [],
            }
        raise AssertionError(f"Unexpected endpoint call: {method} {url}")

    client.call_endpoint.side_effect = call_endpoint
    client.get_members.return_value = {"result": "success", "members": MEMBERS}

    payload = unsubscribe_users(
        client,
        ["bob@example.com"],
        id_mode="email",
        resolved_channel={"stream_id": 1, "name": "general"},
    )
    assert payload["status"] == "success"
    assert payload["channel_id"] == 1
    assert payload["channel_name"] == "general"


def test_unsubscribe_users_rejects_malformed_resolved_channel() -> None:
    """A caller-supplied channel must include numeric id and string name."""
    client = mock.MagicMock()
    with pytest.raises(ZulipAPIError, match="Malformed stream object"):
        _ = unsubscribe_users(
            client,
            ["bob@example.com"],
            id_mode="email",
            resolved_channel={"stream_id": "bad", "name": "general"},
        )
