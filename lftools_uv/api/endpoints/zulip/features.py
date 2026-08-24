# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Server feature-level detection and gating.

Zulip exposes capabilities progressively via ``zulip_feature_level``.
The thresholds here are the minimum levels each capability needs, and
:func:`check_feature_level` turns a shortfall into the FR-019
canonical error message.
"""

from __future__ import annotations

from typing import Any

from .errors import ZulipAPIError, ZulipFeatureLevelError

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
#: * Feature level 357 — group-based channel subscription via
#:   ``can_subscribe_group``.
#: * Feature level 161 — ``can_remove_subscribers_group`` permission.
#: * Feature level 334 — ``topic_policy`` per-channel field.
#: * Feature level 59 — stream reactivation via stream update API.
#: * Feature level 389 — channel folders.
#: * Feature level 414 — channel folder ordering.
FEATURE_LEVELS: dict[str, int] = {
    "web-public": 12,
    "can-subscribe-group": 357,
    "can-remove-subscribers-group": 161,
    "topic-policy": 334,
    "unarchive": 59,
    "channel-folders": 389,
    "channel-folders-order": 414,
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
