<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- tables document exact CLI/schema names -->

# Data Model: Zulip Show Commands

## Shared Concepts

### SettableAnnotation

Every human detail row includes a settable marker.

| Field | Type | Description |
| --- | --- | --- |
| `status` | `str` | `via --flag`, `via command`, `not exposed`, or `no` |
| `setter` | `str \| null` | CLI flag or command that writes this field, when exposed |
| `notes` | `str \| null` | Feature-level or implementation notes |

**Rules**:

- `via --flag` means the current lftools-uv CLI can set the field.
- `via command` means the current lftools-uv CLI can set the field through a
  subcommand rather than a single option flag.
- `not exposed` means the Zulip API can set the field but no CLI write flag or
  command is currently available.
- `no` means the field is server-derived, read-only, or not in scope for this
  CLI.
- JSON output preserves annotations as an object keyed by field name. The
  annotation value MUST include exactly `status`, `setter`, and `notes`; it
  MUST NOT repeat the field name because the object key already carries it.
  `setter` and `notes` are emitted as `null` when absent.

### GroupSettingDisplay

Represents Zulip group-setting values used by channel and group permissions.

| Field | Type | Description |
| --- | --- | --- |
| `raw` | `int \| object` | Original value from Zulip |
| `direct_members` | `list[int]` | User IDs embedded directly in object form |
| `direct_subgroups` | `list[int]` | Group IDs embedded in object form or the single integer ID |
| `resolved_members` | `list[UserRef]` | Present only when resolution is enabled |
| `resolved_groups` | `list[GroupRef]` | Present only when resolution is enabled |
| `display` | `str` | Human-readable value used in tables |

**Rules**:

- Bare integer values are treated as one group ID.
- Object values MUST support `direct_members` and `direct_subgroups` arrays.
- Unknown IDs remain visible as raw IDs instead of being dropped.
- The `Nobody` system role group is rendered with the display-name mapping from
  `groups.py` when present.

## Entities

### ChannelDetail

Represents a raw Zulip stream object plus derived and resolved details.

| Field | Type | Description | Settable status |
| --- | --- | --- | --- |
| `stream_id` | `int` | Channel ID | no |
| `name` | `str` | Channel name | via --flag; setter `--name` |
| `description` | `str` | Markdown channel description | via --flag; setter `--description` |
| `rendered_description` | `str` | HTML-rendered description, if returned | no |
| `type` | `str` | Derived `public`, `private`, or `web-public` | via --flag; setter `--type` |
| `invite_only` | `bool` | Raw private-channel flag | via --flag; setter `--type` |
| `is_web_public` | `bool` | Raw web-public flag | via --flag; setter `--type` |
| `is_archived` | `bool` | Archived state | via command |
| `folder_id` | `int \| null` | Channel folder assignment | via --flag; setter `--folder`, clear via `--folder-id 0` |
| `topics_policy` | `str` | Raw Zulip topic policy | via --flag; setter `--topic-policy` |
| `can_subscribe_group` | `GroupSettingDisplay` | Who can self-subscribe | via --flag; setter `--allow-group` |
| `can_remove_subscribers_group` | `GroupSettingDisplay` | Who can remove subscribers | via --flag; setter `--can-remove-subscribers-group` |
| `can_add_subscribers_group` | `GroupSettingDisplay` | Who can add subscribers | not exposed |
| `can_administer_channel_group` | `GroupSettingDisplay` | Who can administer channel | not exposed |
| `can_send_message_group` | `GroupSettingDisplay` | Who can post messages | not exposed |
| `can_delete_any_message_group` | `GroupSettingDisplay` | Who can delete any message | not exposed |
| `can_delete_own_message_group` | `GroupSettingDisplay` | Who can delete own messages | not exposed |
| `can_move_messages_out_of_channel_group` | `GroupSettingDisplay` | Who can move messages out | not exposed |
| `can_move_messages_within_channel_group` | `GroupSettingDisplay` | Who can move messages within | not exposed |
| `can_resolve_topics_group` | `GroupSettingDisplay` | Who can resolve topics | not exposed |
| `can_create_topic_group` | `GroupSettingDisplay` | Who can create topics | not exposed |
| `message_retention_days` | `int \| null` | Retention policy | not exposed |
| `history_public_to_subscribers` | `bool` | Shared-history behavior | not exposed |
| `date_created` | `int` | Creation timestamp | no |
| `creator_id` | `int \| null` | Creator user ID | no |
| `first_message_id` | `int \| null` | First message ID | no |
| `stream_post_policy` | `int` | Deprecated posting policy | no |
| `is_announcement_only` | `bool` | Deprecated announcement-only flag | no |
| `subscriber_count` | `int` | Subscriber count hint | no |
| `default_push_notifications` | `bool` | Default mobile push setting | not exposed |
| `is_recently_active` | `bool` | Recent activity marker | no |
| `stream_weekly_traffic` | `int \| null` | Estimated weekly traffic | no |
| `is_default` | `bool` | Default channel marker, when returned | not exposed |

Additional server-returned fields MUST be rendered using the same annotation
model. The raw JSON object remains authoritative.

### GroupDetail

Represents a raw Zulip user-group object plus member and permission displays.

