<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- tables preserve exact Zulip field names -->

# Research: Zulip Show Commands

## Field Inventory: Channels

**Source**: Zulip Get channel by ID and Get all channels documentation:
<https://zulip.com/api/get-stream-by-id> and
<https://zulip.com/api/get-streams>.

The implementation should use the raw stream dict returned by the existing
`resolve_channel()` helper. `_normalize_channel()` is too lossy for show output:
it keeps only `stream_id`, `name`, `description`, derived `type`,
`subscriber_count`, and `is_archived`.

| Field | API notes | Feature level |
| --- | --- | --- |
| `stream_id` | Unique channel ID | baseline |
| `name` | Channel name | baseline |
| `is_archived` | Archived marker | FL 315 on this endpoint |
| `description` | Markdown description | baseline |
| `date_created` | UNIX timestamp | FL 30 |
| `creator_id` | Creator user ID or null | FL 254 |
| `invite_only` | Private-channel flag | baseline |
| `rendered_description` | HTML description | baseline |
| `is_web_public` | Unauthenticated web access flag | Zulip 2.1.0 |
| `stream_post_policy` | Deprecated posting policy | FL 1; deprecated FL 333 |
| `message_retention_days` | Retention days, null, or -1 | FL 17 |
| `default_push_notifications` | Default mobile push setting | FL 507 |
| `history_public_to_subscribers` | Shared history flag | baseline |
| `topics_policy` | Topic policy string | FL 392; `empty_topic_only` FL 404 |
| `first_message_id` | First message ID or null | Zulip 2.1.0 |
| `folder_id` | Channel folder ID or null | FL 389 |
| `is_recently_active` | Recent activity marker | FL 323 |
| `is_announcement_only` | Deprecated announcement-only flag | FL 1 |
| `can_add_subscribers_group` | Add-subscriber permission | FL 342 |
| `can_remove_subscribers_group` | Remove-subscriber permission | FL 142; object form FL 320; current update flag gate uses FL 161 |
| `can_administer_channel_group` | Channel administration permission | FL 325 |
| `can_delete_any_message_group` | Delete any message permission | FL 407 |
| `can_delete_own_message_group` | Delete own message permission | FL 407 |
| `can_move_messages_out_of_channel_group` | Move messages out permission | FL 396 |
| `can_move_messages_within_channel_group` | Move messages within permission | FL 396 |
| `can_send_message_group` | Send-message permission | FL 333 |
| `can_subscribe_group` | Self-subscribe permission | FL 357 |
| `can_resolve_topics_group` | Resolve topics permission | FL 402 |
| `can_create_topic_group` | Create topics permission | FL 441 |
| `subscriber_count` | Subscriber count hint | FL 394 |
| `stream_weekly_traffic` | Estimated weekly messages | FL 199 |
| `is_default` | Default channel marker, only when requested | endpoint-dependent |

### Channel Settable Annotations

| Field | Annotation |
| --- | --- |
| `name` | via `--name` |
| `description` | via `--description` |
| `type`, `invite_only`, `is_web_public` | via `--type` |
| `topics_policy` | via `--topic-policy` |
| `can_subscribe_group` | via `--allow-group` |
| `can_remove_subscribers_group` | via `--can-remove-subscribers-group` |
| `folder_id` | via `--folder` |
| `is_archived` | via `channel archive` / `channel unarchive` |
| `can_add_subscribers_group` | not exposed; API settable at FL 342 |
| `can_administer_channel_group` | not exposed; API settable at FL 325 |
| `can_send_message_group` | not exposed; API settable at FL 333 |
| other server fields | no, unless future implementation exposes them |

## Field Inventory: Groups

**Source**: Zulip Get user groups documentation:
<https://zulip.com/api/get-user-groups>.

The implementation should use raw dicts from `_fetch_groups()`. Existing
`_normalize_group()` intentionally collapses `members` to `member_count`.

| Field | API notes | Feature level |
| --- | --- | --- |
| `id` | User group ID | baseline |
| `name` | API name; system groups use `role:` names | baseline |
| `description` | Human description | baseline |
| `date_created` | Creation timestamp or null | FL 292 |
| `creator_id` | Creator user ID or null | FL 292 |
| `members` | Direct member user IDs | baseline; deactivated users excluded at FL 303 |
| `direct_subgroup_ids` | Direct subgroup IDs | FL 131 |
| `is_system_group` | System group marker | FL 93 |
| `can_add_members_group` | Add-members permission | FL 305 |
| `can_join_group` | Join permission | FL 301 |
| `can_leave_group` | Leave permission | FL 308 |
| `can_manage_group` | Manage permission | FL 283 |
| `can_mention_group` | Mention permission | FL 191; object form FL 258 |
| `can_remove_members_group` | Remove-members permission | FL 324 |
| `deactivated` | Deactivated group marker | FL 290 |

System role groups should reuse the `SYSTEM_ROLE_GROUPS` and
`SYSTEM_ROLE_DISPLAY_NAMES` mappings from `groups.py`, covering Owners,
Administrators, Moderators, Full Members, Members, Everyone, and Nobody.

