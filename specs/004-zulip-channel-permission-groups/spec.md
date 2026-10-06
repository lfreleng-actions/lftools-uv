<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- tables preserve exact CLI/API names -->

# Feature Specification: Zulip Channel Permission Groups

**Feature Branch**: `004-zulip-channel-permission-groups`
**Created**: 2026-10-06
**Status**: Draft
**Input**: User description: "Expose three Zulip channel permission-group
settings as writable CLI flags for channel create and update, spec only."

## Clarifications

### Session 2026-10-06

- Q: Which permissions are in scope? → A: Exactly three channel permission
  group settings: `can_add_subscribers_group`,
  `can_administer_channel_group`, and `can_send_message_group`.
- Q: Should the feature rename the existing `--allow-group` flag? → A: No.
  Keep `--allow-group` for backwards compatibility. New flags mirror Zulip API
  field names for predictability: `--can-add-subscribers-group`,
  `--can-administer-channel-group`, and `--can-send-message-group`.
- Q: Should `can_send_message_group` fall back to legacy `stream_post_policy`
  on servers below feature level 333? → A: No. The CLI must fail with a clear
  feature-level error rather than silently using different semantics.
- Q: How should values be specified? → A: Reuse the existing permission group
  syntax from `--allow-group` and `--can-remove-subscribers-group`: a
  comma-separated list of group names, or `id:NUM` for explicit group ID lookup.
- Q: Does the API support resetting these permissions to an implicit server
  default? → A: No reset/null form was found in the official Zulip parameter
  documentation. This feature does not add a `none` sentinel for these flags.
  Users set an explicit group-setting value; `Nobody` can be used only when
  the server accepts it for that permission.
- Q: How should implementation be delivered? → A: Implementation must be split
  into three stacked PRs, one permission flag per PR. Shared feature-level and
  resolver plumbing lands in the first implementation PR.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Control who can add subscribers (Priority: P1)

As a Zulip administrator, I want to set who can add other users to a channel
when creating or updating the channel so that channel membership management is
constrained by organization policy.

**Why this priority**: This permission directly affects channel access and is
one of the settings already displayed by `channel show` but not writable.

**Independent Test**: Mock `channel create` and `channel update` calls using
`--can-add-subscribers-group`, verify the resolved group-setting value is sent
as `can_add_subscribers_group` in the correct create/update shape, verify
feature-level gating at FL 342, and verify `channel show` annotations identify
the new setter.

**Acceptance Scenarios**:

1. **Given** a Zulip server at feature level 342 or newer, **When** the user
   runs `zulip channel create project --can-add-subscribers-group Administrators`,
   **Then** the create request includes `can_add_subscribers_group` with the
   resolved Administrators group-setting value.
2. **Given** an existing channel on a Zulip server at feature level 342 or
   newer, **When** the user runs
   `zulip channel update project --can-add-subscribers-group "Engineering, id:22"`,
   **Then** the update request includes `can_add_subscribers_group` wrapped as
   `{"new": {"direct_members": [], "direct_subgroups": [...]}}`.
3. **Given** a server below FL 342, **When** either command uses
   `--can-add-subscribers-group`, **Then** the command fails before mutation
   with the feature-level error shape defined in the contract.
4. **Given** `zulip channel show project`, **When** the server returns
   `can_add_subscribers_group`, **Then** the settable annotation reports
   `via --flag` and setter `--can-add-subscribers-group`.

---

### User Story 2 - Control who can administer a channel (Priority: P1)

As a Zulip administrator, I want to set who can administer a channel during
creation or update so that channel-level administration can be delegated without
making every delegate an organization administrator.

**Why this priority**: Administration permissions control future channel
configuration changes and are core to safe delegation.

**Independent Test**: Mock `channel create` and `channel update` calls using
`--can-administer-channel-group`, verify payload shape, FL 325 gating, and the
corresponding `channel show` annotation.

**Acceptance Scenarios**:

1. **Given** a Zulip server at feature level 325 or newer, **When** the user
   runs `zulip channel create project --can-administer-channel-group Owners`,
   **Then** the create request includes `can_administer_channel_group` with the
   resolved group-setting value.
