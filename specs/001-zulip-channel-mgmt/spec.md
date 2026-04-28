<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Feature Specification: Zulip Channel Management

**Feature Branch**: `001-zulip-channel-mgmt`
**Created**: 2026-04-28
**Status**: Draft
**Input**: User description: "Add support in lftools-uv
for managing Zulip channels (streams), including
user-facing commands for channel administration on
a single Zulip server."

## Clarifications

### Session 2026-04-29

- Q: For private channel creation, must the command require specifying
  who can access the channel at creation time? → A: Yes — private
  channels MUST require at least one `--subscribe USER` or
  `--allow-group GROUP` at creation time to prevent creating an
  inaccessible channel. The Zulip API does NOT auto-subscribe the
  requester on channel creation — without explicit `principals`, no one
  is subscribed. For private channels this means the channel becomes
  completely inaccessible. `--subscribe` adds immediate subscribers;
  `--allow-group` grants group-based access permission (not
  auto-subscribed).
- Q: Should the delete command support only archive (deactivate) or
  also permanent deletion? → A: Archive only — permanent deletion is
  removed from scope entirely (Zulip API only supports archive).
- Q: Should the archive command require a confirmation flag to prevent
  accidental archival? → A: Yes — require `--yes` flag; reject without
  it (safe default, scriptable).
- Q: Should mutation commands (create, update, archive, unarchive,
  subscribe, unsubscribe) also support `--json` output? → A: Yes — all
  commands support `--json` for full automation consistency. All mutations
  return a consistent JSON schema with `status`, `channel_id`
  (int or null), `channel_name`, and `operation` fields.
- Q: Should subscribe/unsubscribe auto-detect user identifier format
  or require explicit flags? → A: Require explicit `--by-email`,
  `--by-id`, or `--by-name` flag (three identification modes for USERS
  only). `--by-name` matches on the Zulip `full_name` field (Zulip has
  no stable username field). If `--by-name` matches multiple users, the
  command MUST fail with an ambiguity error listing the matches and
  instruct the user to use `--by-id` or `--by-email` instead.
- Q: Should the tool support listing Zulip users to aid channel management
  workflows? → A: Yes — add `lftools-uv zulip user list` command showing
  full name, email, and user ID with `--json` support. Lists active
  users only by default; `--include-bots` and `--include-deactivated`
  flags for broader listing.
- Q: What is the implementation dependency ordering between list users and
  create channel? → A: List users (User Story 2) must be implemented before
  create channel (User Story 4) because private channel creation requires
  valid user identifiers discoverable via user listing.
- Q: Should the tool support listing user groups to aid private channel
  creation? → A: Yes — add `lftools-uv zulip group list` command. This is a
  prerequisite for channel creation since private channels can specify
  allowed groups. Groups are identifiable by `--group-name` (case-
  insensitive) or `--group-id`; ambiguous name matches fail with error.
- Q: Should an unarchive command be provided since archive is reversible?
  → A: Yes — add `lftools-uv zulip channel unarchive` with `--yes` flag
  required for safety.
- Q: How should channel commands identify a target channel? → A: The
  channel is the first positional argument and MUST be interpreted as a
  channel name by default, even if numeric-looking. Use `--channel-id`
  to target a channel by numeric ID explicitly; use `--channel-name`
  only for explicitness, not disambiguation. Channel name matching
  MUST be case-insensitive. (Zulip channel names are
  case-insensitively unique.)
- Q: Should archived channels appear in the default channel list? → A:
  No — list active channels only by default; add `--include-archived`
  flag to include archived channels.
- Q: What fields should the update command support in v1? → A: Name,
  description, channel type (public/web-public/private), and topic policy.
  No other settings for v1.
- Q: What should the config CLI flag be named and what is the exact
  precedence? → A: `--zuliprc PATH` pointing to a zuliprc-format file.
  Precedence: `--zuliprc` flag > `./zuliprc` (current directory) >
  `[zulip]` section in lftools.ini > `~/.zuliprc`.
- Q: How should `--by-name` handle ambiguous matches (multiple users with
  the same full_name)? → A: Command MUST fail with an ambiguity error
  listing the matching users (with their emails/IDs) and instruct the
  user to retry with `--by-id` or `--by-email`.
- Q: Should "initial subscribers" and "allowed groups" be separate concepts
  in private channel creation? → A: Yes — `--subscribe USER` adds
  immediate subscribers; `--allow-group GROUP` grants group-based access
  permission (users are NOT auto-subscribed). For public and web-public
  channels, `--allow-group` is not applicable. Lockout prevention
  requires at least one `--subscribe` or `--allow-group`.
- Q: How should groups be identified in commands? → A: By `--group-name`
  (case-insensitive) or `--group-id`. If a group name is ambiguous, the
  command MUST fail with an error instructing the user to use
  `--group-id`.
- Q: Should the tool require a minimum Zulip server version? → A: No —
  feature-detect at runtime. Commands relying on newer features
  (unarchive, group-based access, topic policy, web-public channels)
  MUST detect server capabilities and return a clear error like "This
  operation requires Zulip feature level X (server has Y)" if
  unsupported.
- Q: Should no-op mutations succeed or fail? → A: Succeed silently
  (exit 0). Archive already-archived, unarchive already-active,
  subscribe already-subscribed, unsubscribe not-subscribed, and
  update-with-no-changes all return success.
- Q: Should mutation JSON output follow a consistent schema? → A:
  Yes — single mutations: `{"status": "success"|"error",
  "channel_id": int|null, "channel_name": str,
  "operation": str, ...}`. Bulk operations:
  `{"status": "partial"|"success"|"error",
  "channel_id": int|null, "channel_name": str,
  "operation": "subscribe"|"unsubscribe",
  "results": [...], "errors": [...]}`. `channel_id` is `null`
  when the target channel cannot be resolved.
