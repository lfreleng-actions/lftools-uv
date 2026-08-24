# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Channel archival and restoration.

Backs ``lftools-uv zulip channel archive`` and ``channel unarchive``.
Both operations are idempotent: an already-archived channel reports
success without re-issuing the mutation.
"""

from __future__ import annotations

from typing import Any

from .dispatch import resolve_channel
from .errors import ZulipAPIError, ZulipValidationError
from .features import FEATURE_LEVELS, check_feature_level
from .logger import log


def archive_channel(
    client: Any,
    channel: str | int,
    *,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Archive (deactivate) a Zulip channel.

    Resolves ``channel`` via :func:`resolve_channel` (by name when a
    string is supplied, by id when an int is supplied) and then calls
    the Zulip ``DELETE /streams/{stream_id}`` endpoint to deactivate
    the stream. The operation is idempotent: if the resolved channel
    is already archived, no DELETE call is issued and a success
    ``MutationResult`` is returned anyway. This matches the FR-018
    expectations for ``--include-archived``.

    Returns the standard ``MutationResult`` payload:
    ``{"status": "success", "channel_id": <int>, "channel_name": <str>,
    "operation": "archive"}``.
    """
    if isinstance(channel, bool) or channel is None:
        raise ZulipValidationError("archive_channel requires a channel name or id")
    if isinstance(channel, int):
        if channel <= 0:
            raise ZulipValidationError(f"archive_channel requires a positive channel id (got {channel})")
        target = resolve_channel(client, channel_id=channel, include_archived=include_archived)
    elif isinstance(channel, str):
        channel_name = channel.strip()
        if not channel_name:
            raise ZulipValidationError("archive_channel requires a non-empty channel name")
        target = resolve_channel(client, name=channel_name, include_archived=include_archived)
    else:  # pragma: no cover - defensive
        raise ZulipValidationError(f"Unsupported channel target type: {type(channel).__name__}")

    stream_id = target.get("stream_id")
    name = target.get("name")
    if not isinstance(stream_id, int):
        raise ZulipAPIError(f"Resolved channel missing numeric stream_id: {target!r}")
    if not isinstance(name, str) or not name:
        raise ZulipAPIError(f"Resolved channel missing string name: {target!r}")

    if target.get("is_archived"):
        # Already-archived no-op: return success without calling DELETE.
        log.debug("Channel %r (id=%s) already archived; skipping DELETE", name, stream_id)
        return {
            "status": "success",
            "channel_id": stream_id,
            "channel_name": name,
            "operation": "archive",
        }

    try:
        response = client.call_endpoint(
            url=f"streams/{stream_id}",
            method="DELETE",
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to archive channel {name!r}: {exc}") from exc

    if not isinstance(response, dict):
        raise ZulipAPIError(f"Malformed archive response for {name!r}: {response!r}")
    result_field = response.get("result")
    if result_field != "success":
        # The Zulip server reports an already-deactivated stream via
        # ``code == "STREAM_DEACTIVATED"``. Treat only that documented
        # code as idempotent success; any other non-success response is a
        # genuine API error.
        code = str(response.get("code", ""))
        msg = str(response.get("msg", ""))
        if code == "STREAM_DEACTIVATED":
            log.debug(
                "Server reports channel %r already deactivated; treating as success",
                name,
            )
        else:
            detail = msg or repr(response)
            raise ZulipAPIError(f"Failed to archive channel {name!r}: {detail}")

    return {
        "status": "success",
        "channel_id": stream_id,
        "channel_name": name,
        "operation": "archive",
    }


def unarchive_channel(
    client: Any,
    channel: str | None = None,
    *,
    channel_id: int | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Reactivate (unarchive) an archived channel.

    Resolves the target channel by name (case-insensitive) or numeric
    ``channel_id``. When ``include_archived`` is ``True`` the listing
    request includes archived streams alongside the active set (so the
    resolver can match either); when ``False`` and the channel exists
    only in the archived set, :class:`ZulipNotFoundError` is raised
    with the FR-018 advisory message suggesting ``--include-archived``.

    Already-active channels are handled idempotently: the function
    returns a success ``MutationResult`` without contacting the stream
    update API, so retries are safe (FR-013 idempotency). Archived
    channels are reactivated with ``PATCH streams/{stream_id}`` and
    ``{"is_archived": False}``.

    Returns the canonical ``MutationResult`` dict:
    ``{"status": "success", "channel_id": int, "channel_name": str,
    "operation": "unarchive"}``.

    Raises:
        ZulipValidationError: if neither/both of ``channel``/``channel_id``
            are supplied.
        ZulipFeatureLevelError: if the server's reported feature level
            is below :data:`FEATURE_LEVELS`[``"unarchive"``].
        ZulipNotFoundError: if the target channel cannot be located
            (FR-018 message includes ``--include-archived`` hint when
            the channel exists only in the archived set).
        ZulipAPIError: if the Zulip server returns a non-success
            stream update response.
    """
    if (channel is None) == (channel_id is None):
        raise ZulipValidationError("unarchive_channel requires exactly one of 'channel' or 'channel_id'")
    if channel_id is not None:
        if isinstance(channel_id, bool) or channel_id <= 0:
            raise ZulipValidationError(f"unarchive_channel requires a positive channel id (got {channel_id})")
    elif channel is not None:
        channel = channel.strip()
        if not channel:
            raise ZulipValidationError("unarchive_channel requires a non-empty channel name")

    check_feature_level(
        client,
        required_level=FEATURE_LEVELS["unarchive"],
        feature_name="unarchive",
    )

    stream = resolve_channel(
        client,
        name=channel,
        channel_id=channel_id,
        include_archived=include_archived,
    )

    stream_id = stream.get("stream_id")
    if not isinstance(stream_id, int):
        raise ZulipAPIError(f"Resolved channel missing numeric stream_id: {stream!r}")
    stream_name = stream.get("name")
    if not isinstance(stream_name, str) or not stream_name:
        raise ZulipAPIError(f"Resolved channel missing string name: {stream!r}")

    # Idempotent no-op: already-active channels skip the PATCH entirely so
    # retries after a partial failure are safe.
    if not stream.get("is_archived", False):
        return {
            "status": "success",
            "channel_id": stream_id,
            "channel_name": stream_name,
            "operation": "unarchive",
        }

    try:
        response = client.call_endpoint(
            url=f"streams/{stream_id}",
            method="PATCH",
            request={"is_archived": False},
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to unarchive channel {stream_name!r}: {exc}") from exc

    if not isinstance(response, dict) or response.get("result") != "success":
        msg = (response or {}).get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to unarchive channel {stream_name!r}: {msg or response!r}")

    return {
        "status": "success",
        "channel_id": stream_id,
        "channel_name": stream_name,
        "operation": "unarchive",
    }