| Field | Type | Description | Settable status |
| --- | --- | --- | --- |
| `id` | `int` | Raw Zulip group ID | no |
| `group_id` | `int` | Alias used by existing CLI JSON | no |
| `name` | `str` | Raw API name | not exposed; custom groups only |
| `display_name` | `str` | System-role display name or custom name | no |
| `description` | `str` | Human description | not exposed |
| `is_system_group` | `bool` | Built-in role group marker | no |
| `type` | `str` | Derived `system` or `custom` | no |
| `deactivated` | `bool` | Group deactivation status | not exposed |
| `date_created` | `int \| null` | Creation timestamp | no |
| `creator_id` | `int \| null` | Creator user ID | no |
| `creator` | `UserRef \| null` | Derived creator display when resolved | no |
| `members` | `list[int]` | Direct member user IDs | not exposed |
| `direct_subgroup_ids` | `list[int]` | Direct subgroup IDs | not exposed |
| `can_manage_group` | `GroupSettingDisplay` | Who can manage group | not exposed |
| `can_mention_group` | `GroupSettingDisplay` | Who can mention group | not exposed |
| `can_add_members_group` | `GroupSettingDisplay` | Who can add members | not exposed |
| `can_join_group` | `GroupSettingDisplay` | Who can join group | not exposed |
| `can_leave_group` | `GroupSettingDisplay` | Who can leave group | not exposed |
| `can_remove_members_group` | `GroupSettingDisplay` | Who can remove members | not exposed |

Member display rows are derived from `members` and the users list when
resolution is enabled. Recursive expansion of `direct_subgroup_ids` is out of
scope.

### UserDetail

Represents a raw Zulip user object plus role label and optional group
membership.

| Field | Type | Description | Settable status |
| --- | --- | --- | --- |
| `user_id` | `int` | Raw user ID | no |
| `full_name` | `str` | Display name | not exposed |
| `email` | `str` | API email address; server setter `new_email` | not exposed |
| `delivery_email` | `str \| null` | Real email, if visible; server setter `new_email` | not exposed |
| `role` | `int` | Raw Zulip role value | not exposed |
| `role_label` | `str` | owner/administrator/moderator/member/guest | no |
| `is_owner` | `bool` | Owner marker | not exposed; derived from role |
| `is_admin` | `bool` | Administrator marker | not exposed; derived from role |
| `is_guest` | `bool` | Guest marker | not exposed; derived from role |
| `is_bot` | `bool` | Bot marker | no |
| `bot_type` | `int \| null` | Bot type enum | no |
| `bot_owner_id` | `int \| null` | Bot owner user ID | no |
| `bot_owner` | `UserRef \| null` | Derived bot owner display when resolved | no |
| `is_active` | `bool` | Active account marker | not exposed |
| `is_deleted` | `bool` | Deleted account marker, when present | no |
| `date_joined` | `str` | Account join timestamp | no |
| `timezone` | `str` | IANA time zone; server setter `timezone` | not exposed |
| `avatar_url` | `str \| null` | Avatar URL | no |
| `avatar_version` | `int` | Avatar cache-busting version | no |
| `is_imported_stub` | `bool` | Imported stub marker | no |
| `profile_data` | `object` | Custom profile fields | not exposed |
| `groups` | `list[GroupRef]` | Derived membership when resolved | no |

Role mapping uses Zulip's documented values: 100 owner, 200 administrator,
300 moderator, 400 member, 600 guest.

### FolderDetail

Represents a raw Zulip channel folder plus resolved creator and assigned
channels.

| Field | Type | Description | Settable status |
| --- | --- | --- | --- |
| `id` | `int` | Folder ID | no |
| `name` | `str` | Folder name | via --flag; setter `--name` |
| `description` | `str` | Markdown description | via --flag; setter `--description` |
| `rendered_description` | `str` | HTML-rendered description | no |
| `order` | `int \| null` | Folder order; FL 414+ | via command `folder move` |
| `is_archived` | `bool` | Archived marker | via command |
| `date_created` | `int \| null` | Creation timestamp | no |
| `creator_id` | `int \| null` | Creator user ID | no |
| `channels` | `list[ChannelRef]` | Derived assigned channels | no |

`channels` is derived by listing streams and filtering on `folder_id` when
resolution is enabled. It is omitted with `--no-resolve`.

## Relationships

```text
ChannelDetail ── folder_id ──▶ FolderDetail
ChannelDetail ── creator_id ─▶ UserDetail
ChannelDetail ── group settings ─▶ GroupDetail/UserDetail refs
GroupDetail ─── creator_id ─▶ UserDetail refs
GroupDetail ─── members ─────▶ UserDetail refs
GroupDetail ─── direct_subgroup_ids ─▶ GroupDetail refs
UserDetail ─── bot_owner_id ─▶ UserDetail refs
UserDetail ─── derived membership ─▶ GroupDetail refs
FolderDetail ─ channels ─────▶ ChannelDetail refs
```

## Validation Rules

- Show commands are read-only and MUST NOT send mutation requests.
- Targeting constraints are enforced before target resolution.
- `--no-resolve` skips derived lookup sections but not the lookup necessary to
  locate the target by name.
- All raw IDs remain available in JSON even when human output resolves names.
