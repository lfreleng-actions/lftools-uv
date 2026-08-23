# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Channel updates.

Backs ``lftools-uv zulip channel update``. :func:`update_channel` is an
orchestrator: it validates the requested change, applies the FR-019
feature-level gates, resolves the target channel and any group settings,
enforces lockout prevention, and only then issues the PATCH. Each of
those steps lives in its own helper below, in the order the orchestrator
runs them.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from .channels import ChannelType
from .dispatch import resolve_channel
from .errors import ZulipAPIError, ZulipLockoutError, ZulipValidationError
from .features import FEATURE_LEVELS, check_feature_level
from .folders import _validate_channel_folder_assignment_id
from .groups import GroupSettingValue, resolve_groups
from .topics import TOPIC_POLICY_MAP, TopicPolicy
from .users import IdMode, resolve_users


def _subscriber_count(
    client: Any,
    stream_id: int,
    *,
    channel: dict[str, Any] | None = None,
) -> int:
    """Return the number of subscribers to ``stream_id``.

    Fast path: when the already-resolved ``channel`` dict carries a
    ``subscriber_count`` integer (exposed by recent Zulip servers), use
    it directly to avoid an extra round-trip.

    Slow path: fall back to ``GET /api/v1/streams/{stream_id}/members``
    and count the returned ``subscribers`` list. This is materially
    more expensive on large channels because it fetches the full
    subscriber-ID list just to answer a yes/no question.

    Used by :func:`update_channel` to decide whether the lockout-
    prevention rule applies when converting a channel to private
    (FR-004 / spec scenario 13/14).
    """
    if channel is not None:
        hint = channel.get("subscriber_count")
        if isinstance(hint, int) and hint >= 0:
            return hint
    try:
        response = client.call_endpoint(
            url=f"streams/{stream_id}/members",
            method="GET",
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to query channel members: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected members response: {response!r}")
    subscribers = response.get("subscribers", [])
    if not isinstance(subscribers, list):
        raise ZulipAPIError(f"Malformed members payload: {response!r}")
    return len(subscribers)


@dataclass(frozen=True)
class _ChannelUpdate:
    """The settings a single :func:`update_channel` call wants to change.

    Every field mirrors the identically named :func:`update_channel`
    parameter. Grouping them into one value keeps each helper below down
    to a couple of arguments.
    """

    new_name: str | None = None
    description: str | None = None
    channel_type: ChannelType | None = None
    topic_policy: TopicPolicy | None = None
    subscribe: tuple[str, ...] = ()
    user_id_mode: IdMode | None = None
    allow_group: str | None = None
    can_remove_subscribers_group: str | None = None
    folder_id: int | None = None
    folder_id_specified: bool = False

    @property
    def folder_change(self) -> bool:
        """Whether the update touches the channel's folder assignment."""
        return self.folder_id is not None or self.folder_id_specified


def _validate_update_request(changes: _ChannelUpdate) -> None:
    """Reject an update that asks for nothing, or for an invalid value."""
    settings_specified = (
        any(
            v is not None
            for v in (
                changes.new_name,
                changes.description,
                changes.channel_type,
                changes.topic_policy,
                changes.allow_group,
                changes.can_remove_subscribers_group,
            )
        )
        or bool(changes.subscribe)
        or changes.folder_id_specified
        or changes.folder_id is not None
    )
    if not settings_specified:
        raise ZulipValidationError(
            "channel update requires at least one setting to change "
            "(--name, --description, --type, --topic-policy, --allow-group, "
            "--folder, --subscribe, or --can-remove-subscribers-group)"
        )

    valid_channel_types = {"public", "private", "web-public"}
    if changes.channel_type is not None and changes.channel_type not in valid_channel_types:
        raise ZulipValidationError(
            f"Invalid channel_type {changes.channel_type!r}; expected one of {', '.join(sorted(valid_channel_types))}"
        )
    valid_topic_policies = {"allow", "deny", "follow-default"}
    if changes.topic_policy is not None and changes.topic_policy not in valid_topic_policies:
        raise ZulipValidationError(
            f"Invalid topic_policy {changes.topic_policy!r}; expected one of {', '.join(sorted(valid_topic_policies))}"
        )
    if changes.folder_id is not None:
        _validate_channel_folder_assignment_id(changes.folder_id)


def _check_web_public_conversion(client: Any) -> None:
    """Verify that the server and the realm both permit web-public channels."""
    # Fetch server settings ONCE and reuse for both the feature-
    # level check (by priming the cached level) and the spectator-
    # access validation (spec scenario 8). Avoids two HTTP calls
    # when the cache is cold.
    try:
        settings_response = client.get_server_settings()
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to query server settings: {exc}") from exc
    if not isinstance(settings_response, dict) or settings_response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected server-settings response: {settings_response!r}")
    # Prime the feature-level cache so the following check_feature_level
    # call does not issue a second HTTP request.
    level_value = settings_response.get("zulip_feature_level")
    if isinstance(level_value, int):
        try:
            client._lftools_feature_level = level_value
        except AttributeError:  # pragma: no cover - defensive
            pass
    check_feature_level(client, FEATURE_LEVELS["web-public"], feature_name="web-public")
    # ``realm_enable_spectator_access`` is present on recent Zulip
    # servers; defensively allow the transition when the field is
    # absent (older servers leave enforcement to the API itself).
    spectator = settings_response.get("realm_enable_spectator_access")
    if spectator is False:
        # Use ZulipValidationError (not ZulipFeatureLevelError) so
        # the user sees the actual cause — feature-level error
        # messages are formatted as version mismatches and would
        # be misleading when the realm has explicitly disabled
        # spectator access.
        raise ZulipValidationError(
            "Cannot convert channel to web-public: spectator access "
            "is disabled on this Zulip realm (realm_enable_spectator_access=false). "
            "Enable spectator access in the realm settings first."
        )


def _check_update_feature_levels(client: Any, changes: _ChannelUpdate) -> None:
    """Apply the FR-019 feature-level gates for the requested settings."""
    if changes.channel_type == "web-public":
        _check_web_public_conversion(client)
    if changes.topic_policy is not None:
        check_feature_level(client, FEATURE_LEVELS["topic-policy"], feature_name="topic-policy")
    if changes.allow_group is not None:
        check_feature_level(client, FEATURE_LEVELS["can-subscribe-group"], feature_name="can-subscribe-group")
    if changes.can_remove_subscribers_group is not None:
        check_feature_level(
            client,
            FEATURE_LEVELS["can-remove-subscribers-group"],
            feature_name="can-remove-subscribers-group",
        )
    if changes.folder_change:
        check_feature_level(client, FEATURE_LEVELS["channel-folders"], feature_name="channel-folders")


def _resolved_channel_identity(channel: dict[str, Any]) -> tuple[int, str]:
    """Return the ``(stream_id, name)`` pair carried by a resolved channel."""
    stream_id_raw = channel.get("stream_id")
    if not isinstance(stream_id_raw, int):
        raise ZulipAPIError(f"Resolved channel missing stream_id: {channel!r}")
    name_raw = channel.get("name")
    if not isinstance(name_raw, str):
        raise ZulipAPIError(f"Resolved channel missing name: {channel!r}")
    return stream_id_raw, name_raw


def _resolve_allow_group(
    client: Any,
    allow_group: str | None,
) -> tuple[list[dict[str, Any]] | None, GroupSettingValue | None]:
    """Resolve ``--allow-group`` into its group dicts and API value.

    ``allow_group`` is always resolved with allow_nobody=True; the
    lockout-prevention check decides whether a Nobody-only value is
    acceptable in the current context. (Per spec, Nobody is only
    forbidden when converting to private with 0 existing subscribers
    and no --subscribe targets; on a channel that already has
    subscribers, Nobody is allowed and simply disables future joins.)
    """
    if allow_group is None:
        return None, None
    return resolve_groups(client, allow_group, allow_nobody=True)


def _resolve_can_remove_group(client: Any, spec: str | None) -> GroupSettingValue | None:
    """Resolve ``--can-remove-subscribers-group`` into its API value."""
    if spec is None:
        return None
    _, can_remove_value = resolve_groups(client, spec)
    return can_remove_value


def _allow_group_satisfies_lockout(
    allow_group_resolved: list[dict[str, Any]] | None,
    allow_group_value: GroupSettingValue | None,
) -> bool:
    """Whether an ``--allow-group`` value retains access to the channel.

    An allow-group satisfies lockout prevention only if it resolves to
    something other than just the Nobody system role (which would
    disable the permission entirely).
    """
    allow_group_is_only_nobody = (
        allow_group_resolved is not None
        and len(allow_group_resolved) == 1
        and allow_group_resolved[0].get("name") == "role:nobody"
    )
    return allow_group_value is not None and not allow_group_is_only_nobody


def _enforce_private_lockout(
    client: Any,
    channel: dict[str, Any],
    stream_id: int,
    changes: _ChannelUpdate,
    *,
    allow_group_satisfies: bool,
) -> None:
    """Refuse a conversion to private that would lock everyone out."""
    is_type_to_private = changes.channel_type == "private" and not bool(channel.get("invite_only"))
    if not is_type_to_private:
        return
    if bool(changes.subscribe) or allow_group_satisfies:
        return
    # Inspect current subscriber count; if zero, refuse.
    current = _subscriber_count(client, stream_id, channel=channel)
    if current == 0:
        raise ZulipLockoutError(
            "Converting channel to private with no existing subscribers "
            "would lock everyone out. Specify --subscribe users or a "
            "non-Nobody --allow-group to retain access."
        )


def _validate_subscribe_flags(changes: _ChannelUpdate) -> None:
    """Reject ``--subscribe`` combinations the update endpoint cannot honour."""
    if changes.subscribe and changes.channel_type != "private":
        raise ZulipValidationError("--subscribe is only valid when using --type private")
    if changes.subscribe and changes.user_id_mode is None:
        raise ZulipValidationError("--subscribe requires one of --by-email/--by-id/--by-name")


def _subscribe_before_update(client: Any, resolved_name: str, changes: _ChannelUpdate) -> None:
    """Subscribe the ``--subscribe`` users before the PATCH is issued.

    The users are subscribed first so that type-to-private conversions
    truly retain access — relying on the lockout-prevention bypass
    without actually subscribing would still lock the channel out.
    """
    assert changes.user_id_mode is not None  # for type narrowing (validated above)
    resolved_users = resolve_users(client, changes.subscribe, mode=changes.user_id_mode)
    principals: list[Any] = []
    for user in resolved_users:
        user_id_value = user.get("user_id")
        if isinstance(user_id_value, int):
            principals.append(user_id_value)
            continue
        email = user.get("delivery_email") or user.get("email")
        if isinstance(email, str) and email:
            principals.append(email)
            continue
        raise ZulipAPIError(f"Resolved user missing usable principal: {user!r}")
    try:
        sub_response = client.call_endpoint(
            url="users/me/subscriptions",
            method="POST",
            request={
                "subscriptions": json.dumps([{"name": resolved_name}]),
                "principals": json.dumps(principals),
            },
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to subscribe users during update: {exc}") from exc
    if not isinstance(sub_response, dict) or sub_response.get("result") != "success":
        msg = ""
        if isinstance(sub_response, dict):
            msg = str(sub_response.get("msg") or sub_response)
        raise ZulipAPIError(f"Subscribe-during-update failed: {msg or sub_response!r}")


def _build_update_request(
    changes: _ChannelUpdate,
    allow_group_value: GroupSettingValue | None,
    can_remove_value: GroupSettingValue | None,
) -> dict[str, Any]:
    """Build the PATCH body for the requested settings.

    Group settings are wrapped in the ``{"new": value}`` envelope that
    the PATCH endpoints require; note that this differs from the POST
    endpoints (``streams`` create), which take the raw value.
    """
    request: dict[str, Any] = {}
    if changes.new_name is not None:
        request["new_name"] = changes.new_name
    if changes.description is not None:
        request["description"] = changes.description
    if changes.channel_type is not None:
        request["is_private"] = changes.channel_type == "private"
        request["is_web_public"] = changes.channel_type == "web-public"
    if changes.topic_policy is not None:
        request["topics_policy"] = TOPIC_POLICY_MAP[changes.topic_policy]
    if allow_group_value is not None:
        request["can_subscribe_group"] = {"new": allow_group_value}
    if can_remove_value is not None:
        request["can_remove_subscribers_group"] = {"new": can_remove_value}
    if changes.folder_change:
        request["folder_id"] = changes.folder_id
    return request


def _patch_channel(client: Any, stream_id: int, request: dict[str, Any]) -> None:
    """Issue ``PATCH /api/v1/streams/{stream_id}`` and validate the response."""
    try:
        response = client.call_endpoint(
            url=f"streams/{stream_id}",
            method="PATCH",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to update channel: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = ""
        if isinstance(response, dict):
            msg = str(response.get("msg") or response)
        raise ZulipAPIError(f"Update failed: {msg or response!r}")


def _update_result(stream_id: int, resolved_name: str, changes: _ChannelUpdate) -> dict[str, Any]:
    """Build the ``MutationResult`` dict returned by :func:`update_channel`."""
    # Reflect rename in the returned channel_name.
    effective_name = changes.new_name if changes.new_name is not None else resolved_name
    result = {
        "status": "success",
        "channel_id": stream_id,
        "channel_name": effective_name,
        "operation": "update",
    }
    if changes.folder_change:
        result["folder_id"] = changes.folder_id
    return result


def update_channel(
    client: Any,
    *,
    name: str | None = None,
    channel_id: int | None = None,
    new_name: str | None = None,
    description: str | None = None,
    channel_type: ChannelType | None = None,
    topic_policy: TopicPolicy | None = None,
    subscribe_user_specs: Iterable[str] | None = None,
    user_id_mode: IdMode | None = None,
    allow_group: str | None = None,
    can_remove_subscribers_group: str | None = None,
    folder_id: int | None = None,
    folder_id_specified: bool = False,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Update channel settings via ``PATCH /api/v1/streams/{stream_id}``.

    Implements FR-004 (channel update) end-to-end:

    * Validates that at least one setting flag is supplied (rename,
      description, type, topic-policy, allow-group, folder assignment,
      or can-remove-subscribers-group).
    * Applies the FR-019 feature-level checks for web-public,
      topic-policy, can-subscribe-group (``--allow-group``) and
      can-remove-subscribers-group.
    * Enforces lockout prevention when converting to ``private``: if
      the channel currently has 0 subscribers, the caller must supply
      either ``subscribe_user_specs`` (a non-empty list) or a non-Nobody
      ``allow_group`` value. ``Nobody`` does NOT satisfy this rule.
      When ``subscribe_user_specs`` is supplied, the users are
      resolved AND actually subscribed via
      ``POST /api/v1/users/me/subscriptions`` before the PATCH so that
      access is genuinely retained (the API call would otherwise lock
      the channel out, despite passing client-side validation).
    * Resolves group specs and wraps them using the group-setting-update
      ``{"new": value}`` envelope required by the Zulip PATCH endpoints.
      Note that this wrapping differs from the POST endpoints
      (``streams`` create), which take the raw value.
    * Returns the standard ``MutationResult`` dict
      (``status``/``channel_id``/``channel_name``/``operation``).
    """
    changes = _ChannelUpdate(
        new_name=new_name,
        description=description,
        channel_type=channel_type,
        topic_policy=topic_policy,
        subscribe=tuple(subscribe_user_specs or ()),
        user_id_mode=user_id_mode,
        allow_group=allow_group,
        can_remove_subscribers_group=can_remove_subscribers_group,
        folder_id=folder_id,
        folder_id_specified=folder_id_specified,
    )
    _validate_update_request(changes)
    _check_update_feature_levels(client, changes)

    channel = resolve_channel(
        client,
        name=name,
        channel_id=channel_id,
        include_archived=include_archived,
    )
    stream_id, resolved_name = _resolved_channel_identity(channel)

    allow_group_resolved, allow_group_value = _resolve_allow_group(client, changes.allow_group)
    can_remove_value = _resolve_can_remove_group(client, changes.can_remove_subscribers_group)

    _enforce_private_lockout(
        client,
        channel,
        stream_id,
        changes,
        allow_group_satisfies=_allow_group_satisfies_lockout(allow_group_resolved, allow_group_value),
    )

    _validate_subscribe_flags(changes)
    if changes.subscribe:
        _subscribe_before_update(client, resolved_name, changes)

    request = _build_update_request(changes, allow_group_value, can_remove_value)
    _patch_channel(client, stream_id, request)
    return _update_result(stream_id, resolved_name, changes)
