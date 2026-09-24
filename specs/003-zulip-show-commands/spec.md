<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Feature Specification: Zulip Show Commands

**Feature Branch**: `003-zulip-show-commands`
**Created**: 2026-09-24
**Status**: Draft
**Input**: User description: "Add specification artifacts for Zulip show
commands, including detailed read-only views for channels, groups, users, and
channel folders."

## Clarifications

### Session 2026-09-24

- Q: What command scope should this feature cover? → A: Add exactly four
  read-only commands: `lftools-uv zulip channel show`,
  `lftools-uv zulip group show`, `lftools-uv zulip user show`, and
  `lftools-uv zulip folder show`.
- Q: Should identifiers in detail output be resolved to names? → A: Yes.
  Resolve IDs to human-readable names by default. Every show command MUST
  provide `--no-resolve` to skip extra API calls and render raw IDs.
- Q: How much server data should be shown? → A: Show every field returned by
  the relevant Zulip server object. Human output MUST annotate each field with
  whether it is settable through the current CLI, server-settable but not yet
  exposed, or read-only.
- Q: How should targeting work? → A: Match existing command patterns. Channel
  show accepts a positional channel name or `--channel-id`, plus
  `--include-archived`. Group show accepts `--group-name` or `--group-id` and
  also accepts a positional group name as shorthand for `--group-name`. User
  show uses the existing `--by-email`, `--by-id`, and `--by-name` pattern.
  Folder show accepts a folder name or `id:N`, matching the folder resolver.
- Q: Should machine-readable output be supported? → A: Yes. All four commands
  support the hidden `--json` flag convention and emit stable JSON envelopes.
- Q: Are future write flags for additional channel permissions in scope? → A:
  No. The show command MUST display those fields and mark them as
  server-settable but not exposed when the CLI lacks a write flag.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Inspect a channel configuration (Priority: P1)

As a Zulip administrator, I want to inspect one channel's complete server
configuration so that I can audit settings hidden by `channel list` before
making changes.

**Why this priority**: Channel detail inspection is the primary gap. The
existing `channel list` projection intentionally drops most stream fields,
including permission groups and folder assignment.

**Independent Test**: Mock the Zulip streams response for one channel and verify
`channel show` renders all returned fields, resolves folder/user/group IDs by
default, honors `--no-resolve`, marks settable fields, and emits JSON.

**Acceptance Scenarios**:

1. **Given** a configured Zulip connection and an active channel, **When** the
   user runs `zulip channel show general`, **Then** the output includes every
   field returned by the raw stream object with settable annotations.
2. **Given** a channel with permission group fields, **When** the user runs
   `zulip channel show general`, **Then** group IDs and group-setting values are
   rendered as group display names by default.
3. **Given** the same channel, **When** the user runs
   `zulip channel show general --no-resolve`, **Then** raw numeric IDs and raw
   group-setting structures are rendered without group, user, or folder lookup.
4. **Given** an archived channel, **When** the user runs
   `zulip channel show old --include-archived`, **Then** the archived channel is
   resolved and shown; without `--include-archived`, the existing archived-target
   hint is used.
5. **Given** `--json`, **When** channel show succeeds, **Then** the command emits
   `{"channel": {...}, "annotations": {...}, "resolved": {...}}`.

---

### User Story 2 - Inspect a group and its members (Priority: P1)

As a Zulip administrator, I want to inspect a user group, including its members
and permission settings, so that I can audit access-control inputs before using
them on channels.

**Why this priority**: `group list` intentionally collapses `members` to a
count. The member list is explicitly required for useful group auditing.

**Independent Test**: Mock the user-groups and users responses and verify group
show displays identity fields, member rows, direct subgroups, permission fields,
system-role display names, and JSON output.

**Acceptance Scenarios**:

1. **Given** a custom group, **When** the user runs
   `zulip group show --group-name Engineering`, **Then** output includes group
   identity, description, type, deactivated state, member rows, subgroups, and
   group permission settings.
2. **Given** a system role group, **When** the user runs
   `zulip group show Administrators`, **Then** the human display name is shown
   and the raw API name is retained in JSON.
3. **Given** a group with member IDs, **When** resolution is enabled, **Then**
   members are rendered as Full Name, Email, and User ID rows.
4. **Given** `--no-resolve`, **When** group show runs, **Then** member and
   subgroup sections show raw IDs only and do not fetch user details.

---

### User Story 3 - Inspect a user account (Priority: P2)

As a Zulip administrator, I want to inspect one user account, including role,
bot status, profile fields, and group membership, so that I can diagnose access
and identity issues from the CLI.

**Why this priority**: User detail inspection complements group and channel
inspection, but channel and group audits deliver the immediate administration
value.

