# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Read-only Zulip detail projections for ``show`` commands."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from .channels import _fetch_streams, resolve_channel
from .errors import ZulipAmbiguityError, ZulipNotFoundError, ZulipValidationError
from .features import FEATURE_LEVELS, check_feature_level
from .folders import _fetch_channel_folders, _resolve_single_channel_folder_token
from .groups import SYSTEM_ROLE_DISPLAY_NAMES, _fetch_groups
from .users import IdMode, _fetch_users, _resolve_single_user

SettableStatus = Literal["via --flag", "via command", "not exposed", "no"]


@dataclass(frozen=True)
class SettableAnnotation:
    """Settable metadata attached to one displayed detail field."""

    status: SettableStatus
    setter: str | None = None
    notes: str | None = None

    def as_json(self) -> dict[str, str | None]:
        """Return the stable JSON annotation shape."""
        return {"status": self.status, "setter": self.setter, "notes": self.notes}


READ_ONLY = SettableAnnotation("no")

CHANNEL_GROUP_SETTING_FIELDS = {
    "can_subscribe_group",
    "can_remove_subscribers_group",
    "can_add_subscribers_group",
    "can_administer_channel_group",
    "can_send_message_group",
    "can_delete_any_message_group",
    "can_delete_own_message_group",
    "can_move_messages_out_of_channel_group",
    "can_move_messages_within_channel_group",
    "can_resolve_topics_group",
    "can_create_topic_group",
}

GROUP_SETTING_FIELDS = {
    "can_manage_group",
    "can_mention_group",
    "can_add_members_group",
    "can_join_group",
    "can_leave_group",
    "can_remove_members_group",
}

CHANNEL_ANNOTATIONS: dict[str, SettableAnnotation] = {
    "name": SettableAnnotation("via --flag", "--name"),
    "description": SettableAnnotation("via --flag", "--description"),
    "type": SettableAnnotation("via --flag", "--type", "derived from invite_only/is_web_public"),
    "invite_only": SettableAnnotation("via --flag", "--type"),
    "is_web_public": SettableAnnotation("via --flag", "--type"),
    "is_archived": SettableAnnotation("via command", "channel archive/unarchive"),
    "folder_id": SettableAnnotation("via --flag", "--folder", "clear with --folder-id 0"),
    "topics_policy": SettableAnnotation("via --flag", "--topic-policy"),
    "can_subscribe_group": SettableAnnotation("via --flag", "--allow-group"),
    "can_remove_subscribers_group": SettableAnnotation("via --flag", "--can-remove-subscribers-group"),
    "can_add_subscribers_group": SettableAnnotation("not exposed", None, "server-settable FL 342"),
    "can_administer_channel_group": SettableAnnotation("not exposed", None, "server-settable FL 325"),
    "can_send_message_group": SettableAnnotation("not exposed", None, "server-settable FL 333"),
    "can_delete_any_message_group": SettableAnnotation("not exposed", None, "server-settable FL 407"),
    "can_delete_own_message_group": SettableAnnotation("not exposed", None, "server-settable FL 407"),
    "can_move_messages_out_of_channel_group": SettableAnnotation("not exposed", None, "server-settable FL 396"),
    "can_move_messages_within_channel_group": SettableAnnotation("not exposed", None, "server-settable FL 396"),
    "can_resolve_topics_group": SettableAnnotation("not exposed", None, "server-settable FL 402"),
    "can_create_topic_group": SettableAnnotation("not exposed", None, "server-settable FL 441"),
    "message_retention_days": SettableAnnotation("not exposed", None, "server-settable retention policy"),
    "history_public_to_subscribers": SettableAnnotation("not exposed", None, "server-settable shared-history setting"),
    "default_push_notifications": SettableAnnotation("not exposed", None, "server-settable notification default"),
    "is_default": SettableAnnotation("not exposed", None, "server-settable default channel status"),
    "is_default_stream": SettableAnnotation("not exposed", None, "server-settable default channel status"),
}

GROUP_ANNOTATIONS: dict[str, SettableAnnotation] = {
    "id": READ_ONLY,
    "group_id": READ_ONLY,
    "name": SettableAnnotation("not exposed", None, "custom groups only"),
    "display_name": READ_ONLY,
    "description": SettableAnnotation("not exposed"),
    "is_system_group": READ_ONLY,
    "type": READ_ONLY,
    "deactivated": SettableAnnotation("not exposed"),
    "date_created": READ_ONLY,
    "creator_id": READ_ONLY,
    "members": SettableAnnotation("not exposed"),
    "direct_subgroup_ids": SettableAnnotation("not exposed"),
    **{field: SettableAnnotation("not exposed") for field in GROUP_SETTING_FIELDS},
}