- Q: How should `--subscribe USER` in `channel create` identify users?
  → A: Using the same `--by-email`/`--by-id`/`--by-name` mechanism as
  subscribe/unsubscribe. The identifier flag applies to ALL `--subscribe`
  values in a single invocation (cannot mix email and ID in one command).
  `--by-name` ambiguity follows the same fail-with-error behavior as
  FR-005/FR-006.
- Q: How should numeric channel/group identifiers be disambiguated?
  → A: Channels use `--channel-id`/`--channel-name` for explicit
  disambiguation. Groups use `--group-id`/`--group-name`. Users keep
  `--by-id`/`--by-email`/`--by-name`. The positional channel argument
  defaults to name interpretation unless `--channel-id` is specified.
- Q: How should commands resolve archived channels as targets? → A:
  Commands search active channels only by default. `--include-archived`
  extends the search to include archived channels. Commands like
  `unarchive` (where targeting archived channels is the primary use case)
  require `--include-archived` to locate the target channel.
- Q: What happens when `--allow-group` is used against a Zulip server
  that doesn't support group-based access control? → A: Command returns
  a clear feature-level error following the FR-019 pattern.
- Q: Does Zulip support more than two channel types? → A: Yes — Zulip
  supports three types: public (visible to organization members),
  web-public (visible to anyone on the internet without a Zulip account,
  requires spectator access enabled), and private (invite-only). All
  three MUST be supported in `channel create` and `channel update`.
  Web-public requires runtime feature detection (spectator access).
- Q: Should channel creation support announcement control? → A: Yes —
  `--announce` explicitly requests an announcement in the server's
  announcement stream; `--no-announce` explicitly suppresses it. These
  are mutually exclusive. Default (neither flag): follow API default
  (no announcement). The Zulip API `announce` parameter defaults to
  `false`.
- Q: Should channel creation and update support the "no topic" topic
  policy? → A: Yes — `--topic-policy` with values `allow`, `deny`, or
  `follow-default`. Requires runtime feature-level detection per FR-019.
- Q: Does the Zulip API auto-subscribe the requester on channel
  creation? → A: NO. The `principals` parameter must explicitly include
  users to subscribe. Without explicit subscribers, no one is subscribed.
  This makes the lockout prevention policy for private channels even more
  critical — an empty private channel is inaccessible to everyone.
- Q: How should identifier flags be namespaced to avoid ambiguity?
  → A: Channels: `--channel-id`/`--channel-name` (positional arg
  defaults to name). Groups: `--group-id`/`--group-name`. Users:
  `--by-email`/`--by-id`/`--by-name`. This eliminates cross-entity
  ambiguity (e.g., `subscribe 123 --by-name Alice` is unambiguous:
  `123` is the channel name, `--by-name` applies to user `Alice`).
- Q: Should web-public channels require feature detection? → A: Yes —
  web-public channels require spectator access enabled on the server.
  Attempting to create or update to web-public on a server without
  spectator access MUST return a feature-level error per FR-019.
- Q: Should US8 (Update) have complete topic-policy scenarios? → A:
  Yes — added scenarios for `allow`, `deny`, `follow-default`, and
  unsupported server.

- Q: Should bulk mutation JSON include an `operation` field? → A: Yes —
  bulk operations (subscribe/unsubscribe) MUST include
  `"operation": "subscribe"|"unsubscribe"` in their JSON schema for
  unambiguous automation parsing.
- Q: Does archiving an already-archived channel require `--include-archived`?
  → A: Yes — since commands search active channels by default, targeting
  an already-archived channel for archive (no-op) requires
  `--include-archived` to locate it.
- Q: Should update-to-private enforce lockout prevention? → A: Yes —
  when updating a channel's type to private, if the channel has NO current
  subscribers, the command MUST require `--subscribe` or `--allow-group` to
  prevent creating an inaccessible channel (same rule as FR-002 for
  creation).
- Q: Should ambiguous `--group-name` in `--allow-group` fail with an error?
  → A: Yes — if `--group-name` matches multiple groups, the command MUST
  fail with an ambiguity error listing matching groups (with IDs) and
  instruct the user to retry with `--group-id`.
- Q: Should US7 use the canonical command name in acceptance scenarios?
  → A: Yes — use `lftools-uv zulip channel subscribers` explicitly in
  US7 narrative and acceptance scenarios for clarity and testability.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - List Available Channels (Priority: P1)

As a Zulip administrator using lftools-uv, I want to list all active channels
(public, web-public, and private) on my Zulip server so that I can audit the
current channel structure and plan organizational changes.

**Why this priority**: Listing is the most fundamental operation — it is
required for discovery before any other channel management action can be taken,
and it is non-destructive.

**Independent Test**: Can be fully tested by running the list command against a
Zulip server and verifying that all known active channels appear with correct
names and types. Delivers immediate value by enabling channel auditing.

**Acceptance Scenarios**:

1. **Given** a configured Zulip connection, **When** I run the list channels
   command, **Then** I see a human-readable table showing all active channels
   with their name, description, type (public/web-public/private), and
   subscriber count. Archived channels are excluded by default.
2. **Given** a configured Zulip connection, **When** I run the list channels
   command with `--include-archived`, **Then** I see all channels including
   archived ones, with an indication of archived status.
3. **Given** a configured Zulip connection, **When** I run the list channels
   command with `--json`, **Then** I receive JSON output containing the same
   channel data suitable for scripting and automation.
4. **Given** no valid Zulip configuration exists, **When** I run the list
   channels command, **Then** I see a clear error message indicating the
   configuration problem and the command exits with a non-zero exit code.

---

### User Story 2 - List Zulip Users (Priority: P1)

As a Zulip administrator, I want to list all users on the Zulip server with
their full name, email, and user ID so that I can discover user identifiers
before subscribing or unsubscribing them from channels.

**Why this priority**: User discovery is a prerequisite for effective
subscribe/unsubscribe operations and for private channel creation (which
requires specifying initial subscribers). This must be implemented before
channel creation (User Story 4).

