<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Data Model: Zulip Channel Management

## Entities

### Channel (Stream)

Represents a Zulip channel (internally called a "stream" in the Zulip API).

| Field | Type | Description |
| --- | --- | --- |
| `stream_id` | `int` | Zulip internal stream ID (unique) |
| `name` | `str` | Channel name (case-insensitive unique) |
| `description` | `str` | Channel description (may be empty) |
| `type` | `str (enum)` | Visibility: public/web-public/private |
| `topic_policy` | `str \| None` | Policy: allow/deny/follow-default |
| `is_archived` | `bool` | Channel is deactivated/archived |
| `subscriber_count` | `int` | Number of current subscribers |
| `can_access_group` | `GroupSettingValue \| None` | Access perm group |
| `can_remove_subscribers_group` | `GroupSettingValue \| None` | Removal perm |

**GroupSettingValue** (Zulip API "group-setting value"):

The Zulip API represents group-based permissions as a "group-setting
value" — either a simple integer (single group) or a complex object
(multiple groups):

- **Simple form**: `int` — a single user group ID
- **Complex form**: `{"direct_members": [], "direct_subgroups": [id1, id2, ...]}`

**CLI Translation**: comma-separated group names/IDs on the command line
→ resolve each to a numeric group ID → if one group, send simple int;
if multiple, send complex form with all IDs in `direct_subgroups` and
empty `direct_members`.

**Validation Rules**:

- `name` MUST NOT be empty
- `name` is case-insensitively unique on the server
- `type` must be one of the three supported values
- `topic_policy` requires minimum Zulip feature level (threshold
  hardcoded during implementation, checked at runtime against server's
  reported level)
- `web-public` type requires minimum Zulip feature level (threshold
  hardcoded during implementation, checked at runtime against server's
  reported level) and spectator access enabled
