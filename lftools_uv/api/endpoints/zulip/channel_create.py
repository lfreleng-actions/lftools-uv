# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Channel creation.

Backs ``lftools-uv zulip channel create``: validates the requested
settings, applies the feature-level gates, and issues the subscribe
call that Zulip uses to create a channel.
"""

from __future__ import annotations

from typing import Any, Literal

from .dispatch import resolve_channel
from .errors import (
    ZulipAPIError,
    ZulipLockoutError,
    ZulipNotFoundError,
    ZulipValidationError,
)
from .features import FEATURE_LEVELS, check_feature_level
from .folders import _validate_channel_folder_assignment_id
from .groups import GroupSettingValue
from .logger import log
from .topics import TOPIC_POLICY_MAP, VALID_TOPIC_POLICIES


def create_channel(
    client: Any,
    *,
    name: str,
    description: str = "",
    channel_type: Literal["public", "private", "web-public"] = "public",
    subscribe_user_ids: list[int] | None = None,
    allow_group_value: GroupSettingValue | None = None,
    can_remove_subscribers_group_value: GroupSettingValue | None = None,
    announce: bool | None = None,
    topic_policy: str | None = None,
    folder_id: int | None = None,
    folder_id_specified: bool = False,
) -> dict[str, Any]:
    """Create a new Zulip channel (stream).

    Parameters
    ----------
    client
        Authenticated Zulip client instance.
    name
        The channel name (required).
    description
        Optional channel description.
    channel_type
        One of ``public``, ``private``, or ``web-public``.
    subscribe_user_ids
        List of user IDs to subscribe on creation.
    allow_group_value
        Resolved group-setting value for ``can_subscribe_group`` field.
        For private channels, callers should validate this is not the
        ``Nobody`` group before calling (to prevent lockout).
    can_remove_subscribers_group_value
        Resolved group-setting value for ``can_remove_subscribers_group``.
    announce
        ``True`` to announce, ``False`` to suppress, ``None`` for API default.
    topic_policy
        One of ``allow``, ``deny``, ``follow-default``, or ``None``.
    folder_id
        Channel folder ID to assign, or ``None`` to clear when
        ``folder_id_specified`` is true.

    Returns
    -------
    dict
        A ``MutationResult``-style dict with keys ``status``, ``channel_id``,
        ``channel_name``, ``operation``, and ``type``.

    Raises
    ------
    ZulipValidationError
        For client-side validation failures (e.g. invalid topic-policy value).
    ZulipLockoutError
        When creating a private channel without subscribers and allow-group
        is either missing or only contains ``Nobody``.
    ZulipFeatureLevelError
        When the server lacks the required feature level for web-public,
        topic-policy, can-subscribe-group, or can-remove-subscribers-group
        features.
    ZulipAPIError
        For transport or server errors.
    """
    # Validate topic_policy if provided
    if topic_policy is not None and topic_policy not in VALID_TOPIC_POLICIES:
        raise ZulipValidationError(
            f"Invalid topic-policy value: {topic_policy!r}. Valid values are: {', '.join(sorted(VALID_TOPIC_POLICIES))}"
        )

    # Feature-level checks
    if channel_type == "web-public":
        check_feature_level(client, FEATURE_LEVELS["web-public"], "web-public channels")

    if topic_policy is not None:
        check_feature_level(client, FEATURE_LEVELS["topic-policy"], "topic-policy")

    if allow_group_value is not None:
        check_feature_level(client, FEATURE_LEVELS["can-subscribe-group"], "group-based channel subscription")

    if can_remove_subscribers_group_value is not None:
        check_feature_level(client, FEATURE_LEVELS["can-remove-subscribers-group"], "can-remove-subscribers-group")

    if folder_id is not None:
        _validate_channel_folder_assignment_id(folder_id)
    if folder_id is not None or folder_id_specified:
        check_feature_level(client, FEATURE_LEVELS["channel-folders"], "channel-folders")

    # Lockout prevention for private channels:
    # Require at least one subscriber OR a non-None allow_group_value.
    # Callers must validate that allow_group_value is not the Nobody group
    # before calling (the CLI does this via resolve_groups with allow_nobody=False).
    has_subscribers = bool(subscribe_user_ids)
    has_allow_group = allow_group_value is not None

    if channel_type == "private" and not has_subscribers and not has_allow_group:
        raise ZulipLockoutError(
            "Private channels require at least one --subscribe user or a non-Nobody --allow-group to prevent lockout."
        )

    subscription: dict[str, Any] = {"name": name}
    if description:
        subscription["description"] = description
    if folder_id is not None or folder_id_specified:
        subscription["folder_id"] = folder_id

    principals: list[int] = list(subscribe_user_ids) if subscribe_user_ids else []

    request: dict[str, Any] = {
        "subscriptions": [subscription],
        "principals": principals,
        "invite_only": channel_type == "private",
        "is_web_public": channel_type == "web-public",
    }

    if announce is True:
        request["announce"] = True
    elif announce is False:
        request["announce"] = False
    # None = API default (no key)

    if allow_group_value is not None:
        request["can_subscribe_group"] = allow_group_value

    if can_remove_subscribers_group_value is not None:
        request["can_remove_subscribers_group"] = can_remove_subscribers_group_value

    # Make the API call
    try:
        response = client.call_endpoint(
            url="users/me/subscriptions",
            method="POST",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to create channel: {exc}") from exc

    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg", str(response)) if isinstance(response, dict) else str(response)
        raise ZulipAPIError(f"Failed to create channel: {msg}")

    # Extract the stream_id from the response
    # The subscriptions endpoint returns subscriptions in the response as a dict
    # mapping email -> list of stream names. We need to fetch the stream to get its ID.
    warnings: list[str] = []
    try:
        stream = resolve_channel(client, name=name)
        stream_id = stream["stream_id"]
    except ZulipNotFoundError:
        # Channel was created but we can't find it - unusual edge case
        stream_id = None
        if topic_policy is not None:
            warnings.append(f"Channel created but could not locate to apply topic-policy '{topic_policy}'")

    # If topic_policy was requested, apply it via PATCH using the topics_policy field
    # (introduced in Zulip feature level 334)
    topic_policy_applied = False
    if topic_policy is not None and stream_id is not None:
        topic_policy_value = TOPIC_POLICY_MAP[topic_policy]
        try:
            patch_response = client.call_endpoint(
                url=f"streams/{stream_id}",
                method="PATCH",
                request={"topics_policy": topic_policy_value},
            )
            if isinstance(patch_response, dict) and patch_response.get("result") == "success":
                topic_policy_applied = True
            else:
                patch_msg = patch_response.get("msg") if isinstance(patch_response, dict) else str(patch_response)
                warnings.append(f"Failed to apply topic-policy '{topic_policy}': {patch_msg}")
                log.warning("Failed to set topic_policy on channel %s: %s", name, patch_msg)
        except Exception as exc:  # pragma: no cover
            warnings.append(f"Failed to apply topic-policy '{topic_policy}': {exc}")
            log.warning("Failed to set topic_policy on channel %s: %s", name, exc)

    # Determine overall status
    status = "success"
    if warnings:
        status = "partial"

    result: dict[str, Any] = {
        "status": status,
        "channel_id": stream_id,
        "channel_name": name,
        "operation": "create",
        "type": channel_type,
    }
    if topic_policy is not None:
        result["topic_policy_applied"] = topic_policy_applied
    if folder_id is not None or folder_id_specified:
        result["folder_id"] = folder_id
    if warnings:
        result["warnings"] = warnings

    return result