**Dependency**: None (depends only on Zulip configuration, same as
User Story 1).

**Independent Test**: Can be tested by running the user list command against a
Zulip server and verifying that all known active users appear with correct
full names, emails, and user IDs.

**Acceptance Scenarios**:

1. **Given** a configured Zulip connection, **When** I run the list users
   command, **Then** I see a human-readable table showing all active human users
   with their full name, email address, and user ID. Bot accounts and
   deactivated users are excluded by default.
2. **Given** a configured Zulip connection, **When** I run the list users
   command with `--include-bots`, **Then** bot accounts are included in the
   results alongside human users.
3. **Given** a configured Zulip connection, **When** I run the list users
   command with `--include-deactivated`, **Then** deactivated users are
   included in the results with an indication of their deactivated status.
4. **Given** a configured Zulip connection, **When** I run the list users
   command with `--json`, **Then** I receive JSON output containing the same
   user data suitable for scripting and automation.
5. **Given** no valid Zulip configuration exists, **When** I run the list users
   command, **Then** I see a clear error message indicating the configuration
   problem and the command exits with a non-zero exit code.

---

### User Story 3 - List User Groups (Priority: P1)

As a Zulip administrator, I want to list all user groups on the Zulip server so
that I can discover group identifiers to use when creating private channels with
group-based access control.

**Why this priority**: Group discovery is a prerequisite for private channel
creation when specifying allowed groups. This must be implemented before
channel creation (User Story 4).

**Dependency**: None (depends only on Zulip configuration, same as
User Story 1).

**Independent Test**: Can be tested by running the group list command against a
Zulip server and verifying that all known user groups appear with correct names,
IDs, and member counts.

**Acceptance Scenarios**:

1. **Given** a configured Zulip connection, **When** I run the list groups
   command, **Then** I see a human-readable table showing all user groups with
   their name, group ID, description, and member count.
2. **Given** a configured Zulip connection, **When** I run the list groups
   command with `--json`, **Then** I receive JSON output containing the same
   group data suitable for scripting and automation.
3. **Given** no valid Zulip configuration exists, **When** I run the list groups
   command, **Then** I see a clear error message indicating the configuration
   problem and the command exits with a non-zero exit code.

---

### User Story 4 - Create a Channel (Priority: P1)

As a Zulip administrator, I want to create new channels (public, web-public, or
private) from the command line so that I can automate channel provisioning for
new projects or teams.

**Why this priority**: Channel creation is a core management action required to
set up new collaboration spaces. Combined with listing, it provides a complete
provisioning workflow.

**Dependency**: Requires User Story 2 (List Zulip Users) and User Story 3
(List User Groups) — private channel creation requires specifying initial
subscribers or allowed groups, and admins need to discover valid identifiers
via the user list and group list commands first.

**Independent Test**: Can be tested by creating a new channel and then verifying
it appears in the channel list with the correct name, description, and type.

**Acceptance Scenarios**:

1. **Given** a configured Zulip connection, **When** I create a public (or
   web-public) channel with a name and description, **Then** the channel is
   created on the server with the specified type and a success confirmation is
   displayed.
2. **Given** a configured Zulip connection, **When** I create a private channel
   with a name, description, and `--subscribe USER --by-email` for at least one
   initial subscriber, **Then** the channel is created as a private
   (invite-only) channel on the server with the specified users
   immediately subscribed.
3. **Given** a configured Zulip connection, **When** I create a private channel
   with a name, description, and `--subscribe USER --by-name` where the
   `full_name` matches multiple users, **Then** the command fails with an
   ambiguity error listing the matching users (with their emails and user IDs)
   and instructs the user to retry with `--by-id` or `--by-email`.
4. **Given** a configured Zulip connection, **When** I create a private channel
   with a name, description, and `--allow-group GROUP` (using `--group-name` or
   `--group-id`), **Then** the channel is created as a private channel with the
   specified group(s) granted access permission. Group members are NOT
   automatically subscribed.
5. **Given** a configured Zulip connection, **When** I create a private channel
   with both `--subscribe USER` and `--allow-group GROUP`, **Then** both are
   applied: users are immediately subscribed and groups are granted access
   permission.
6. **Given** a configured Zulip connection, **When** I attempt to create a
   private channel without specifying any `--subscribe` or `--allow-group`,
   **Then** the command rejects the request with an error explaining that
   private channels require at least one subscriber or allowed group to prevent
   creating an inaccessible channel. (Note: the Zulip API does NOT
   auto-subscribe the requester — without explicit subscribers, no one is
   subscribed and the channel is inaccessible.)
7. **Given** a public or web-public channel creation, **When** I specify
   `--allow-group`, **Then** the command rejects the request with an error
   explaining that `--allow-group` is only applicable to private channels.
8. **Given** a channel with the same name already exists, **When** I attempt to
   create a channel with that name, **Then** I see an error message indicating
   the name conflict and the command exits with a non-zero exit code.
9. **Given** a Zulip server that does not support group-based access control,
   **When** I create a private channel with `--allow-group`, **Then** the
   command returns a clear error message indicating the required Zulip feature
   level and the server's current level, and exits with a non-zero exit code.
10. **Given** a configured Zulip connection, **When** I create a channel with
    `--announce`, **Then** the channel is created and an announcement is posted
    to the server's designated announcement stream.
11. **Given** a configured Zulip connection, **When** I create a channel with
    `--no-announce`, **Then** the channel is created without an announcement.
12. **Given** a configured Zulip connection, **When** I create a channel without
    specifying `--announce` or `--no-announce`, **Then** the API default applies
    (no announcement).
13. **Given** a configured Zulip connection, **When** I specify both
    `--announce` and `--no-announce`, **Then** the command rejects the
    request with an error explaining that these flags are mutually exclusive.
