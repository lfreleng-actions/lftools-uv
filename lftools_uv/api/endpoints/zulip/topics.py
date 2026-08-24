# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Per-channel topic policy.

The ``topics_policy`` channel field arrived in Zulip feature level
334; this module owns the string/integer mapping used across the
package as well as the ``topic-policy`` get/set operations.
"""

from __future__ import annotations

from typing import Any, Literal

from .dispatch import resolve_channel
from .errors import ZulipAPIError, ZulipValidationError
from .features import FEATURE_LEVELS, check_feature_level

#: Valid topic-policy values per spec.
VALID_TOPIC_POLICIES = frozenset({"allow", "deny", "follow-default"})

#: Zulip API mapping from topic_policy string to integer.
TOPIC_POLICY_MAP: dict[str, int] = {
    "allow": 1,
    "deny": 2,
    "follow-default": 0,
}
TOPIC_POLICY_REVERSE_MAP: dict[int, str] = {value: key for key, value in TOPIC_POLICY_MAP.items()}


#: Allowed values for the ``--topic-policy`` flag.
TopicPolicy = Literal["allow", "deny", "follow-default"]


def _normalize_topic_policy(raw_policy: Any) -> TopicPolicy:
    """Translate Zulip topic-policy API values to CLI policy strings."""
    if isinstance(raw_policy, str) and raw_policy in VALID_TOPIC_POLICIES:
        return raw_policy  # type: ignore[return-value]
    if not isinstance(raw_policy, bool) and isinstance(raw_policy, int) and raw_policy in TOPIC_POLICY_REVERSE_MAP:
        return TOPIC_POLICY_REVERSE_MAP[raw_policy]  # type: ignore[return-value]
    raise ZulipAPIError(f"Malformed topic-policy value from server: {raw_policy!r}")


def _resolve_topic_policy_channel(
    client: Any,
    channel: str | int | dict[str, Any],
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Resolve a topic-policy target passed as name, ID, or stream dict."""
    if isinstance(channel, bool) or channel is None:
        raise ZulipValidationError("topic-policy requires a channel name or id")
    if isinstance(channel, dict):
        return channel
    if isinstance(channel, int):
        if channel <= 0:
            raise ZulipValidationError(f"topic-policy requires a positive channel id (got {channel})")
        return resolve_channel(client, channel_id=channel, include_archived=include_archived)
    if isinstance(channel, str):
        channel_name = channel.strip()
        if not channel_name:
            raise ZulipValidationError("topic-policy requires a non-empty channel name")
        return resolve_channel(client, name=channel_name, include_archived=include_archived)
    raise ZulipValidationError(f"Unsupported channel target type: {type(channel).__name__}")


def get_topic_policy(
    client: Any,
    channel: str | int | dict[str, Any],
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Return the current topic-editing policy for a channel."""
    check_feature_level(client, FEATURE_LEVELS["topic-policy"], feature_name="topic-policy")
    target = _resolve_topic_policy_channel(client, channel, include_archived=include_archived)
    stream_id = target.get("stream_id")
    channel_name = target.get("name")
    if not isinstance(stream_id, int) or not isinstance(channel_name, str):
        raise ZulipAPIError(f"Resolved channel missing stream_id/name: {target!r}")

    try:
        response = client.call_endpoint(url=f"streams/{stream_id}", method="GET")
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to read topic policy for {channel_name!r}: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to read topic policy for {channel_name!r}: {msg or response!r}")
    stream_info = response.get("stream")
    if not isinstance(stream_info, dict):
        raise ZulipAPIError(f"Malformed stream-info response for {channel_name!r}: {response!r}")

    raw_policy = stream_info.get("topics_policy", stream_info.get("topic_policy"))
    topic_policy = _normalize_topic_policy(raw_policy)
    return {
        "channel_id": stream_id,
        "channel_name": channel_name,
        "topic_policy": topic_policy,
    }


def set_topic_policy(
    client: Any,
    channel: str | int | dict[str, Any],
    policy: TopicPolicy,
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Set a channel topic-editing policy via the Zulip PATCH endpoint."""
    if policy not in VALID_TOPIC_POLICIES:
        raise ZulipValidationError(
            f"Invalid topic-policy value: {policy!r}. Valid values are: {', '.join(sorted(VALID_TOPIC_POLICIES))}"
        )
    check_feature_level(client, FEATURE_LEVELS["topic-policy"], feature_name="topic-policy")
    target = _resolve_topic_policy_channel(client, channel, include_archived=include_archived)
    stream_id = target.get("stream_id")
    channel_name = target.get("name")
    if not isinstance(stream_id, int) or not isinstance(channel_name, str):
        raise ZulipAPIError(f"Resolved channel missing stream_id/name: {target!r}")

    try:
        response = client.call_endpoint(
            url=f"streams/{stream_id}",
            method="PATCH",
            request={"topics_policy": TOPIC_POLICY_MAP[policy]},
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to set topic policy for {channel_name!r}: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to set topic policy for {channel_name!r}: {msg or response!r}")

    return {
        "status": "success",
        "channel_id": stream_id,
        "channel_name": channel_name,
        "operation": "topic-policy",
        "topic_policy": policy,
    }
