# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Presentation helpers for Zulip ``show`` commands."""

from __future__ import annotations

from typing import Any

import typer

from lftools_uv.typer_apps.zulip.helpers import emit_table


def _stringify(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (list, dict)):
        return str(value)
    return str(value)


def render_detail_fields(detail: dict[str, Any], raw_key: str) -> None:
    """Render the primary ``Field | Value | Settable | Notes`` table."""
    raw = detail[raw_key]
    annotations = detail["annotations"]
    display_fields = detail.get("_display_fields", {})
    rows: list[list[Any]] = []
    derived = detail.get("derived", {})
    for field, value in derived.items():
        annotation = annotations.get(field, {"status": "no", "setter": None, "notes": None})
        notes = annotation.get("notes") or ""
        setter = annotation.get("setter")
        if setter and not notes:
            notes = f"setter {setter}"
        elif setter:
            notes = f"setter {setter}; {notes}"
        rows.append([field, _stringify(display_fields.get(field, value)), annotation["status"], notes])
    for field, value in raw.items():
        annotation = annotations.get(field, {"status": "no", "setter": None, "notes": None})
        notes = annotation.get("notes") or ""
        setter = annotation.get("setter")
        if setter and not notes:
            notes = f"setter {setter}"
        elif setter:
            notes = f"setter {setter}; {notes}"
        rows.append([field, _stringify(display_fields.get(field, value)), annotation["status"], notes])
    emit_table(rows, headers=("Field", "Value", "Settable", "Notes"))


def render_group_sections(detail: dict[str, Any], *, resolve: bool) -> None:
    """Render members and direct subgroups for ``group show``."""
    group = detail["group"]
    resolved = detail.get("resolved", {})
    typer.echo("\nMembers")
    if resolve:
        rows = [
            [member.get("full_name") or "", member.get("email") or "", member.get("user_id")]
            for member in resolved.get("members", [])
        ]
        emit_table(rows, headers=("Full Name", "Email", "User ID"))
    else:
        emit_table([[uid] for uid in group.get("members", [])], headers=("User ID",))
    subgroup_ids = group.get("direct_subgroup_ids", [])
    if subgroup_ids or resolved.get("direct_subgroups"):
        typer.echo("\nDirect Subgroups")
        if resolve:
            rows = [
                [subgroup.get("name") or "", subgroup.get("group_id"), subgroup.get("type") or ""]
                for subgroup in resolved.get("direct_subgroups", [])
            ]
            emit_table(rows, headers=("Name", "Group ID", "Type"))
        else:
            emit_table([[gid] for gid in subgroup_ids], headers=("Group ID",))


def render_user_sections(detail: dict[str, Any], *, resolve: bool) -> None:
    """Render profile data and memberships for ``user show``."""
    profile = detail["user"].get("profile_data")
    if isinstance(profile, dict) and profile:
        typer.echo("\nProfile Fields")
        rows = []
        for field_id, data in profile.items():
            if isinstance(data, dict):
                rows.append([field_id, data.get("value", ""), data.get("rendered_value", "")])
            else:
                rows.append([field_id, data, ""])
        emit_table(rows, headers=("Field ID", "Value", "Rendered Value"))
    if resolve:
        typer.echo("\nGroups")
        rows = [
            [group.get("name") or "", group.get("group_id"), group.get("type") or ""]
            for group in detail.get("resolved", {}).get("groups", [])
        ]
        emit_table(rows, headers=("Name", "Group ID", "Type"))


def render_folder_sections(detail: dict[str, Any], *, resolve: bool) -> None:
    """Render assigned channels for ``folder show``."""
    if not resolve:
        return
    typer.echo("\nAssigned Channels")
    rows = [
        [
            channel.get("name") or "",
            channel.get("stream_id"),
            channel.get("type") or "",
            "yes" if channel.get("is_archived") else "no",
        ]
        for channel in detail.get("resolved", {}).get("channels", [])
    ]
    emit_table(rows, headers=("Name", "Channel ID", "Type", "Archived"))
