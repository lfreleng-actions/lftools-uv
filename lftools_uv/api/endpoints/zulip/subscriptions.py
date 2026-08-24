# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Channel subscription management.

Listing subscribers plus the bulk subscribe/unsubscribe mutations,
which report per-user outcomes rather than aborting on the first
failure.
"""

from __future__ import annotations

import json
from collections.abc import Iterable
from typing import Any

from .dispatch import resolve_channel
from .errors import (
    ZulipAmbiguityError,
    ZulipAPIError,
    ZulipNotFoundError,
    ZulipValidationError,
)
from .users import IdMode, _fetch_users, _resolve_single_user, resolve_users


def list_subscribers(
    client: Any,
    *,
    name: str | None = None,
    channel_id: int | None = None,
    include_archived: bool = False,
) -> list[dict[str, Any]]:
    """List subscribers of a channel, enriched with name/email metadata.

    Resolves the target channel via :func:`resolve_channel` (so the
    same name/id targeting rules apply, including the friendly
    ``--include-archived`` hint when the channel exists only in the
    archived set). Then calls the Zulip ``GET /streams/{id}/members``
    endpoint and cross-references each subscriber ``user_id`` against
    the users listing to populate ``full_name`` and ``email``.

    Returns a list of ``{"user_id", "full_name", "email"}`` dicts in
    the order returned by the server. When a subscriber's metadata is
    not present in the users listing (e.g. deactivated accounts), the
    enrichment fields are populated with ``None`` rather than raising.

    Raises :class:`ZulipValidationError` if neither or both of
    ``name``/``channel_id`` are supplied, :class:`ZulipNotFoundError`
    when the channel cannot be located, or :class:`ZulipAPIError` for
    server-side failures.
    """
    if (name is None) == (channel_id is None):
        raise ZulipValidationError("list_subscribers requires exactly one of 'name' or 'channel_id'")
    stream = resolve_channel(
        client,
        name=name,
        channel_id=channel_id,
        include_archived=include_archived,
    )
    stream_id = stream.get("stream_id")
    if not isinstance(stream_id, int) or isinstance(stream_id, bool):
        raise ZulipAPIError(f"Resolved channel missing numeric stream_id: {stream!r}")

    try:
        response = client.call_endpoint(
            url=f"streams/{stream_id}/members",
            method="GET",
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to list subscribers: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        raise ZulipAPIError(f"Unexpected subscribers response: {response!r}")
    subscriber_ids = response.get("subscribers", [])
    if not isinstance(subscriber_ids, list):
        raise ZulipAPIError(f"Malformed subscribers payload: {response!r}")
    if not subscriber_ids:
        return []

    normalized_ids: list[int] = []
    for raw_id in subscriber_ids:
        if not isinstance(raw_id, int) or isinstance(raw_id, bool):
            raise ZulipAPIError(f"Malformed subscriber id in payload: {raw_id!r}")
        normalized_ids.append(raw_id)

    # Build a user_id → member dict lookup so enrichment is O(N+M).
    members = _fetch_users(client)
    by_id: dict[int, dict[str, Any]] = {}
    for member in members:
        uid = member.get("user_id")
        if isinstance(uid, int) and not isinstance(uid, bool):
            by_id[uid] = member

    enriched: list[dict[str, Any]] = []
    for uid in normalized_ids:
        member_record = by_id.get(uid)
        if member_record is None:
            enriched.append({"user_id": uid, "full_name": None, "email": None})
            continue
        full_name = member_record.get("full_name")
        email = member_record.get("delivery_email") or member_record.get("email")
        enriched.append(
            {
                "user_id": uid,
                "full_name": "" if full_name is None else str(full_name),
                "email": "" if email is None else str(email),
            }
        )
    return enriched


#: Spec-defined maximum number of users that can be subscribed in a single
#: invocation. See data-model.md / contracts/cli-commands.md.
MAX_SUBSCRIBE_USERS = 50


def subscribe_users(
    client: Any,
    channel: str | int,
    users: Iterable[str],
    *,
    id_mode: IdMode,
    include_archived: bool = False,
    _resolved_stream: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Subscribe one or more users to a channel.

    ``channel`` may be a string (channel name) or an int (numeric
    ``stream_id``). Numeric channel names are explicitly preserved by
    the CLI layer — callers that want id-based resolution must pass an
    actual ``int``.

    ``users`` is the iterable of identifiers (emails, ids, or full
    names depending on ``id_mode``). Up to :data:`MAX_SUBSCRIBE_USERS`
    identifiers per invocation are permitted (FR / spec cap of 50).

    ``_resolved_stream`` is an internal optimisation: when the caller
    has *already* resolved the channel (e.g. the CLI layer pre-resolves
    so it can thread channel context into ``--json`` error payloads),
    it may pass the resulting stream dict here to skip a redundant
    ``GET /streams`` round-trip. Callers outside this package should
    leave it as ``None``.

    Returns the standard bulk-mutation payload with ``status``,
    ``channel_id``, ``channel_name``, ``operation``, ``results``, and
    ``errors`` fields per ``contracts/cli-commands.md``. Per-user
    outcomes are derived from the Zulip server's ``subscribed`` and
    ``already_subscribed`` maps. The ``unauthorized`` list, if any, is
    surfaced under ``errors``.

    Raises:
        ZulipValidationError: empty user list, more than 50 users, or
            other client-side validation failures.
        ZulipNotFoundError / ZulipAmbiguityError: from resolve_users
            (e.g. unknown identifier, ambiguous full-name match) or
            from resolve_channel (e.g. unknown channel).
        ZulipAPIError: when the Zulip subscribe endpoint returns an
            error response.
    """
    user_list = list(users)
    if not user_list:
        raise ZulipValidationError("subscribe_users requires at least one user identifier")
    if len(user_list) > MAX_SUBSCRIBE_USERS:
        raise ZulipValidationError(
            f"subscribe_users accepts at most {MAX_SUBSCRIBE_USERS} users per invocation (got {len(user_list)})"
        )

    if isinstance(channel, bool):  # bool is an int subclass — reject explicitly
        raise ZulipValidationError(f"Invalid channel argument: {channel!r}")
    if _resolved_stream is not None:
        # Caller (e.g. the CLI) has already resolved the channel. Trust
        # the supplied dict and skip the redundant API round-trip.
        stream = _resolved_stream
    elif isinstance(channel, int):
        stream = resolve_channel(client, channel_id=channel, include_archived=include_archived)
    else:
        stream = resolve_channel(client, name=str(channel), include_archived=include_archived)

    channel_id = stream.get("stream_id")
    channel_name = stream.get("name")
    if not isinstance(channel_id, int) or not isinstance(channel_name, str):
        raise ZulipAPIError(f"Malformed stream object: {stream!r}")

    resolved_users = resolve_users(client, user_list, mode=id_mode)

    # Build a stable per-user identity used for matching the server
    # response and for the ``user`` field in the result payload. Prefer
    # delivery_email (the Zulip "real" address) and fall back to email.
    user_emails: list[str] = []
    for u in resolved_users:
        email = u.get("delivery_email") or u.get("email")
        if not isinstance(email, str) or not email:
            raise ZulipAPIError(f"Resolved user missing email: {u!r}")
        user_emails.append(email)

    import json as _json

    request = {
        "subscriptions": _json.dumps([{"name": channel_name}]),
        "principals": _json.dumps(user_emails),
    }

    try:
        response = client.call_endpoint(url="users/me/subscriptions", method="POST", request=request)
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to subscribe users: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Subscribe request failed: {msg or response!r}")

    # Defensive: the Zulip API contract documents these as a dict / dict
    # / list, but real-world responses can drift (or be replayed via a
    # fake client in tests). Validate the shapes up front so a server-
    # side regression surfaces as a clear ZulipAPIError instead of a
    # misleading "no response from server" per-user error.
    subscribed_raw = response.get("subscribed", {})
    already_raw = response.get("already_subscribed", {})
    unauthorized_raw = response.get("unauthorized", [])
    if not isinstance(subscribed_raw, dict):
        raise ZulipAPIError(
            f"Malformed subscribe response: 'subscribed' must be a dict, got {type(subscribed_raw).__name__}"
        )
    if not isinstance(already_raw, dict):
        raise ZulipAPIError(
            f"Malformed subscribe response: 'already_subscribed' must be a dict, got {type(already_raw).__name__}"
        )
    if not isinstance(unauthorized_raw, list):
        raise ZulipAPIError(
            f"Malformed subscribe response: 'unauthorized' must be a list, got {type(unauthorized_raw).__name__}"
        )

    def _channel_users(field_name: str, mapping: dict[str, Any]) -> set[str]:
        users = mapping.get(channel_name, [])
        if not isinstance(users, list):
            raise ZulipAPIError(
                f"Malformed subscribe response: '{field_name}[{channel_name}]' must be a list, "
                f"got {type(users).__name__}"
            )
        return {str(user) for user in users}

    subscribed = _channel_users("subscribed", subscribed_raw)
    already = _channel_users("already_subscribed", already_raw)
    unauthorized: list[Any] = unauthorized_raw

    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    accounted: set[str] = set()
    for email in user_emails:
        if email in subscribed:
            results.append({"user": email, "status": "subscribed"})
            accounted.add(email)
        elif email in already:
            results.append({"user": email, "status": "already_subscribed"})
            accounted.add(email)
        elif email in unauthorized:
            errors.append({"user": email, "error": "unauthorized"})
            accounted.add(email)
    # Any user not mentioned in either map is treated as an error so
    # callers can detect silent partial failures.
    for email in user_emails:
        if email not in accounted:
            errors.append({"user": email, "error": "no response from server"})

    if errors and not results:
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "success"

    return {
        "status": status,
        "channel_id": channel_id,
        "channel_name": channel_name,
        "operation": "subscribe",
        "results": results,
        "errors": errors,
    }


