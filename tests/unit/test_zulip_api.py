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
    resolve_channel,
    resolve_groups,
    resolve_users,
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


def test_get_client_rejects_incomplete_credentials() -> None:
    """``get_client`` errors clearly when synthesized creds are incomplete."""
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


def _channels_payload(active: list[dict[str, Any]], archived: list[dict[str, Any]]) -> Any:
    """Return a client whose streams endpoint returns ``active`` or ``archived``."""
    client = mock.MagicMock()

    def side_effect(*, url: str, method: str, request: dict[str, Any] | None = None) -> Any:
        assert url == "streams"
        assert method == "GET"
        if request and request.get("include_archived"):
            return {"result": "success", "streams": archived}
        return {"result": "success", "streams": active}

    client.call_endpoint.side_effect = side_effect
    return client


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
    client = _channels_payload(LIST_ACTIVE, LIST_ARCHIVED)
    channels = list_channels(client)
    assert [c["stream_id"] for c in channels] == [1, 2, 3]
    assert all(not c["is_archived"] for c in channels)


def test_list_channels_normalizes_type() -> None:
    """Each stream maps to one of public / private / web-public."""
    client = _channels_payload(LIST_ACTIVE, LIST_ARCHIVED)
    by_id = {c["stream_id"]: c for c in list_channels(client)}
    assert by_id[1]["type"] == "public"
    assert by_id[2]["type"] == "private"
    assert by_id[3]["type"] == "web-public"


def test_list_channels_include_archived_returns_all() -> None:
    """``include_archived=True`` returns the archived superset."""
    client = _channels_payload(LIST_ACTIVE, LIST_ARCHIVED)
    channels = list_channels(client, include_archived=True)
    assert {c["stream_id"] for c in channels} == {1, 2, 3, 99}


def test_list_channels_empty_list() -> None:
    """An empty server returns an empty list, not an error."""
    client = _channels_payload([], [])
    assert list_channels(client) == []


def test_list_channels_propagates_api_error() -> None:
    """API failures bubble up as ``ZulipAPIError``."""
    client = mock.MagicMock()
    client.call_endpoint.return_value = {"result": "error", "msg": "boom"}
    with pytest.raises(ZulipAPIError):
        _ = list_channels(client)


def test_list_channels_keeps_description_and_count() -> None:
    """The returned dict carries description and subscriber_count."""
    client = _channels_payload(LIST_ACTIVE, LIST_ARCHIVED)
    by_id = {c["stream_id"]: c for c in list_channels(client)}
    assert by_id[1]["description"] == "General discussion"
    assert by_id[1]["subscriber_count"] == 42
    assert by_id[1]["name"] == "general"
