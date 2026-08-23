# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Channel-folder management.

Channel folders arrived in Zulip feature level 389 (ordering in 414),
so every mutation here is feature-gated. Includes the folder
resolution helpers used by ``channel create``/``channel update``.
"""

from __future__ import annotations

import json
from typing import Any, Literal

from .errors import (
    ZulipAmbiguityError,
    ZulipAPIError,
    ZulipNotFoundError,
    ZulipValidationError,
)
from .features import FEATURE_LEVELS, check_feature_level


def _normalize_channel_folder(raw: dict[str, Any]) -> dict[str, Any]:
    """Project a raw Zulip channel-folder object to a stable shape.

    Channel folders require Zulip feature level 389. The ``order`` field
    was added at feature level 414, so missing values are represented as
    ``None`` rather than treated as malformed.
    """
    folder_id = raw.get("id")
    if not isinstance(folder_id, int) or isinstance(folder_id, bool):
        raise ZulipAPIError(f"Channel folder missing numeric id: {raw!r}")
    name = raw.get("name")
    if not isinstance(name, str) or not name:
        raise ZulipAPIError(f"Channel folder missing non-empty name: {raw!r}")
    order_raw = raw.get("order")
    if order_raw is None:
        order: int | None = None
    elif isinstance(order_raw, int) and not isinstance(order_raw, bool):
        order = order_raw
    else:
        raise ZulipAPIError(f"Channel folder has malformed order: {raw!r}")
    description = raw.get("description")
    rendered = raw.get("rendered_description")
    date_created = raw.get("date_created")
    creator_id = raw.get("creator_id")
    return {
        "id": folder_id,
        "name": name,
        "order": order,
        "description": "" if description is None else str(description),
        "rendered_description": "" if rendered is None else str(rendered),
        "is_archived": bool(raw.get("is_archived", False)),
        "date_created": date_created if isinstance(date_created, int) and not isinstance(date_created, bool) else None,
        "creator_id": creator_id if isinstance(creator_id, int) and not isinstance(creator_id, bool) else None,
    }


def _fetch_channel_folders(client: Any, *, include_archived: bool = False) -> list[dict[str, Any]]:
    """Return raw channel folders from ``GET /api/v1/channel_folders``."""
    request: dict[str, Any] = {}
    if include_archived:
        request["include_archived"] = True
    try:
        response = client.call_endpoint(
            url="channel_folders",
            method="GET",
            request=request or None,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to list channel folders: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to list channel folders: {msg or response!r}")
    folders = response.get("channel_folders", [])
    if not isinstance(folders, list):
        raise ZulipAPIError(f"Malformed channel_folders payload: {response!r}")
    return folders


def list_channel_folders(
    client: Any,
    *,
    include_archived: bool = False,
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """List normalized channel folders, gated at feature level 389.

    ``order`` is optional before feature level 414; omitted values are
    returned as ``None`` in JSON and render as a blank table cell.
    """
    check_feature_level(client, FEATURE_LEVELS["channel-folders"], "channel-folders")
    if limit is not None:
        if not isinstance(limit, int) or isinstance(limit, bool) or limit < 0:
            raise ZulipValidationError("--limit must be a non-negative integer")
    raw_folders = _fetch_channel_folders(client, include_archived=include_archived)
    folders = [_normalize_channel_folder(folder) for folder in raw_folders]
    if not include_archived:
        folders = [folder for folder in folders if not folder["is_archived"]]
    if limit is not None:
        folders = folders[:limit]
    return folders


def _get_channel_folder_limits(client: Any) -> dict[str, int]:
    """Return cached `/register` channel-folder length limits when available."""
    cached = getattr(client, "_lftools_channel_folder_limits", None)
    if isinstance(cached, dict):
        return {str(k): v for k, v in cached.items() if isinstance(v, int) and not isinstance(v, bool)}
    limits: dict[str, int] = {}
    try:
        response = client.call_endpoint(url="register", method="GET")
    except Exception:
        response = None
    if isinstance(response, dict) and response.get("result") == "success":
        for key in ("max_channel_folder_name_length", "max_channel_folder_description_length"):
            value = response.get(key)
            if isinstance(value, int) and not isinstance(value, bool):
                limits[key] = value
    try:
        client._lftools_channel_folder_limits = limits
    except AttributeError:  # pragma: no cover - defensive
        pass
    return limits


def _validate_channel_folder_values(
    client: Any,
    *,
    name: str | None = None,
    description: str | None = None,
) -> None:
    """Validate folder names/descriptions against known server limits."""
    if name is not None and not name.strip():
        raise ZulipValidationError("Folder name must not be empty")
    limits = _get_channel_folder_limits(client)
    name_limit = limits.get("max_channel_folder_name_length")
    if name is not None and name_limit is not None and len(name) > name_limit:
        raise ZulipValidationError(f"Folder name exceeds server limit of {name_limit} characters")
    description_limit = limits.get("max_channel_folder_description_length")
    if description is not None and description_limit is not None and len(description) > description_limit:
        raise ZulipValidationError(f"Folder description exceeds server limit of {description_limit} characters")


def _validate_channel_folder_assignment_id(folder_id: Any) -> None:
    """Validate a non-null channel folder assignment ID."""
    if not isinstance(folder_id, int) or isinstance(folder_id, bool) or folder_id <= 0:
        raise ZulipValidationError(f"folder_id must be a positive integer (got {folder_id})")


def _folder_mutation_result(
    response: dict[str, Any],
    *,
    operation: str,
    fallback_id: int | None,
    fallback_name: str | None,
) -> dict[str, Any]:
    """Build the folder mutation result contract from a Zulip response."""
    raw_id = response.get("channel_folder_id", response.get("folder_id", response.get("id", fallback_id)))
    folder_id = raw_id if isinstance(raw_id, int) and not isinstance(raw_id, bool) else fallback_id
    folder_name: str | None = fallback_name
    raw_folder = response.get("channel_folder")
    if isinstance(raw_folder, dict):
        raw_name = raw_folder.get("name")
        if isinstance(raw_name, str):
            folder_name = raw_name
        raw_folder_id = raw_folder.get("id")
        if isinstance(raw_folder_id, int) and not isinstance(raw_folder_id, bool):
            folder_id = raw_folder_id
    raw_name = response.get("folder_name")
    if isinstance(raw_name, str):
        folder_name = raw_name
    return {
        "status": "success",
        "folder_id": folder_id,
        "folder_name": folder_name,
        "operation": operation,
    }


def create_channel_folder(client: Any, name: str, description: str = "") -> dict[str, Any]:
    """Create a channel folder via ``POST /channel_folders/create``.

    Channel folders require Zulip feature level 389. The server enforces
    admin-only permissions; this helper intentionally surfaces those
    API errors without client-side role checks.
    """
    check_feature_level(client, FEATURE_LEVELS["channel-folders"], "channel-folders")
    _validate_channel_folder_values(client, name=name, description=description)
    request = {"name": name, "description": description}
    try:
        response = client.call_endpoint(
            url="channel_folders/create",
            method="POST",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to create channel folder: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to create channel folder: {msg or response!r}")
    return _folder_mutation_result(response, operation="create", fallback_id=None, fallback_name=name)


def update_channel_folder(
    client: Any,
    folder_id: int,
    *,
    name: str | None = None,
    description: str | None = None,
    is_archived: bool | None = None,
) -> dict[str, Any]:
    """Update a channel folder via ``PATCH /channel_folders/{id}``.

    The same endpoint implements rename, description updates, archive,
    and unarchive. Zulip exposes no hard-delete endpoint for folders.
    """
    _validate_channel_folder_assignment_id(folder_id)
    if name is None and description is None and is_archived is None:
        raise ZulipValidationError("folder update requires at least one of --name, --description, or archive state")
    check_feature_level(client, FEATURE_LEVELS["channel-folders"], "channel-folders")
    _validate_channel_folder_values(client, name=name, description=description)
    request: dict[str, Any] = {}
    if name is not None:
        request["name"] = name
    if description is not None:
        request["description"] = description
    if is_archived is not None:
        request["is_archived"] = is_archived
    try:
        response = client.call_endpoint(
            url=f"channel_folders/{folder_id}",
            method="PATCH",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to update channel folder {folder_id}: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to update channel folder {folder_id}: {msg or response!r}")
    operation = "update"
    if is_archived is True and name is None and description is None:
        operation = "archive"
    elif is_archived is False and name is None and description is None:
        operation = "unarchive"
    return _folder_mutation_result(response, operation=operation, fallback_id=folder_id, fallback_name=name)


def archive_channel_folder(client: Any, folder_id: int) -> dict[str, Any]:
    """Archive a channel folder; there is no hard-delete endpoint."""
    return update_channel_folder(client, folder_id, is_archived=True)


def unarchive_channel_folder(client: Any, folder_id: int) -> dict[str, Any]:
    """Unarchive a channel folder via the feature-level-389 PATCH API."""
    return update_channel_folder(client, folder_id, is_archived=False)


def reorder_channel_folders(client: Any, order: list[int]) -> dict[str, Any]:
    """Reorder all channel folders via ``PATCH /channel_folders``.

    Zulip requires feature level 414 and expects ``order`` as a
    JSON-encoded array containing every channel folder ID exactly once.
    The server enforces admin-only permissions and validates completeness.
    """
    check_feature_level(client, FEATURE_LEVELS["channel-folders-order"], "channel-folders-order")
    for folder_id in order:
        _validate_channel_folder_assignment_id(folder_id)
    request = {"order": json.dumps(order)}
    try:
        response = client.call_endpoint(
            url="channel_folders",
            method="PATCH",
            request=request,
        )
    except Exception as exc:  # pragma: no cover - network errors
        raise ZulipAPIError(f"Failed to reorder channel folders: {exc}") from exc
    if not isinstance(response, dict) or response.get("result") != "success":
        msg = response.get("msg") if isinstance(response, dict) else None
        raise ZulipAPIError(f"Failed to reorder channel folders: {msg or response!r}")
    return response


def plan_folder_move(
    current_order: list[int],
    target_id: int,
    reference_id: int,
    position: Literal["before", "after"],
) -> list[int]:
    """Return the folder order produced by moving a folder."""
    if position not in ("before", "after"):
        raise ZulipValidationError(f"Invalid folder move position: {position!r}")
    _validate_channel_folder_assignment_id(target_id)
    _validate_channel_folder_assignment_id(reference_id)
    if target_id == reference_id:
        raise ZulipValidationError("Cannot move folder relative to itself")
    if target_id not in current_order:
        raise ZulipNotFoundError(f"Target folder id {target_id} not found")
    if reference_id not in current_order:
        raise ZulipNotFoundError(f"Reference folder id {reference_id} not found")

    new_order = [folder_id for folder_id in current_order if folder_id != target_id]
    insert_at = new_order.index(reference_id)
    if position == "after":
        insert_at += 1
    new_order.insert(insert_at, target_id)
    return new_order


def _resolve_single_channel_folder_token(
    token: str,
    folders: list[dict[str, Any]],
    *,
    allow_none: bool,
    bare_int_is_id: bool,
    option_name: str,
) -> int | None:
    """Resolve one folder token against an already-fetched folder list."""
    token = token.strip()
    if not token:
        raise ZulipValidationError(f"{option_name} must not be empty")
    if allow_none and token.casefold() == "none":
        return None

    id_lookup = False
    if token.casefold().startswith("id:"):
        suffix = token[3:].strip()
        id_lookup = True
    elif bare_int_is_id and token.isdigit():
        suffix = token
        id_lookup = True
    else:
        suffix = ""

    if id_lookup:
        try:
            wanted = int(suffix)
        except ValueError as exc:
            raise ZulipValidationError(f"id: prefix requires a numeric folder ID, got {suffix!r}") from exc
        if wanted <= 0:
            raise ZulipValidationError(f"id: prefix requires a positive folder ID, got {wanted}")
        for folder in folders:
            if folder["id"] == wanted:
                return wanted
        if bare_int_is_id and token.isdigit():
            raise ZulipNotFoundError(
                f"No channel folder with id {wanted}. If you meant a numeric folder ID, use 'id:{wanted}'."
            )
        raise ZulipNotFoundError(f"No channel folder with id {wanted}")

    target = token.casefold()
    matches = [folder for folder in folders if str(folder.get("name", "")).casefold() == target]
    if not matches:
        if token.isdigit():
            raise ZulipNotFoundError(
                f"No channel folder named {token!r}. If you meant a numeric folder ID, use 'id:{token}'."
            )
        raise ZulipNotFoundError(f"No channel folder named {token!r}")
    if len(matches) > 1:
        raise ZulipAmbiguityError(
            f"Channel folder name {token!r} matched {len(matches)} folders; use the id:NUM prefix to disambiguate",
            matches=[
                {"id": folder["id"], "name": folder["name"], "is_archived": folder["is_archived"]} for folder in matches
            ],
        )
    folder_id = matches[0]["id"]
    if not isinstance(folder_id, int):
        raise ZulipAPIError(f"Resolved folder missing numeric id: {matches[0]!r}")
    return folder_id


def resolve_channel_folder_reference(token: str, folders: list[dict[str, Any]]) -> int:
    """Resolve a folder move reference from name, ``id:N``, or bare ID."""
    folder_id = _resolve_single_channel_folder_token(
        token,
        folders,
        allow_none=False,
        bare_int_is_id=True,
        option_name="folder reference",
    )
    if folder_id is None:  # pragma: no cover - allow_none=False
        raise ZulipValidationError("folder reference must identify a folder")
    return folder_id


def resolve_channel_folder_token(client: Any, token: str) -> int | None:
    """Resolve a folder token for channel assignment.

    Accepts a case-insensitive folder name, ``id:N`` for explicit ID
    lookup, or ``none`` to clear the assignment. Numeric-looking names
    are treated as names; if absent, the error hints to use ``id:N``.
    """
    check_feature_level(client, FEATURE_LEVELS["channel-folders"], "channel-folders")
    folders = list_channel_folders(client, include_archived=True)
    return _resolve_single_channel_folder_token(
        token,
        folders,
        allow_none=True,
        bare_int_is_id=False,
        option_name="--folder",
    )