def unsubscribe_users(
    client: Any,
    users: Iterable[str],
    *,
    channel: str | None = None,
    channel_id: int | None = None,
    id_mode: IdMode,
    include_archived: bool = False,
    resolved_channel: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Unsubscribe one or more users from a channel.

    Resolves the channel target (by name or numeric id) and the user
    identifiers (per ``id_mode``), then calls the Zulip
    ``DELETE /users/me/subscriptions`` endpoint. The return value is a
    bulk :class:`MutationResult`-shaped dict:

    .. code-block:: python

       {
           "status": "success" | "partial" | "error",
           "channel_id": int,
           "channel_name": str,
           "operation": "unsubscribe",
           "results": [
               {"user": "<identifier>", "status": "unsubscribed"},
               {"user": "<identifier>", "status": "not_subscribed"},
           ],
           "errors": [],
       }

    The Zulip server returns ``removed`` for users who were unsubscribed
    and ``not_removed`` for users who were not subscribed in the first
    place — the latter is reported as a ``not_subscribed`` no-op,
    consistent with the CLI contract "exit 0 = all succeeded (including
    no-ops)".

    Pass ``resolved_channel`` (a stream dict as returned by
    :func:`resolve_channel`) to skip the internal channel resolution
    step. This lets callers that have already resolved the channel
    (for example the CLI, which needs the resolved id available for
    the ``--json`` error payload before invoking this function) avoid
    a redundant ``GET /streams`` round-trip. When ``resolved_channel``
    is supplied, ``channel`` and ``channel_id`` are ignored.
    """
    if resolved_channel is None:
        if (channel is None) == (channel_id is None):
            raise ZulipValidationError("unsubscribe_users requires exactly one of 'channel' or 'channel_id'")
    user_list = list(users)
    if not user_list:
        raise ZulipValidationError("unsubscribe_users requires at least one user")
    if len(user_list) > MAX_SUBSCRIBE_USERS:
        raise ZulipValidationError(
            f"unsubscribe_users accepts at most {MAX_SUBSCRIBE_USERS} users per invocation (got {len(user_list)})"
        )

    if resolved_channel is not None:
        target = resolved_channel
    else:
        target = resolve_channel(
            client,
            name=channel,
            channel_id=channel_id,
            include_archived=include_archived,
        )
    resolved_target_id = target.get("stream_id")
    resolved_target_name = target.get("name")
    if not isinstance(resolved_target_id, int) or not isinstance(resolved_target_name, str):
        raise ZulipAPIError(f"Malformed stream object: {target!r}")

    # Resolve identifiers one-by-one so a single bad entry does not
    # abort the whole bulk operation. Per-user resolution failures are
    # captured into ``errors`` while successfully-resolved users still
    # get sent to the Zulip API. This matches the bulk-operation
    # behavior described in the data-model spec (status: partial).
    members = _fetch_users(client)
    results: list[dict[str, Any]] = []
    errors: list[dict[str, Any]] = []
    principals: list[Any] = []
    resolved_pairs: list[tuple[str, Any]] = []  # (original, principal)

    for original in user_list:
        try:
            user = _resolve_single_user(original, members, mode=id_mode)
        except ZulipAmbiguityError as exc:
            match_parts = [f"{m.get('full_name')} <{m.get('email')}> (id: {m.get('user_id')})" for m in exc.matches]
            detail = f"{exc}; matches: {', '.join(match_parts)}"
            errors.append({"user": original, "error": detail, "matches": exc.matches})
            continue
        except (ZulipNotFoundError, ZulipValidationError) as exc:
            errors.append({"user": original, "error": str(exc)})
            continue
        if id_mode == "id":
            principal: Any = int(user["user_id"])
        else:
            # For both name- and email-mode lookups we send delivery_email
            # (falling back to ``email``) as principals so that the server
            # can match against the channel's subscriber list. Zulip
            # principals accept emails or user IDs interchangeably.
            principal = user.get("delivery_email") or user.get("email")
            if not isinstance(principal, str) or not principal:
                errors.append({"user": original, "error": f"Resolved user missing email: {user!r}"})
                continue
        principals.append(principal)
        resolved_pairs.append((original, principal))

    if not principals:
        # Every identifier failed to resolve — skip the API call entirely
        # and return an all-errors payload so the caller can surface the
        # per-user failures without a spurious server round-trip.
        return {
            "status": "error",
            "channel_id": resolved_target_id,
            "channel_name": resolved_target_name,
            "operation": "unsubscribe",
            "results": results,
            "errors": errors,
        }

    # The DELETE response reports removed/not_removed by stream, not by
    # principal, so request one principal at a time to preserve per-user
    # results and partial-failure reporting.
    for original, principal in resolved_pairs:
        try:
            response = client.call_endpoint(
                url="users/me/subscriptions",
                method="DELETE",
                request={
                    "subscriptions": json.dumps([resolved_target_name]),
                    "principals": json.dumps([principal]),
                },
            )
        except Exception as exc:  # pragma: no cover - network errors
            raise ZulipAPIError(f"Failed to unsubscribe users: {exc}") from exc

        if not isinstance(response, dict) or response.get("result") != "success":
            msg = (response or {}).get("msg") if isinstance(response, dict) else None
            raise ZulipAPIError(f"Unexpected unsubscribe response: {msg or response!r}")

        removed_set = {str(item) for item in response.get("removed", []) or []}
        not_removed_set = {str(item) for item in response.get("not_removed", []) or []}

        if resolved_target_name in removed_set:
            results.append({"user": original, "status": "unsubscribed"})
        elif resolved_target_name in not_removed_set:
            results.append({"user": original, "status": "not_subscribed"})
        else:
            errors.append(
                {
                    "user": original,
                    "error": "Server did not report an outcome for this user",
                }
            )

    if errors and not results:
        status = "error"
    elif errors:
        status = "partial"
    else:
        status = "success"

    return {
        "status": status,
        "channel_id": resolved_target_id,
        "channel_name": resolved_target_name,
        "operation": "unsubscribe",
        "results": results,
        "errors": errors,
    }