14. **Given** a configured Zulip connection, **When** I create a channel with
    `--topic-policy deny`, **Then** the channel is created with the topic
    policy set to require topics on all messages.
15. **Given** a configured Zulip connection, **When** I create a channel without
    specifying `--topic-policy`, **Then** the channel is created using the
    server's default topic policy.
16. **Given** a Zulip server that does not support the topic policy feature,
    **When** I create a channel with `--topic-policy`, **Then** the command
    returns a clear error message indicating the required Zulip feature level
    and the server's current level, and exits with a non-zero exit code.
17. **Given** a Zulip server that does not support web-public channels
    (spectator access not enabled), **When** I create a web-public
    channel, **Then** the command returns a clear error message
    indicating the required capability and exits with a non-zero exit
    code.
18. **Given** a configured Zulip connection, **When** I create a channel with
    `--json`, **Then** the JSON response follows the standard mutation schema:
    `{"status": "success", "channel_id": int, "channel_name": str,
    "operation": "create", "type": "public"|"web-public"|"private"}`.
19. **Given** a configured Zulip connection, **When** I create a private
    channel with `--allow-group GROUP --group-name` and the group name matches
    multiple groups, **Then** the command fails with an ambiguity error listing
    the matching groups (with their IDs) and instructs the user to retry with
    `--group-id`.

---

### User Story 5 - Subscribe Users to a Channel (Priority: P2)

As a Zulip administrator, I want to subscribe one or more users to a channel by
email address, user ID, or full name so that I can bulk-manage channel
membership for onboarding or team changes.

**Why this priority**: User subscription management is the most common ongoing
administrative task after initial channel setup, especially for onboarding
workflows.

**Independent Test**: Can be tested by subscribing users to an existing channel
and verifying their membership via the subscriber list command.

**Acceptance Scenarios**:

1. **Given** an existing channel (identified by positional name argument),
   **When** I subscribe a single user using `--by-email`, **Then** the user is
   added to the channel and a success confirmation is displayed.
2. **Given** an existing channel, **When** I subscribe multiple users using
   `--by-email` in a single command, **Then** all specified users are
   added and a summary of results is displayed.
3. **Given** an existing channel, **When** I subscribe a user using `--by-id`,
   **Then** the user is added to the channel.
4. **Given** an existing channel, **When** I subscribe a user using
   `--by-name` (matching on Zulip `full_name`), **Then** the user is added to
   the channel.
5. **Given** an existing channel, **When** I use `--by-name` and the full name
   matches multiple users, **Then** the command fails with an ambiguity error
   listing the matching users (with their emails and user IDs) and instructs
   the user to retry with `--by-id` or `--by-email`.
6. **Given** a channel with a numeric name, **When** I pass it as the
   positional channel argument, **Then** it is interpreted as the
   channel name by default. Use `--channel-id` only when targeting
   by numeric ID.
7. **Given** an invalid email address, user ID, or full name, **When** I
   attempt to subscribe the user, **Then** I see an error identifying the
   invalid user and the command exits with a non-zero exit code.
8. **Given** an existing channel, **When** I attempt to subscribe users without
   specifying `--by-email`, `--by-id`, or `--by-name`, **Then** the command
   rejects the request with an error explaining that an identifier flag is
   required.
9. **Given** an existing channel, **When** I subscribe a user who is already
   subscribed, **Then** the command succeeds silently (exit 0) — this is a
   no-op.
10. **Given** an existing channel, **When** I subscribe users with `--json`,
    **Then** the JSON response follows the standard bulk mutation schema:
    `{"status": "partial"|"success"|"error",
    "channel_id": int|null, "channel_name": str,
    "operation": "subscribe", "results": [...],
    "errors": [...]}` where `channel_id` is `null` when the
    target channel cannot be resolved.

---

### User Story 6 - Unsubscribe Users from a Channel (Priority: P2)

As a Zulip administrator, I want to unsubscribe one or more users from a channel
so that I can manage access when team members rotate off a project.

**Why this priority**: Unsubscribe is the complement to subscribe and is needed
for complete membership lifecycle management.

**Independent Test**: Can be tested by unsubscribing users from a channel and
verifying they no longer appear in the subscriber list.

**Acceptance Scenarios**:

1. **Given** a user subscribed to a channel, **When** I unsubscribe them using
   `--by-email`, **Then** the user is removed from the channel and a success
   confirmation is displayed.
2. **Given** a channel, **When** I unsubscribe multiple users in a single
   command, **Then** all specified users are removed and a summary of results is
   displayed.
3. **Given** a user who is not subscribed to the channel, **When** I attempt to
   unsubscribe them, **Then** the command succeeds silently (exit 0) — this is
   a no-op.
4. **Given** a channel, **When** I use `--by-name` and the full name matches
   multiple users, **Then** the command fails with an ambiguity error listing
   the matching users (with their emails and user IDs) and instructs the user
   to retry with `--by-id` or `--by-email`.
5. **Given** a channel, **When** I unsubscribe users with `--json`,
   **Then** the JSON response follows the standard bulk mutation
   schema: `{"status": "partial"|"success"|"error",
   "channel_id": int|null, "channel_name": str,
   "operation": "unsubscribe", "results": [...],
   "errors": [...]}` where `channel_id` is `null` when the
   target channel cannot be resolved.

---

### User Story 7 - List Channel Subscribers (Priority: P2)

As a Zulip administrator, I want to list all subscribers of a specific channel
so that I can audit membership and verify subscription changes.

**Why this priority**: Subscriber listing is essential for auditing and
verifying subscribe/unsubscribe operations.

**Independent Test**: Can be tested by listing subscribers of a known channel
and verifying the output includes expected users.

**Acceptance Scenarios**:

1. **Given** a channel with subscribers, **When** I run
   `lftools-uv zulip channel subscribers <channel>`, **Then** I see
   a human-readable table showing each subscriber's full name,
   email, and user ID.