2. **Given** an existing channel on a Zulip server at feature level 325 or
   newer, **When** the user runs
   `zulip channel update project --can-administer-channel-group "Release Managers"`,
   **Then** the update request includes `can_administer_channel_group` wrapped
   with `{"new": ...}`.
3. **Given** a server below FL 325, **When** either command uses
   `--can-administer-channel-group`, **Then** the command fails before mutation
   with the feature-level error shape defined in the contract.
4. **Given** `zulip channel show project`, **When** the server returns
   `can_administer_channel_group`, **Then** the settable annotation reports
   `via --flag` and setter `--can-administer-channel-group`.

---

### User Story 3 - Control who can post in a channel (Priority: P1)

As a Zulip administrator, I want to set who can post messages in a channel
using the modern `can_send_message_group` field so that posting permissions are
managed consistently with other group-setting permissions.

**Why this priority**: `can_send_message_group` replaced the legacy
`stream_post_policy` field and controls the central ability to post in a
channel.

**Independent Test**: Mock `channel create` and `channel update` calls using
`--can-send-message-group`, verify payload shape, FL 333 gating, no
`stream_post_policy` fallback, and the corresponding `channel show` annotation.

**Acceptance Scenarios**:

1. **Given** a Zulip server at feature level 333 or newer, **When** the user
   runs `zulip channel create announcements --can-send-message-group Moderators`,
   **Then** the create request includes `can_send_message_group` with the
   resolved group-setting value.
2. **Given** an existing channel on a Zulip server at feature level 333 or
   newer, **When** the user runs
   `zulip channel update announcements --can-send-message-group "Full Members"`,
   **Then** the update request includes `can_send_message_group` wrapped with
   `{"new": ...}`.
3. **Given** a server below FL 333, **When** either command uses
   `--can-send-message-group`, **Then** the command fails before mutation and
   MUST NOT send legacy `stream_post_policy`.
4. **Given** `zulip channel show announcements`, **When** the server returns
   `can_send_message_group`, **Then** the settable annotation reports
   `via --flag` and setter `--can-send-message-group`.

### Edge Cases

- All three flags MUST accept the same comma-separated group specification
  syntax as `--allow-group`: names by default, `id:NUM` for explicit numeric
  IDs, empty segments ignored, and a wholly empty specification rejected.
- A numeric-looking group token without `id:` MUST be treated as a name. If not
  found, the error MUST hint: `If you meant a numeric group ID, use 'id:NUM'.`
- Ambiguous group names MUST fail before mutation with the existing ambiguity
  style listing candidate IDs and names.
- Multiple permission flags MAY be supplied in the same `channel create` or
  `channel update` invocation. Each maps independently to its own Zulip field.
- The feature MUST NOT rename, remove, or change `--allow-group` behavior.
- The feature MUST NOT add user-facing US#/FR#/T### identifiers to help text.
- Because official docs do not document a null/reset value for these group
  settings, `none` is treated as a group name rather than a clearing sentinel.
- Zulip may return `ignored_parameters_unsupported` in successful responses for
  unsupported request parameters. The implementation MUST rely on feature-level
  gating and exact field names instead of trusting a success response alone.
- If `channel show` receives any of the three fields from the server, it MUST
  continue to render raw and resolved values exactly as feature 003 designed.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-061**: System MUST add `--can-add-subscribers-group` to
  `lftools-uv zulip channel create` and `lftools-uv zulip channel update`.
  The flag MUST map exactly to Zulip field `can_add_subscribers_group`.
- **FR-062**: System MUST add `--can-administer-channel-group` to
  `lftools-uv zulip channel create` and `lftools-uv zulip channel update`.
  The flag MUST map exactly to Zulip field `can_administer_channel_group`.
- **FR-063**: System MUST add `--can-send-message-group` to
  `lftools-uv zulip channel create` and `lftools-uv zulip channel update`.
  The flag MUST map exactly to Zulip field `can_send_message_group`.
- **FR-064**: Each new flag MUST reuse the existing group resolver used by
  `--allow-group` and `--can-remove-subscribers-group`: comma-separated group
  names by default, `id:NUM` for explicit ID lookup, system role display names,
  ambiguity handling, and the numeric-not-found `id:` hint.