## Field Inventory: Users

**Source**: Zulip Get all users documentation:
<https://zulip.com/api/get-users>.

The existing `_fetch_users()` requests `include_custom_profile_fields=False` for
list output. User show should fetch or request raw user objects with custom
profile fields included so `profile_data` is available.

| Field | API notes | Feature level |
| --- | --- | --- |
| `user_id` | Unique user ID | baseline |
| `delivery_email` | Real email or null | always present FL 163+ |
| `email` | API email address | baseline |
| `full_name` | Display name | baseline |
| `date_joined` | Join timestamp string | changed FL 475 |
| `is_active` | Deactivation marker | baseline |
| `is_owner` | Owner marker | FL 8 |
| `is_admin` | Administrator marker | baseline |
| `is_guest` | Guest marker | baseline |
| `is_bot` | Bot marker | baseline |
| `bot_type` | Bot type enum or null | baseline |
| `bot_owner_id` | Bot owner user ID or null | FL 1 |
| `role` | 100 owner, 200 admin, 300 moderator, 400 member, 600 guest | FL 59 |
| `timezone` | IANA time zone | baseline |
| `avatar_url` | Avatar URL or null | optional behavior FL 18; visibility changes FL 163 |
| `avatar_version` | Avatar version | baseline |
| `is_imported_stub` | Imported stub marker | FL 433 |
| `is_deleted` | Deleted marker when true | FL 490 |
| `profile_data` | Custom profile fields for non-bots | baseline when requested |

## Field Inventory: Channel Folders

**Source**: Zulip Get channel folders documentation:
<https://zulip.com/api/get-channel-folders>.

The implementation should use raw channel-folder objects from
`_fetch_channel_folders()` or preserve all fields before normalization.

| Field | API notes | Feature level |
| --- | --- | --- |
| `id` | Folder ID | FL 389 |
| `name` | Folder name | FL 389 |
| `order` | Zero-indexed display order | FL 414 |
| `date_created` | Creation timestamp or null | FL 389 |
| `creator_id` | Creator user ID or null | FL 389 |
| `description` | Markdown description | FL 389 |
| `rendered_description` | HTML description | FL 389 |
| `is_archived` | Archive marker | FL 389 |

Assigned channels are not embedded in the folder response. Folder show must list
streams and filter raw stream objects where `folder_id` equals the folder ID.

## Decision 1: Four Commands Instead of Two

**Decision**: Provide `channel show`, `group show`, `user show`, and
`folder show`.

**Rationale**: The lossy list commands exist for all four entities, and each
has detail data that administrators need for auditing. Splitting by entity keeps
targeting consistent with current command groups.

**Alternatives Considered**:

- Only `channel show` and `group show`: Rejected because user and folder detail
  auditing are part of the locked scope.
- One generic `zulip show TYPE TARGET`: Rejected because it would duplicate
  target parsing rules and depart from existing Typer command grouping.

## Decision 2: Resolve IDs by Default with `--no-resolve`

**Decision**: Resolve IDs to names by default and provide `--no-resolve` on all
four commands.

**Rationale**: Human-readable auditing is the primary use case. Raw numeric IDs
are difficult to review, especially for permission group-setting values.
`--no-resolve` gives scripts and performance-sensitive workflows a predictable
way to avoid nonessential lookups.

**Alternatives Considered**:

- Opt-in resolution only: Rejected because default output would remain hard to
  audit.
- Never resolve: Rejected because it fails the human inspection use case.

## Decision 3: Show All Fields with Annotation

**Decision**: Display every server-returned field and annotate each with its
settable status.

**Rationale**: The motivation is that `channel list` and `group list` are
lossy. A detail command that hides unknown or read-only fields would recreate
that problem.

**Alternatives Considered**:

- Show only fields settable by current CLI flags: Rejected because fields such
  as `can_add_subscribers_group` must be visible before write flags exist.
- Show a curated subset: Rejected because it risks omitting new server fields.

## Decision 4: Positional Group Name Ergonomics

**Decision**: `group show GROUP` is accepted as shorthand for
`group show --group-name GROUP`, while `--group-id` remains available.

**Rationale**: This mirrors the ease of `channel show NAME` and preserves the
existing explicit `group list --group-name/--group-id` filter style.

**Alternatives Considered**:

- Only `--group-name`/`--group-id`: Rejected as unnecessarily verbose for the
  common case.
- Bare numeric as ID: Rejected to avoid changing the name-first pattern used by
  channels and folders.

## Decision 5: Derived Membership and Assigned-Channel Sections

**Decision**: User show includes groups containing the user, and folder show
includes channels assigned to the folder, only when resolution is enabled.

**Rationale**: These sections answer common auditing questions, but they require
extra list calls. Tying them to `--no-resolve` keeps cost predictable.

**Alternatives Considered**:

- Always skip derived sections: Rejected because it omits the practical detail
  administrators asked for.
- Add separate flags for every section: Rejected for v1 because `--no-resolve`
  already provides a clear cost-control switch.