2. **Given** a channel with subscribers, **When** I run
   `lftools-uv zulip channel subscribers <channel>` with `--json`,
   **Then** I receive JSON output containing subscriber details.
3. **Given** a non-existent channel name or ID, **When** I run
   `lftools-uv zulip channel subscribers <channel>`, **Then** I see
   an error message indicating the channel was not found and the
   command exits with a non-zero exit code.

---

### User Story 8 - Update Channel Settings (Priority: P3)

As a Zulip administrator, I want to update a channel's name, description,
channel type (public/web-public/private), or topic policy so that I can keep
channel metadata current as projects evolve.

**Why this priority**: Updates are less frequent than creation or membership
changes but needed for ongoing maintenance.

**Independent Test**: Can be tested by updating a channel's name or description
and verifying the changes via the list command.

**Acceptance Scenarios**:

1. **Given** an existing channel, **When** I update its description, **Then**
   the channel description is changed on the server and a success confirmation
   is displayed.
2. **Given** an existing channel, **When** I update its name, **Then** the
   channel is renamed on the server.
3. **Given** an existing channel, **When** I update its channel type (e.g.,
   public to private, private to web-public, or any other transition supported
   by the Zulip API), **Then** the channel type is changed on the server.
4. **Given** an existing channel, **When** I update its topic policy using
   `--topic-policy allow`, **Then** the channel's topic policy is changed to
   permit messages without a topic.
5. **Given** an existing channel, **When** I update its topic policy using
   `--topic-policy deny`, **Then** the channel's topic policy is changed to
   require topics on all messages.
6. **Given** an existing channel, **When** I update its topic policy using
   `--topic-policy follow-default`, **Then** the channel's topic policy is
   changed to follow the server's default setting.
7. **Given** a Zulip server that does not support the topic policy feature,
   **When** I update a channel with `--topic-policy`, **Then** the command
   returns a clear error message indicating the required Zulip feature level
   and the server's current level, and exits with a non-zero exit code.
8. **Given** a Zulip server that does not support web-public channels, **When**
   I update a channel's type to web-public, **Then** the command returns a
   clear error message indicating the required capability and exits with a
   non-zero exit code.
9. **Given** an existing channel, **When** I update multiple settings (e.g.,
   name and description) in a single command, **Then** all specified settings
   are updated.
10. **Given** an existing channel, **When** I issue an update with values
    identical to the current state, **Then** the command succeeds silently
    (exit 0) — this is a no-op.
11. **Given** a non-existent channel, **When** I attempt to update it,
    **Then** I see an error indicating the channel was not found and the
    command exits with a non-zero exit code.
12. **Given** an existing channel, **When** I update it with `--json`, **Then**
    the JSON response follows the standard mutation schema:
    `{"status": "success", "channel_id": int, "channel_name": str,
    "operation": "update", ...updated fields}`.
13. **Given** a public or web-public channel with NO current subscribers,
    **When** I update its type to private without specifying `--subscribe` or
    `--allow-group`, **Then** the command rejects the request with an error
    explaining that converting to private requires at least one subscriber or
    allowed group to prevent lockout.
14. **Given** a public channel with existing subscribers, **When** I update its
    type to private, **Then** the type change succeeds (existing subscribers
    retain access).

---

### User Story 9 - Archive a Channel (Priority: P3)

As a Zulip administrator, I want to archive (deactivate) a channel so that I can
clean up unused channels with a reversible action.

**Why this priority**: Archival is the least frequent operation and
carries risk, making it lower priority than other management tasks.
Permanent deletion is out of scope as the Zulip API only supports archiving.

**Independent Test**: Can be tested by archiving a channel and verifying it no
longer appears in the active channel list.

**Acceptance Scenarios**:

1. **Given** an existing active channel, **When** I archive it with the `--yes`
   flag, **Then** the channel is deactivated on the server and a success
   confirmation is displayed.
2. **Given** an existing channel, **When** I attempt to archive it without the
   `--yes` flag, **Then** the command rejects the request with a message
   explaining that `--yes` is required to confirm archival.
3. **Given** an already-archived channel, **When** I attempt to archive it with
   `--include-archived --yes`, **Then** the command succeeds silently
   (exit 0) — this is a no-op.
4. **Given** a non-existent channel, **When** I attempt to archive it,
   **Then** I see an error indicating the channel was not found and the command
   exits with a non-zero exit code.
5. **Given** an existing channel, **When** I archive it with `--yes --json`,
   **Then** the JSON response follows the standard mutation schema:
   `{"status": "success", "channel_id": int, "channel_name": str,
   "operation": "archive"}`.

---

### User Story 10 - Unarchive a Channel (Priority: P3)

As a Zulip administrator, I want to unarchive (reactivate) a previously archived
channel so that I can restore channels that were archived by mistake or are
needed again.

**Why this priority**: Unarchive is the complement to archive and completes the
reversible archival lifecycle. It is lower priority because it is only needed
after an archive operation.

**Note**: Since commands search active channels by default, unarchiving an
archived channel requires `--include-archived` to locate the target channel.

**Independent Test**: Can be tested by unarchiving a previously archived channel
and verifying it reappears in the active channel list.

**Acceptance Scenarios**:

1. **Given** an archived channel, **When** I unarchive it with
   `--include-archived --yes`, **Then** the channel is reactivated on the server
   and a success confirmation is displayed.
2. **Given** an archived channel, **When** I attempt to unarchive it without the
   `--yes` flag, **Then** the command rejects the request with a message
   explaining that `--yes` is required to confirm unarchival.
3. **Given** an archived channel, **When** I attempt to unarchive it without
   `--include-archived`, **Then** the command returns a "channel not found"
   error and suggests using `--include-archived` to target archived channels.
4. **Given** a channel that is already active, **When** I attempt to unarchive
   it with `--yes`, **Then** the command succeeds silently (exit 0) — this is
   a no-op.
5. **Given** a non-existent channel, **When** I attempt to unarchive it,
   **Then** I see an error indicating the channel was not found and the command
   exits with a non-zero exit code.