USER_ANNOTATIONS: dict[str, SettableAnnotation] = {
    "user_id": READ_ONLY,
    "full_name": SettableAnnotation("not exposed"),
    "email": SettableAnnotation("not exposed", None, "server setter new_email"),
    "delivery_email": SettableAnnotation("not exposed", None, "server setter new_email"),
    "role": SettableAnnotation("not exposed"),
    "role_label": READ_ONLY,
    "is_owner": SettableAnnotation("not exposed", None, "derived from role"),
    "is_admin": SettableAnnotation("not exposed", None, "derived from role"),
    "is_guest": SettableAnnotation("not exposed", None, "derived from role"),
    "is_bot": READ_ONLY,
    "bot_type": READ_ONLY,
    "bot_owner_id": READ_ONLY,
    "is_active": SettableAnnotation("not exposed"),
    "is_deleted": READ_ONLY,
    "date_joined": READ_ONLY,
    "timezone": SettableAnnotation("not exposed", None, "server setter timezone"),
    "avatar_url": READ_ONLY,
    "avatar_version": READ_ONLY,
    "is_imported_stub": READ_ONLY,
    "profile_data": SettableAnnotation("not exposed"),
}

FOLDER_ANNOTATIONS: dict[str, SettableAnnotation] = {
    "id": READ_ONLY,
    "name": SettableAnnotation("via --flag", "--name"),
    "description": SettableAnnotation("via --flag", "--description"),
    "rendered_description": READ_ONLY,
    "order": SettableAnnotation("via command", "folder move"),
    "is_archived": SettableAnnotation("via command", "folder archive/unarchive"),
    "date_created": READ_ONLY,
    "creator_id": READ_ONLY,
    "channels": READ_ONLY,
}


def annotation_for(field: str, registry: dict[str, SettableAnnotation]) -> SettableAnnotation:
    """Return an annotation for ``field``, defaulting to read-only."""
    return registry.get(field, READ_ONLY)


def json_annotations(fields: list[str], registry: dict[str, SettableAnnotation]) -> dict[str, dict[str, str | None]]:
    """Return stable JSON annotations for ``fields``."""
    return {field: annotation_for(field, registry).as_json() for field in fields}


def public_detail_payload(detail: dict[str, Any]) -> dict[str, Any]:
    """Strip internal display-only keys before JSON emission."""
    return {key: value for key, value in detail.items() if not key.startswith("_")}


def channel_type_from_stream(stream: dict[str, Any]) -> str:
    """Derive the human channel type from Zulip's raw flags."""
    if stream.get("is_web_public"):
        return "web-public"
    if stream.get("invite_only"):
        return "private"
    return "public"


def role_label(role: Any) -> str:
    """Return the human label for a Zulip role value."""
    return {
        100: "owner",
        200: "administrator",
        300: "moderator",
        400: "member",
        600: "guest",
    }.get(role, f"unknown ({role})")


def user_ref(user: dict[str, Any] | None, user_id: int | None = None) -> dict[str, Any] | None:
    """Return the stable compact user reference shape."""
    if user is None:
        if user_id is None:
            return None
        return {"user_id": user_id, "full_name": None, "email": None}
    raw_id = user.get("user_id", user_id)
    return {
        "user_id": raw_id,
        "full_name": user.get("full_name"),
        "email": user.get("delivery_email") or user.get("email"),
    }


def group_display_name(group: dict[str, Any]) -> str:
    """Return the human display name for a raw Zulip group."""
    name = str(group.get("name", ""))
    if group.get("is_system_group", False) or name.startswith("role:"):
        return SYSTEM_ROLE_DISPLAY_NAMES.get(name, name)
    return name


def group_ref(group: dict[str, Any] | None, group_id: int | None = None) -> dict[str, Any] | None:
    """Return the stable compact group reference shape."""
    if group is None:
        if group_id is None:
            return None
        return {"group_id": group_id, "name": None, "type": None}
    raw_id = group.get("id", group.get("group_id", group_id))
    group_type = "system" if group.get("is_system_group", False) else "custom"
    return {"group_id": raw_id, "name": group_display_name(group), "type": group_type}


