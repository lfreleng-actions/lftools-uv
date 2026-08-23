# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Channel lookup and listing.

Holds the raw stream fetch, the name/id resolution used by nearly
every other module in this package, and the ``channel list``
projection.
"""

from __future__ import annotations

from typing import Any, Literal

from .errors import ZulipAPIError, ZulipNotFoundError, ZulipValidationError


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


#: Allowed values for the ``--type`` flag on ``channel update``.
ChannelType = Literal["public", "private", "web-public"]