6. **Given** an archived channel, **When** I unarchive it with
   `--include-archived --yes --json`, **Then** the JSON response follows the
   standard mutation schema: `{"status": "success", "channel_id": int,
   "channel_name": str, "operation": "unarchive"}`.
7. **Given** a Zulip server that does not support channel reactivation, **When**
   I attempt to unarchive a channel, **Then** the command returns a clear error
   message indicating the required Zulip feature level and the server's current
   level, and exits with a non-zero exit code.

---

### Edge Cases

- What happens when the Zulip server is unreachable or returns a network error?
  The system should display a clear connection error and exit with a non-zero
  code.
- What happens when the authenticated user does not have sufficient permissions
  to perform an operation (e.g., creating a channel or modifying a private
  channel)? The system should surface the permission error from the server.
- What happens when subscribing or unsubscribing a mix of valid and invalid
  users in a bulk operation? The system should report success for valid users
  and errors for invalid ones, with the overall exit code reflecting whether any
  errors occurred. JSON output uses `"status": "partial"` in this case.
- What happens when attempting to create a channel with an empty or overly long
  name? The system should validate input and return a meaningful error before
  making the API call, or surface the server's validation error.
- What happens when the zuliprc file is malformed or missing required fields?
  The system should report a clear configuration error identifying the issue.
- What happens when creating a private channel without specifying any
  `--subscribe` or `--allow-group`? The system MUST reject the request with a
  clear error explaining that private channels require at least one subscriber
  or allowed group to prevent creating an inaccessible channel. (The Zulip API
  does NOT auto-subscribe the requester — without explicit subscribers, no one
  is subscribed.)
- What happens when `--by-name` matches multiple users with the same
  `full_name`? The command MUST fail with an ambiguity error listing all
  matching users (with their emails and user IDs) and instruct the user to
  retry with `--by-id` or `--by-email`. This applies to `subscribe`,
  `unsubscribe`, and `channel create --subscribe --by-name`.
- What happens when `--allow-group` is used with a public or web-public channel
  creation? The command MUST reject the request with an error explaining that
  `--allow-group` is only applicable to private channels.
- What happens when a command uses a feature unsupported by the target Zulip
  server version? The system MUST detect the missing capability at runtime and
  return a clear error like "This operation requires Zulip feature level X
  (server has Y)" and exit with a non-zero code. This applies to `unarchive`,
  `--allow-group` (group-based access control), `--topic-policy`, and
  web-public channel type (requires spectator access).
- What happens when a mutation is a no-op (e.g., archiving an already-archived
  channel, subscribing an already-subscribed user)? The command MUST succeed
  silently (exit 0) and, when `--json` is used, return `"status": "success"`.
- What happens when a channel identifier is ambiguous (e.g., a numeric name)?
  The positional channel argument defaults to name interpretation. Users can
  explicitly use `--channel-id` or `--channel-name` flags to disambiguate.
- What happens when a command targets an archived channel without
  `--include-archived`? The command returns a "channel not found" error and
  suggests using `--include-archived` to search archived channels.
- What happens when both `--announce` and `--no-announce` are specified?
  The command rejects the request with an error explaining these flags are
  mutually exclusive.
- What happens when creating a web-public channel on a server without spectator
  access enabled? The command returns a clear error message indicating that
  web-public channels require spectator access and exits with a non-zero code.
- What happens when updating a channel to web-public on a server without
  spectator access? Same as above — feature-level error per FR-019.
- What happens when updating a channel's type from public/web-public to
  private when the channel has no subscribers? The command MUST reject the
  request with an error requiring `--subscribe` or `--allow-group` to prevent
  lockout (same rule as private channel creation in FR-002).

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a `lftools-uv zulip channel list` command that
  returns all active channels (public, web-public, and private) visible to the
  authenticated user. An `--include-archived` flag MUST be supported to include
  archived channels in the output, with archived status clearly indicated.
- **FR-002**: System MUST provide a
  `lftools-uv zulip channel create` command that
  creates a new channel with a specified name, description, and type (public,
  web-public, or private). An `--announce` flag MUST be supported to explicitly
  request an announcement in the server's designated announcement stream; a
  `--no-announce` flag explicitly suppresses it. These are mutually exclusive;
  default behavior (neither flag) follows the API default (no announcement).
  A `--topic-policy` flag MUST be supported with values `allow` (messages
  without a topic are permitted), `deny` (messages must have a topic), or
  `follow-default` (use the server's default setting). If not specified, the
  server default applies. This flag requires runtime feature-level detection
  per FR-019; if the server does not support the topic policy feature, the
  command MUST return a clear feature-level error.
  When creating a private channel, the command MUST require at least
  one `--subscribe USER` (immediate subscriber) or `--allow-group GROUP` (grant
  group-based access permission; members are NOT auto-subscribed). Both flags
  may be combined. The command MUST reject private channel creation if neither
  is specified — the Zulip API does NOT auto-subscribe the requester, so
  without explicit subscribers the channel becomes inaccessible. For public and
  web-public channels, `--subscribe` is optional (anyone can join later) and
  `--allow-group` is not applicable and MUST be rejected if provided.
  `--subscribe USER` MUST use the same `--by-email`/`--by-id`/`--by-name`
  identification mechanism as the subscribe/unsubscribe commands; the identifier
  flag applies to ALL `--subscribe` values in a single invocation (mixing email
  and ID in one command is not permitted). `--by-name` ambiguity follows the
  same fail-with-error behavior as FR-005/FR-006.
  Groups in `--allow-group` are identified by `--group-name` (case-insensitive)
  or `--group-id`.
- **FR-003**: System MUST provide a
  `lftools-uv zulip channel archive` command that
  archives (deactivates) a channel. The command MUST require a `--yes` flag to
  confirm the operation; without it, the command MUST reject the request with an
  explanatory message. Permanent deletion is out of scope as it is not supported
  by the Zulip REST API.
- **FR-004**: System MUST provide a
  `lftools-uv zulip channel update` command that
  can modify a channel's name, description, channel type (public, web-public, or
  private — transitions between all three types are supported where the Zulip
  API allows it), and topic policy (`--topic-policy` with values `allow`,
  `deny`, or `follow-default`). These are the only fields supported for v1; no
  other settings are in scope. The `--topic-policy` flag requires runtime
  feature-level detection per FR-019. When updating a channel's type to
  private, the same lockout prevention rule as FR-002 applies: if the channel
  has NO current subscribers, the command MUST require `--subscribe` or
  `--allow-group` to prevent creating an inaccessible private channel.