- `can_remove_subscribers_group` requires minimum Zulip feature level
  (threshold hardcoded during implementation, checked at runtime against
  server's reported level) per FR-019

**State Transitions**:

```text
┌──────────┐   archive    ┌──────────┐
│  Active  │─────────────▶│ Archived │
│          │◀─────────────│          │
└──────────┘  unarchive   └──────────┘
      (min FL, hardcoded at impl)
```

**Type Transitions** (all supported where API allows):

```text
public ↔ private
public ↔ web-public
web-public ↔ private
```

Lockout prevention: Transitioning to `private` when `subscriber_count == 0`
requires at least one `--subscribe` target OR a non-Nobody `--allow-group`.
`--allow-group 'Nobody'` does NOT satisfy lockout prevention — it disables the
permission entirely, leaving no path for anyone to join.

---

### ZulipUser

Represents a user account on the Zulip server.

| Field       | Type   | Description                                     |
|-------------|--------|-------------------------------------------------|
| `user_id`   | `int`  | Zulip's internal user ID (unique)               |
| `full_name` | `str`  | Display name (NOT unique — may be ambiguous)    |
| `email`     | `str`  | Email address (unique)                          |
| `is_bot`    | `bool` | Whether this is a bot account                   |
| `is_active` | `bool` | Whether the account is active (not deactivated) |

**Validation Rules**:

- `full_name` is NOT unique — commands using `--by-name` must handle ambiguity
- `email` is unique and preferred for unambiguous identification
- `user_id` is unique and stable

**Identification Modes** (for `--subscribe`/`--unsubscribe`):

| Flag         | Resolves via | Ambiguity possible?   |
|--------------|--------------|-----------------------|
| `--by-email` | `email`      | No (unique)           |
| `--by-id`    | `user_id`    | No (unique)           |
| `--by-name`  | `full_name`  | Yes — fail with error |

---

### UserGroup

Represents a named group of Zulip users (custom or system role group).

| Field          | Type         | Description                             |
|----------------|--------------|-----------------------------------------|
| `group_id`     | `int`        | Zulip's internal group ID (unique)      |
| `name`         | `str`        | Group name (case-insensitively unique*) |
| `description`  | `str`        | Group description                       |
| `member_count` | `int`        | Number of members in the group          |
| `type`         | `str (enum)` | `custom` or `system`                    |

*Note: Group name uniqueness is case-insensitive per Zulip server behavior,
but ambiguity handling is still required per spec. The error message is
context-specific:

- In `group list` context: fail with error listing matches and instruct
  the user to use `--group-id` flag instead.
- In permission flag context (`--allow-group`,
  `--can-remove-subscribers-group`): fail with error listing matches and
  instruct use of `id:NUM` prefix syntax.

**System Role Groups**: Built-in groups (Owners, Administrators, Moderators,
Full Members, Members, Everyone, Nobody) are listed with `type: system`. They
have numeric IDs just like custom groups and are usable in `--allow-group` and
`--can-remove-subscribers-group`. Users specify system role groups by display
name only (case-insensitive). System groups are identified by the
`is_system_group: true` property on the group object and use the `role:`
naming convention internally. The display-name-to-API-name mapping is:

- "Owners" → group with API name `role:owners`
- "Administrators" → group with API name `role:administrators`
- "Moderators" → group with API name `role:moderators`
- "Full Members" → group with API name `role:fullmembers`
- "Members" → group with API name `role:members`
- "Everyone" → group with API name `role:everyone`
- "Nobody" → group with API name `role:nobody`

The CLI resolution path is: display name → known mapping → find group
object in API response → extract numeric group ID → group-setting value
payload. There is no separate "role token" path at the API level — the
`role:` prefix is purely internal Zulip nomenclature; the API uses numeric
IDs for all groups regardless of type. Users do NOT type `role:` prefixes —
display names are the only accepted form. `Nobody` effectively
disables a permission.

**Create vs Update Payload Shapes**: The group-setting value is sent
differently depending on the endpoint:

- **Create** (POST): raw group-setting value (integer or complex object)
- **Update** (PATCH): `{"new": <group-setting-value>}` (old omitted)

The CLI handles this wrapping automatically; user syntax is the same
for both operations.

**Identification Modes**:

In `group list` filtering:

| Flag           | Resolves via | Ambiguity possible?   |
|----------------|--------------|-----------------------|
| `--group-name` | `name`       | Yes — fail with error |
| `--group-id`   | `group_id`   | No (unique)           |

In permission flags (`--allow-group`, `--can-remove-subscribers-group`):

Groups are identified inline via a comma-separated, quoted string value.
Each item is interpreted as a group name by default. Prefix syntax:

| Prefix    | Meaning                                  | Example      |
|-----------|------------------------------------------|--------------|
| (none)    | Interpret as group name                  | `foo`        |
| `id:`     | Force ID lookup                          | `id:123`     |

Examples:

- `--allow-group 'foo, bar, id:123'`
- `--can-remove-subscribers-group 'baz, admin'`

---

### ZulipConfig

Represents resolved Zulip connection configuration.

| Field     | Type  | Description                |
|-----------|-------|----------------------------|
| `email`   | `str` | Bot/user email for auth    |
| `api_key` | `str` | API key for authentication |
| `site`    | `str` | Zulip server URL           |

**Resolution Precedence** (first match wins):

1. `--zuliprc PATH` CLI flag
2. `./zuliprc` (current working directory)
3. `[zulip]` section in `lftools.ini`
4. `~/.zuliprc`

---

### MutationResult

Standard response schema for mutation operations.

| Field          | Type          | Description                     |
|----------------|---------------|---------------------------------|
| `status`       | `str (enum)`  | Outcome: success/error/partial  |
| `channel_id`   | `int \| None` | Channel ID (None if unresolved) |
| `channel_name` | `str`         | Target channel name             |
| `operation`    | `str`         | Operation performed             |

**Extended for bulk operations** (subscribe/unsubscribe):

| Field     | Type         | Description                      |
|-----------|--------------|----------------------------------|
| `results` | `list[dict]` | Successful individual operations |
| `errors`  | `list[dict]` | Failed individual operations     |

---

## Relationships

```text
Channel 1──────* Subscriber (ZulipUser)
Channel *──────* UserGroup (via --allow-group, all types)
Channel *──────* UserGroup (via --can-remove-subscribers-group, all types)
ZulipConfig 1──── Client Session
```

- A Channel has zero or more Subscribers (ZulipUser instances)
- A Channel may have zero or more allowed UserGroups (via `--allow-group` /
  `can_access_group`) — enforced on private, accepted on public/web-public
- A Channel may have a subscriber-removal permission group (via
  `--can-remove-subscribers-group` / `can_remove_subscribers_group`) —
  valid on ALL channel types
- A ZulipConfig produces one authenticated client session