- **FR-065**: Create requests sent through `POST /api/v1/users/me/subscriptions`
  MUST encode each supplied permission field as a raw Zulip group-setting value:
  either a single integer group ID or an object with `direct_members` and
  `direct_subgroups`.
- **FR-066**: Update requests sent through
  `PATCH /api/v1/streams/{stream_id}` MUST encode each supplied permission
  field as a Zulip group-setting update object: `{"new": <group-setting-value>}`.
  The CLI MUST omit `old`.
- **FR-067**: System MUST add feature-level constants for the three settings:
  `can-add-subscribers-group` = 342,
  `can-administer-channel-group` = 325, and
  `can-send-message-group` = 333.
- **FR-068**: Each new flag MUST short-circuit before mutation when the server
  `zulip_feature_level` is below the field's required feature level. Human
  output MUST use `Error: This operation requires Zulip feature level X (server has Y)`.
  JSON mode MUST exit 1 and return the same error text in the command's
  established error payload style where one exists.
- **FR-069**: The `--can-send-message-group` implementation MUST NOT fall back
  to legacy `stream_post_policy` on older servers. Unsupported servers MUST get
  the FL 333 error from FR-068.
- **FR-070**: The feature MUST NOT add a `none` or null-clearing sentinel for
  the three new flags unless official Zulip documentation later documents one.
  A value of `none` MUST be resolved as a group name and fail if no such group
  exists.
- **FR-071**: `channel create` and `channel update` MUST accept any combination
  of the new flags with existing `--allow-group`,
  `--can-remove-subscribers-group`, `--folder`, `--topic-policy`, and metadata
  flags, subject to each flag's existing validation and feature gate.
- **FR-072**: `channel create` and `channel update` help text MUST describe the
  new flags without spec/task identifiers and must mention the `id:NUM` group
  lookup syntax.
- **FR-073**: `channel show` settable annotations from feature 003 MUST be
  updated so `can_add_subscribers_group`, `can_administer_channel_group`, and
  `can_send_message_group` report `via --flag` with their new setters instead
  of `not exposed`.
- **FR-074**: Tests MUST cover API payloads, CLI flag forwarding, group
  resolution errors, feature-level gates, JSON/human output behavior, and the
  `channel show` annotation update for each new flag.
- **FR-075**: Contracts and quickstart documentation MUST describe the new
  flags, field names, feature levels, value shapes, create-vs-update payload
  difference, no-clear decision, and no `stream_post_policy` fallback.

### Key Entities

- **ChannelPermissionFlag**: One CLI option that maps to one Zulip channel
  permission group setting and carries its required feature level.
- **GroupSettingValue**: Zulip permission value represented as either one user
  group ID integer or an object with `direct_members` and `direct_subgroups`.
- **GroupSettingUpdate**: Zulip update-envelope object containing required
  `new` group-setting value and optional `old`; this CLI omits `old`.
- **Channel Settable Annotation**: Feature 003 metadata that records whether a
  raw `channel show` field is writable and which flag writes it.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-021**: Administrators can create a channel and set any one of the three
  newly exposed permission groups in the same invocation.
- **SC-022**: Administrators can update any one of the three newly exposed
  permission groups on an existing channel in the same invocation used for
  other channel settings.
- **SC-023**: Servers below the documented feature levels fail before mutation
  with the canonical feature-level error rather than silently ignored fields.
- **SC-024**: `channel show` no longer labels these three fields as unexposed;
  it points users to the exact write flags.
- **SC-025**: The three implementation PRs can be reviewed independently while
  preserving a shared, non-duplicative foundation.

## Assumptions

- Existing Zulip channel create/update, group resolution, feature-level checks,
  and show annotations from specs 001 through 003 are present.
- The official Zulip docs cited in `research.md` are authoritative for field
  names, feature levels, and value shapes.
- The authenticated Zulip user has whatever channel or organization permission
  Zulip requires to mutate these settings; the CLI surfaces server permission
  errors as-is.
- Implementation PRs are stacked in this order: shared foundation plus
  `can_add_subscribers_group`, then `can_administer_channel_group`, then
  `can_send_message_group`.