- **FR-005**: System MUST provide a `lftools-uv zulip channel subscribe` command
  that subscribes one or more users to a channel, with support for bulk
  operations. Users MUST be identified via an explicit `--by-email`,
  `--by-id`, or `--by-name` flag; the command MUST reject the request if
  none of these flags is provided. `--by-name` matches on the Zulip
  `full_name` field. If `--by-name` matches multiple users, the command MUST
  fail with an ambiguity error listing the matching users (with their emails
  and user IDs) and instruct the user to use `--by-id` or `--by-email`.
- **FR-006**: System MUST provide a
  `lftools-uv zulip channel unsubscribe` command
  that unsubscribes one or more users from a channel, with support for bulk
  operations. Users MUST be identified via an explicit `--by-email`,
  `--by-id`, or `--by-name` flag; the command MUST reject the request if
  none of these flags is provided. `--by-name` matches on the Zulip
  `full_name` field. If `--by-name` matches multiple users, the command MUST
  fail with an ambiguity error listing the matching users (with their emails
  and user IDs) and instruct the user to use `--by-id` or `--by-email`.
- **FR-007**: System MUST provide a
  `lftools-uv zulip channel subscribers` command
  that lists all subscribers of a specific channel.
- **FR-008**: All commands (listing and mutation) MUST support two output
  formats: a default human-readable format and a `--json` flag for structured
  JSON output suitable for scripting and automation pipelines. Mutation commands
  MUST follow a consistent JSON schema:
  - Single mutations, success/no-op: `{"status": "success",
    "channel_id": int, "channel_name": str, "operation": str,
    ...operation-specific fields}`
  - Single mutations, error: `{"status": "error",
    "channel_id": null, "channel_name": str,
    "operation": str, ...operation-specific fields}` —
    `channel_id` is `null` when the target channel cannot be
    resolved.
  - Bulk operations (subscribe/unsubscribe), success/partial:
    `{"status": "partial"|"success", "channel_id": int,
    "channel_name": str, "operation":
    "subscribe"|"unsubscribe", "results": [...],
    "errors": [...]}`
  - Bulk operations, error: `{"status": "error",
    "channel_id": null, "channel_name": str, "operation":
    "subscribe"|"unsubscribe", "results": [...],
    "errors": [...]}` — `channel_id` is `null` when the
    target channel cannot be resolved.
  - `"status": "partial"` indicates some operations succeeded
    and some failed.
  - Listing commands MUST produce `--json` output as a JSON
    object wrapping an array of entity objects (e.g.,
    `{"channels": [...]}`, `{"users": [...]}`,
    `{"groups": [...]}`). Each entity object contains the
    fields described in its respective FR.
- **FR-009**: System MUST implement a separate reusable API layer that wraps
  Zulip channel operations, maintaining separation between API logic and CLI
  presentation.
- **FR-010**: The CLI layer MUST catch exceptions raised by the API layer, log
  meaningful error messages, and exit with non-zero exit codes on failure.
- **FR-011**: System MUST resolve Zulip configuration using the following
  precedence order: `--zuliprc PATH` CLI flag (pointing to a zuliprc-format
  file) > `./zuliprc` (current working directory) > `[zulip]` section in
  `lftools.ini` > `~/.zuliprc`.
- **FR-012**: The `[zulip]` section in `lftools.ini` MUST support the same
  configuration fields as a standard zuliprc file (email, key, site).
- **FR-013**: System MUST use an official supported Zulip client library for
  all API interactions.
- **FR-014**: The archive command performs a reversible deactivation. Permanent
  deletion is out of scope (Zulip API limitation).
- **FR-015**: System MUST provide a
  `lftools-uv zulip user list` command that returns all active
  human users on the Zulip server with their full name, email
  address, and user ID. The command MUST support
  `--include-bots` to include bot accounts and
  `--include-deactivated` to include deactivated users. The
  command MUST support `--json` output producing
  `{"users": [...]}` where each entry contains `user_id`
  (int), `full_name` (str), `email` (str), `is_bot` (bool),
  and `is_active` (bool).
- **FR-016**: System MUST provide a
  `lftools-uv zulip group list` command that returns all user
  groups on the Zulip server with their name, group ID,
  description, and member count. Groups MUST be identifiable
  by `--group-name` (case-insensitive) or `--group-id` in
  commands that reference them (e.g., `--allow-group`). If a
  group name is ambiguous, the command MUST fail with an error
  instructing the user to specify by `--group-id`. The command
  MUST support `--json` output producing `{"groups": [...]}`
  where each entry contains `group_id` (int), `name` (str),
  `description` (str), and `member_count` (int).
- **FR-017**: System MUST provide a `lftools-uv zulip channel unarchive` command
  that reactivates a previously archived channel. The command MUST require a
  `--yes` flag to confirm the operation; without it, the command MUST reject the
  request with an explanatory message.