def _user_index(users: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {user["user_id"]: user for user in users if isinstance(user.get("user_id"), int)}


def _group_index(groups: list[dict[str, Any]]) -> dict[int, dict[str, Any]]:
    return {group["id"]: group for group in groups if isinstance(group.get("id"), int)}


def _display_user_id(user_id: Any, users_by_id: dict[int, dict[str, Any]] | None) -> str:
    if not isinstance(user_id, int) or isinstance(user_id, bool):
        return str(user_id)
    if users_by_id is None:
        return str(user_id)
    user = users_by_id.get(user_id)
    if user is None:
        return f"unknown user {user_id}"
    name = user.get("full_name") or user.get("email") or user_id
    return f"{name} (id={user_id})"


def _display_group_id(group_id: Any, groups_by_id: dict[int, dict[str, Any]] | None) -> str:
    if not isinstance(group_id, int) or isinstance(group_id, bool):
        return str(group_id)
    if groups_by_id is None:
        return str(group_id)
    group = groups_by_id.get(group_id)
    if group is None:
        return f"unknown group {group_id}"
    return f"{group_display_name(group)} (id={group_id})"


def group_setting_display(
    value: Any,
    *,
    users_by_id: dict[int, dict[str, Any]] | None = None,
    groups_by_id: dict[int, dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Render Zulip group-setting values in integer and object forms."""
    direct_members: list[int] = []
    direct_subgroups: list[int] = []
    if isinstance(value, int) and not isinstance(value, bool):
        direct_subgroups = [value]
    elif isinstance(value, dict):
        raw_members = value.get("direct_members", [])
        raw_subgroups = value.get("direct_subgroups", [])
        if isinstance(raw_members, list):
            direct_members = [v for v in raw_members if isinstance(v, int) and not isinstance(v, bool)]
        if isinstance(raw_subgroups, list):
            direct_subgroups = [v for v in raw_subgroups if isinstance(v, int) and not isinstance(v, bool)]
    parts = [_display_user_id(uid, users_by_id) for uid in direct_members]
    parts.extend(_display_group_id(gid, groups_by_id) for gid in direct_subgroups)
    display = ", ".join(parts) if parts else str(value)
    result: dict[str, Any] = {
        "raw": value,
        "direct_members": direct_members,
        "direct_subgroups": direct_subgroups,
        "display": display,
    }
    if users_by_id is not None:
        result["resolved_members"] = [user_ref(users_by_id.get(uid), uid) for uid in direct_members]
    if groups_by_id is not None:
        result["resolved_groups"] = [group_ref(groups_by_id.get(gid), gid) for gid in direct_subgroups]
    return result


def _group_setting_has_direct_members(value: Any) -> bool:
    """Return True when a group-setting value embeds direct user IDs."""
    if not isinstance(value, dict):
        return False
    raw_members = value.get("direct_members", [])
    return isinstance(raw_members, list) and any(
        isinstance(uid, int) and not isinstance(uid, bool) for uid in raw_members
    )


def _group_setting_has_group_refs(value: Any) -> bool:
    """Return True when a group-setting value embeds group IDs."""
    if isinstance(value, int) and not isinstance(value, bool):
        return True
    if not isinstance(value, dict):
        return False
    raw_subgroups = value.get("direct_subgroups", [])
    return isinstance(raw_subgroups, list) and any(
        isinstance(gid, int) and not isinstance(gid, bool) for gid in raw_subgroups
    )


def _resolve_group_by_show_target(
    groups: list[dict[str, Any]],
    *,
    group_name: str | None = None,
    group_id: int | None = None,
) -> dict[str, Any]:
    if (group_name is None) == (group_id is None):
        raise ZulipValidationError("Exactly one group target is required")
    if group_id is not None:
        for group in groups:
            if group.get("id") == group_id:
                return group
        raise ZulipNotFoundError(f"No user group with id {group_id}")
    assert group_name is not None
    target = group_name.casefold()
    matches = [
        group
        for group in groups
        if group_display_name(group).casefold() == target or str(group.get("name", "")).casefold() == target
    ]
    if len(matches) > 1:
        raise ZulipAmbiguityError(
            f"Group name {group_name!r} matched {len(matches)} groups; use --group-id to disambiguate",
            matches=[{"group_id": group.get("id"), "name": group_display_name(group)} for group in matches],
        )
    if matches:
        return matches[0]
    if group_name.isdigit():
        raise ZulipNotFoundError(
            f"No user group named {group_name!r}. If you meant a numeric group ID, use --group-id."
        )
    raise ZulipNotFoundError(f"No user group named {group_name!r}")


def get_channel_detail(
    client: Any,
    *,
    name: str | None = None,
    channel_id: int | None = None,
    include_archived: bool = False,
    resolve: bool = True,
) -> dict[str, Any]:
    """Return complete raw channel detail plus annotations/resolution."""
    stream = resolve_channel(client, name=name, channel_id=channel_id, include_archived=include_archived)
    derived = {"type": channel_type_from_stream(stream)}
    resolved: dict[str, Any] = {}
    display_fields: dict[str, Any] = {"type": derived["type"]}

    group_fields = [field for field in stream if field in CHANNEL_GROUP_SETTING_FIELDS]
    if resolve:
        users_by_id: dict[int, dict[str, Any]] | None = None
        groups_by_id: dict[int, dict[str, Any]] | None = None
        if group_fields:
            if any(_group_setting_has_direct_members(stream[field]) for field in group_fields):
                users_by_id = _user_index(_fetch_users(client))
            if any(_group_setting_has_group_refs(stream[field]) for field in group_fields):
                groups_by_id = _group_index(_fetch_groups(client))
            resolved["groups"] = {}
            for field in group_fields:
                rendered = group_setting_display(stream[field], users_by_id=users_by_id, groups_by_id=groups_by_id)
                resolved["groups"][field] = rendered
                display_fields[field] = rendered["display"]
        creator_id = stream.get("creator_id")
        if isinstance(creator_id, int) and not isinstance(creator_id, bool):
            if users_by_id is None:
                users_by_id = _user_index(_fetch_users(client))
            resolved["creator"] = user_ref(users_by_id.get(creator_id), creator_id)
            display_fields["creator_id"] = _display_user_id(creator_id, users_by_id)
        folder_id = stream.get("folder_id")
        if isinstance(folder_id, int) and not isinstance(folder_id, bool):
            folders = _fetch_channel_folders(client, include_archived=True)
            folder = next((folder for folder in folders if folder.get("id") == folder_id), None)
            resolved["folder"] = {"id": folder_id, "name": folder.get("name") if folder else None}
            display_fields["folder_id"] = (
                f"{folder.get('name')} (id={folder_id})" if folder else f"unknown folder {folder_id}"
            )
    else:
        for field in group_fields:
            display_fields[field] = stream[field]

    fields = ["type", *list(stream.keys())]
    return {
        "channel": stream,
        "derived": derived,
        "resolved": resolved,
        "annotations": json_annotations(fields, CHANNEL_ANNOTATIONS),
        "_display_fields": display_fields,
        "_raw_key": "channel",
    }


def get_group_detail(
    client: Any,
    *,
    group_name: str | None = None,
    group_id: int | None = None,
    resolve: bool = True,
) -> dict[str, Any]:
    """Return complete raw user-group detail plus annotations/resolution."""
    groups = _fetch_groups(client)
    group = _resolve_group_by_show_target(groups, group_name=group_name, group_id=group_id)
    display_name = group_display_name(group)
    group_type = "system" if group.get("is_system_group", False) else "custom"
    members = group.get("members", []) if isinstance(group.get("members", []), list) else []
    derived = {"display_name": display_name, "type": group_type, "member_count": len(members)}
    resolved: dict[str, Any] = {}
    display_fields: dict[str, Any] = {"display_name": display_name, "type": group_type}
    users_by_id: dict[int, dict[str, Any]] | None = None
    groups_by_id: dict[int, dict[str, Any]] | None = None
    group_setting_values = [group[field] for field in GROUP_SETTING_FIELDS if field in group]

    if resolve:
        creator_id = group.get("creator_id")
        needs_group_setting_users = any(_group_setting_has_direct_members(value) for value in group_setting_values)
        if members or isinstance(creator_id, int) or needs_group_setting_users:
            users_by_id = _user_index(_fetch_users(client))
        resolved["members"] = (
            [user_ref(users_by_id.get(uid), uid) for uid in members if isinstance(uid, int)]
            if users_by_id is not None
            else []
        )
        if isinstance(creator_id, int) and not isinstance(creator_id, bool) and users_by_id is not None:
            resolved["creator"] = user_ref(users_by_id.get(creator_id), creator_id)
            display_fields["creator_id"] = _display_user_id(creator_id, users_by_id)
        subgroup_ids = group.get("direct_subgroup_ids", [])
        if isinstance(subgroup_ids, list) and subgroup_ids:
            groups_by_id = _group_index(groups)
            resolved["direct_subgroups"] = [
                group_ref(groups_by_id.get(gid), gid) for gid in subgroup_ids if isinstance(gid, int)
            ]
            display_fields["direct_subgroup_ids"] = ", ".join(
                _display_group_id(gid, groups_by_id) for gid in subgroup_ids
            )
    for field in GROUP_SETTING_FIELDS:
        if field in group:
            if resolve:
                if groups_by_id is None and _group_setting_has_group_refs(group[field]):
                    groups_by_id = _group_index(groups)
                rendered = group_setting_display(group[field], users_by_id=users_by_id, groups_by_id=groups_by_id)
                display_fields[field] = rendered["display"]
                resolved.setdefault("groups", {})[field] = rendered
            else:
                display_fields[field] = group[field]

    fields = [*list(group.keys()), "display_name", "type"]
    return {
        "group": group,
        "derived": derived,
        "resolved": resolved,
        "annotations": json_annotations(fields, GROUP_ANNOTATIONS),
        "_display_fields": display_fields,
        "_raw_key": "group",
    }


def get_user_detail(client: Any, ident: str, *, mode: IdMode, resolve: bool = True) -> dict[str, Any]:
    """Return complete raw user detail plus annotations/resolution."""
    users = _fetch_users(client, include_custom_profile_fields=True)
    user = _resolve_single_user(ident, users, mode=mode)
    user_id = user.get("user_id")
    derived = {"role_label": role_label(user.get("role"))}
    resolved: dict[str, Any] = {}
    display_fields: dict[str, Any] = {"role_label": derived["role_label"]}
    users_by_id = _user_index(users)
    if resolve:
        bot_owner_id = user.get("bot_owner_id")
        if isinstance(bot_owner_id, int) and not isinstance(bot_owner_id, bool):
            resolved["bot_owner"] = user_ref(users_by_id.get(bot_owner_id), bot_owner_id)
            display_fields["bot_owner_id"] = _display_user_id(bot_owner_id, users_by_id)
        else:
            resolved["bot_owner"] = None
        groups = _fetch_groups(client)
        memberships = []
        if isinstance(user_id, int):
            for group in groups:
                members = group.get("members", [])
                if isinstance(members, list) and user_id in members:
                    memberships.append(group_ref(group))
        resolved["groups"] = memberships
    fields = [*list(user.keys()), "role_label"]
    return {
        "user": user,
        "derived": derived,
        "resolved": resolved,
        "annotations": json_annotations(fields, USER_ANNOTATIONS),
        "_display_fields": display_fields,
        "_raw_key": "user",
    }


def _resolve_folder_for_show(token: str, folders: list[dict[str, Any]]) -> dict[str, Any]:
    folder_id = _resolve_single_channel_folder_token(
        token,
        folders,
        allow_none=False,
        bare_int_is_id=False,
        option_name="folder reference",
    )
    for folder in folders:
        if folder.get("id") == folder_id:
            return folder
    raise ZulipNotFoundError(f"No channel folder with id {folder_id}")


def get_folder_detail(client: Any, token: str, *, resolve: bool = True) -> dict[str, Any]:
    """Return complete raw channel-folder detail plus annotations/resolution."""
    check_feature_level(client, FEATURE_LEVELS["channel-folders"], "channel-folders")
    folders = _fetch_channel_folders(client, include_archived=True)
    folder = _resolve_folder_for_show(token, folders)
    resolved: dict[str, Any] = {}
    display_fields: dict[str, Any] = {}
    if resolve:
        creator_id = folder.get("creator_id")
        if isinstance(creator_id, int) and not isinstance(creator_id, bool):
            users_by_id = _user_index(_fetch_users(client))
            resolved["creator"] = user_ref(users_by_id.get(creator_id), creator_id)
            display_fields["creator_id"] = _display_user_id(creator_id, users_by_id)
        folder_id = folder.get("id")
        streams = _fetch_streams(client, include_archived=True)
        channels = []
        for stream in streams:
            if stream.get("folder_id") == folder_id:
                channels.append(
                    {
                        "stream_id": stream.get("stream_id"),
                        "name": stream.get("name"),
                        "type": channel_type_from_stream(stream),
                        "is_archived": bool(stream.get("is_archived", False)),
                    }
                )
        resolved["channels"] = channels
    fields = list(folder.keys())
    return {
        "folder": folder,
        "resolved": resolved,
        "annotations": json_annotations(fields, FOLDER_ANNOTATIONS),
        "_display_fields": display_fields,
        "_raw_key": "folder",
    }