**Independent Test**: Mock the users and groups responses and verify user show
resolves by email, ID, and full name; handles ambiguous full names; displays
profile data; and shows group membership when resolution is enabled.

**Acceptance Scenarios**:

1. **Given** a user email, **When** the user runs
   `zulip user show alice@example.com --by-email`, **Then** output includes the
   user identity, role, bot fields, active state, join date, timezone, avatar,
   and profile fields.
2. **Given** a user ID, **When** the user runs `zulip user show 42 --by-id`,
   **Then** the same detail output is produced for that user.
3. **Given** a full name matching multiple users, **When** the user runs
   `zulip user show "Alex Kim" --by-name`, **Then** the command fails with the
   existing ambiguity style and suggests `--by-id` or `--by-email`.
4. **Given** resolution is enabled, **When** user show succeeds, **Then** the
   output includes groups containing the user. With `--no-resolve`, that group
   membership section is skipped to avoid the extra groups API call.

---

### User Story 4 - Inspect a channel folder (Priority: P2)

As a Zulip administrator, I want to inspect one channel folder and the channels
assigned to it so that I can audit folder organization without using the web UI.

**Why this priority**: Folder details extend the feature introduced by the
folder-management specification and help validate channel organization.

**Independent Test**: Mock the channel-folder and streams responses and verify
folder show resolves by name and `id:N`, displays all folder fields, lists
assigned channels by default, and skips channel enumeration with `--no-resolve`.

**Acceptance Scenarios**:

1. **Given** a folder name, **When** the user runs `zulip folder show Projects`,
   **Then** the output includes folder identity, description, rendered HTML,
   order, archived state, creation metadata, creator display, and settable
   annotations.
2. **Given** a folder ID, **When** the user runs `zulip folder show id:10`,
   **Then** the same detail output is produced.
3. **Given** resolution is enabled, **When** folder show succeeds, **Then** the
   output lists channels whose raw stream `folder_id` equals the folder ID.
4. **Given** `--no-resolve`, **When** folder show succeeds, **Then** the command
   does not enumerate streams and the assigned-channel section is omitted.

### Edge Cases

- A show command targeting a missing channel, group, user, or folder MUST return
  a non-zero exit code with a clear not-found message.
- Ambiguous group or user names MUST fail with the existing ambiguity patterns
  and include candidate IDs for disambiguation.
- Numeric-looking channel names are still names; users MUST pass
  `--channel-id` to target a channel by ID.
- Numeric-looking folder tokens are names unless prefixed with `id:`.
- Channel and group permission fields can be either an integer group ID or an
  object with `direct_members` and `direct_subgroups`; both shapes MUST render.
- If a server omits a feature-level-gated field, show output MUST omit that
  field rather than synthesize it.
- If resolution data cannot be fetched after the target object is found, the
  command SHOULD fail with a clear API error rather than silently showing
  partially resolved data. Users can rerun with `--no-resolve`.
- `--json` output MUST remain valid JSON even when optional sections are empty.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-039**: System MUST provide `lftools-uv zulip channel show [channel]` with
  optional `--channel-id`, `--include-archived`, `--no-resolve`, and `--json`.
  Exactly one of positional channel name or `--channel-id` MUST be supplied.
- **FR-040**: Channel show MUST display every field present in the raw stream
  object returned by the Zulip API. Human output MUST include, at minimum when
  present, identity fields, folder fields, `topics_policy`, permission group
  fields, retention/history fields, creator metadata, legacy posting fields,
  web/private flags, and `subscriber_count`.
- **FR-041**: Channel show MUST derive a human `type` value from
  `is_web_public` and `invite_only` while preserving those raw fields in JSON.
- **FR-042**: Channel show MUST annotate every displayed field with a settable
  status: `via --flag`, `via command`, `not exposed`, or `no`. Existing
  channel update flags MUST be shown as setters for `name`, `description`,
  `type`, `topics_policy`, `can_subscribe_group`,
  `can_remove_subscribers_group`, and `folder_id`.
- **FR-043**: Channel show MUST mark server-settable but currently unexposed
  channel fields distinctly, including all returned channel group-setting
  permission fields without current write flags. This includes
  `can_add_subscribers_group` (FL 342), `can_administer_channel_group`
  (FL 325), `can_send_message_group` (FL 333), delete-message, move-message,
  resolve-topic, and create-topic permission fields. The feature MUST NOT add
  write flags for these fields.
- **FR-044**: System MUST provide `lftools-uv zulip group show [group]` with
  optional `--group-name`, `--group-id`, `--no-resolve`, and `--json`. The
  positional group argument is shorthand for `--group-name`; exactly one target
  mechanism MUST be supplied.