- **FR-018**: All channel commands that target a specific channel MUST
  accept the channel as a positional argument interpreted as a channel
  name by default, even if numeric-looking. `--channel-id` MUST be
  supported to target a channel by numeric ID; `--channel-name` MAY
  be used for explicitness but is not required for disambiguation.
  Channel name matching MUST be case-insensitive. (Zulip channel
  names are case-insensitively unique, so no ambiguity handling is
  needed for channels.)
  Channel target resolution searches active channels only by default; an
  `--include-archived` flag extends the search to include archived channels.
  Commands where targeting archived channels is the primary use case (e.g.,
  `unarchive`) require `--include-archived` to locate the target. When a
  channel is not found and `--include-archived` was not specified, the error
  message MUST suggest using `--include-archived`.
- **FR-019**: Commands that rely on Zulip features not universally available
  (e.g., unarchive, group-based access control, topic policy, web-public
  channels) MUST detect server capabilities at runtime via the Zulip API
  feature level. If a required feature is unsupported, the command MUST return
  a clear error message in the format "This operation requires Zulip feature
  level X (server has Y)" and exit with a non-zero exit code. No minimum Zulip
  server version is required. Web-public channels specifically require spectator
  access to be enabled on the server/organization.
- **FR-020**: All mutation commands MUST be idempotent for no-op cases:
  archiving an already-archived channel, unarchiving an already-active channel,
  subscribing an already-subscribed user, unsubscribing a user who is not
  subscribed, and updating with values identical to the current state MUST all
  succeed silently (exit 0). When `--json` is used, no-ops MUST return
  `"status": "success"`.

### Key Entities

- **Channel (Stream)**: Represents a Zulip channel with attributes including
  name, description, type (public/web-public/private), topic policy
  (allow/deny/follow-default), archived status, subscriber count, and channel
  ID. Zulip's API refers to these as "streams" internally. Identifiable by
  positional name argument (case-insensitive) or explicit `--channel-id`/
  `--channel-name` flags for disambiguation.
- **Subscriber**: A Zulip user who is a member of a channel, identified by email
  address, user ID, and full name.
- **Zulip User**: A user account on the Zulip server, identified by full name,
  email address, user ID, and active/deactivated status. Used for user discovery
  prior to channel subscription management. Zulip has no stable "username"
  field; `full_name` is used for name-based identification via `--by-name`.
- **User Group**: A named group of Zulip users, identified by `--group-id` or
  `--group-name` (case-insensitive), with description and member count. Used for
  group-based access control when creating private channels via `--allow-group`.
  Groups granted access are permitted to join but are NOT automatically
  subscribed.
- **Zulip Configuration**: Connection and authentication details (server URL,
  bot email, API key) resolved from multiple sources with defined precedence:
  `--zuliprc PATH` > `./zuliprc` > `[zulip]` in lftools.ini > `~/.zuliprc`.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Administrators can list all visible active channels on a Zulip
  server in under 5 seconds for servers with up to 500 channels.
- **SC-002**: Administrators can create, update, archive, and unarchive channels
  in a single CLI invocation without needing to use the Zulip web interface.
- **SC-003**: Administrators can subscribe or unsubscribe up to 50 users in a
  single command invocation.
- **SC-004**: All commands produce a non-zero exit code on any error condition,
  enabling reliable use in automated scripts and CI pipelines. No-op mutations
  (idempotent cases) produce exit code 0.
- **SC-005**: All error messages clearly identify the problem (connection
  failure, authentication error, permission denied, invalid input, unsupported
  server feature level) so that administrators can resolve issues without
  consulting external documentation.
- **SC-006**: JSON output from all commands is valid, parseable JSON that
  can be consumed directly by standard JSON parsers and CLI tooling without
  modification. Mutation commands follow the standard schema defined in
  FR-008, returning at minimum `status`, `channel_id`, `channel_name`,
  and `operation`.
- **SC-007**: Configuration setup requires no more than one file edit (either
  zuliprc or lftools.ini) to begin using all channel management commands.
- **SC-008**: Administrators can list all users on the Zulip server in under 5
  seconds for servers with up to 5,000 users, enabling quick user discovery for
  subscription workflows.

## Assumptions

- The Zulip server being managed is accessible over the network from the machine
  running lftools-uv.
- The authenticated user (via zuliprc or lftools.ini) has sufficient Zulip
  permissions (typically organization administrator) to perform channel
  management operations.
- Only a single Zulip server needs to be managed per command invocation; multi-
  server support is out of scope.
- An official supported Zulip client library will be added as a project
  dependency.
- The implementation will integrate with existing lftools-uv API and CLI
  conventions for exposing commands and Zulip operations.
- Channel operations use Zulip's REST API v1, which uses the term "streams"
  internally; the CLI uses the user-facing term "channels" for clarity.
- The Zulip client library handles HTTP connection management, retries,
  and rate limiting internally.
- Human-readable table output will use a format consistent with other lftools
  listing commands.
- Zulip has no stable "username" field; the `full_name` field is used for
  name-based user identification via `--by-name`. Since `full_name` is not
  unique, ambiguity is handled by failing with a clear error.
- The Zulip API does NOT auto-subscribe the requester on channel creation. The
  `principals` parameter must explicitly include users to subscribe. Without
  explicit subscribers, no one is subscribed to the new channel. This makes the
  lockout prevention policy for private channels critical — an empty private
  channel is inaccessible to everyone including the creator.
- No minimum Zulip server version is required. Features that depend on newer
  Zulip capabilities (e.g., unarchive, group-based access, topic policy,
  web-public channels) are detected at runtime via the Zulip API feature level
  and degrade gracefully with clear error messages.
- Zulip channel names are case-insensitively unique on the server, so channel
  name lookups are unambiguous.
- Identifier flag namespaces are split by entity type: channels use positional
  arg (defaults to name) plus `--channel-id`/`--channel-name` for
  disambiguation; groups use `--group-id`/`--group-name`; users use
  `--by-email`/`--by-id`/`--by-name`. This prevents cross-entity ambiguity.
- The Zulip API `announce` parameter defaults to `false` (no announcement on
  channel creation). The CLI mirrors this default; `--announce` must be
  explicitly specified to request an announcement.