- **FR-045**: Group show MUST display every field present in the raw user-group
  object returned by Zulip, including identity fields, `members`,
  `direct_subgroup_ids`, deactivation state, creation metadata, and permission
  group-setting fields when present.
- **FR-046**: Group show MUST render members as a sub-table containing Full
  Name, Email, and User ID by default. With `--no-resolve`, it MUST render raw
  member user IDs only and skip the users API call.
- **FR-047**: Group show MUST render direct subgroup IDs as group display names
  by default. Recursive subgroup expansion is out of scope.
- **FR-048**: System MUST provide `lftools-uv zulip user show USER` requiring
  exactly one of `--by-email`, `--by-id`, or `--by-name`, plus `--no-resolve`
  and `--json`.
- **FR-049**: User show MUST display every field present in the raw user object
  used for the target, including `user_id`, names, `email`, `delivery_email`,
  role, bot fields, active/deleted status, join date, timezone, avatar fields,
  and custom `profile_data` when available.
- **FR-050**: User show MUST derive a human role label from Zulip role values:
  owner, administrator, moderator, member, or guest, while preserving the raw
  role value in JSON.
- **FR-051**: User show MUST list groups containing the user when resolution is
  enabled. With `--no-resolve`, it MUST skip the groups API call and omit that
  derived membership section.
- **FR-052**: System MUST provide `lftools-uv zulip folder show FOLDER` where
  `FOLDER` is a folder name or `id:N`, plus `--no-resolve` and `--json`.
- **FR-053**: Folder show MUST display every field present in the raw channel
  folder object returned by Zulip: `id`, `name`, `description`,
  `rendered_description`, optional `order`, `is_archived`, `date_created`, and
  `creator_id`.
- **FR-054**: Folder show MUST list channels assigned to the folder by default
  by listing streams and filtering on `folder_id`. With `--no-resolve`, it MUST
  skip that channel enumeration.
- **FR-055**: All show commands MUST resolve IDs to names by default where a
  resolver exists: users, groups, channel folders, channel creators, folder
  creators, group members, subgroup IDs, and channel permission group settings.
- **FR-056**: All show commands MUST document that default resolution can make
  extra Zulip API calls, and `--no-resolve` MUST avoid those nonessential
  calls while preserving target resolution needed to find the object.
- **FR-057**: All show commands MUST support hidden `--json` output. JSON MUST
  include the raw object, settable annotations, and any derived or resolved
  sections without losing raw IDs.
- **FR-058**: Human output MUST use stable ASCII-safe table headings. The
  settable marker MUST be textual, using `via --flag`, `via command`,
  `not exposed`, or `no`.
- **FR-059**: Implementation MUST add API and CLI tests covering success, JSON,
  not-found, ambiguity, `--no-resolve`, settable annotations, and feature-level
  omitted fields for all four commands.
- **FR-060**: Contracts and quickstart documentation MUST describe command
  targeting, output shapes, extra API-call behavior, and out-of-scope write
  flags.

### Key Entities

- **ChannelDetail**: Raw Zulip stream object plus derived `type`, optional
  resolved folder, creator, and permission group names.
- **GroupDetail**: Raw Zulip user-group object plus display name, system/custom
  classification, member rows, direct subgroup names, and permission displays.
- **UserDetail**: Raw Zulip user object plus role label, custom profile data,
  and optional group membership rows.
- **FolderDetail**: Raw Zulip channel-folder object plus creator display and
  optional assigned-channel rows.
- **SettableAnnotation**: Per-field metadata recording whether the current CLI
  can write the field, which flag writes it, or whether it is server-settable
  but not exposed.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-015**: Administrators can inspect one channel's full returned
  configuration, including permission groups, without using the Zulip web UI.
- **SC-016**: Administrators can inspect one group's actual member list and
  permission settings without losing member IDs.
- **SC-017**: Administrators can inspect one user's identity, role, custom
  profile data, and group membership from one CLI invocation.
- **SC-018**: Administrators can inspect one folder and its assigned channels
  from one CLI invocation.
- **SC-019**: Each show command supports parseable JSON suitable for automation.
- **SC-020**: `--no-resolve` reduces nonessential lookup calls while preserving
  accurate raw detail output.

## Assumptions

- Existing Zulip optional dependency, configuration resolution, API exceptions,
  Typer apps, list commands, and resolver helpers from specs 001 and 002 are
  present.
- The implementation will reuse the refactored Zulip packages under
  `lftools_uv/api/endpoints/zulip/` and `lftools_uv/typer_apps/zulip/` rather
  than recreating single-file modules.
- Show commands are read-only and do not mutate Zulip state.
- Feature-level-gated fields are displayed when returned by the server; older
  servers may omit them.
- Future write flags for additional channel permissions are tracked separately
  and are not part of this feature.
