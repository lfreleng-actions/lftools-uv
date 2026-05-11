<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# CLI Command Contracts: Zulip Channel Management

This document defines the public CLI interface contracts for all Zulip
channel management commands.

## Optional Dependency

The `zulip` command group requires the `zulip` optional extra. Install
with `pip install "lftools-uv[zulip]"` or `uv pip install "lftools-uv[zulip]"`.
When the extra is not installed, the command group still appears in CLI
help but running any subcommand produces a user-friendly error:

```text
Zulip support requires the zulip extra. Install with:
  pip install "lftools-uv[zulip]"
```

## Global Options (all zulip commands)

| Option         | Type   | Required | Description                             |
|----------------|--------|----------|-----------------------------------------|
| `--zuliprc`    | PATH   | No       | Path to zuliprc configuration file      |
| `--json`       | flag   | No       | Output in JSON format                   |

---

## `lftools-uv zulip channel list`

**Description**: List channels visible to the authenticated user.

| Option               | Type | Required | Description                         |
|----------------------|------|----------|-------------------------------------|
| `--include-archived` | flag | No       | Include archived channels in output |

**Human Output**: Table with columns: Name, Description, Type, Subscribers,
Status (if `--include-archived`).

**JSON Output**:

```json
{
  "channels": [
    {
      "stream_id": 1,
      "name": "general",
      "description": "General discussion",
      "type": "public",
      "subscriber_count": 42,
      "is_archived": false
    }
  ]
}
```

**Exit Codes**: 0 = success, 1 = error (config/connection/permission)

---

## `lftools-uv zulip channel create <name>`

**Description**: Create a new channel.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | positional | Yes | Channel name |
| `--description` | str | No | Channel description |
| `--type` | choice | No (public) | public/web-public/private |
| `--subscribe` | str (multi) | Conditional | Users to subscribe |
| `--by-email` | flag | Conditional | Identify users by email |
| `--by-id` | flag | Conditional | Identify users by ID |
| `--by-name` | flag | Conditional | Identify users by name |
| `--allow-group` | str | Conditional | Groups allowed to join |
| `--can-remove-subscribers-group` | str | No | Subscriber removal perm |
| `--announce` | flag | No | Post announcement |
| `--no-announce` | flag | No | Suppress announcement |
| `--topic-policy` | choice | No | allow/deny/follow-default |

**`--allow-group` conditional requirement**: Required (either this with a
non-Nobody group, or `--subscribe`) when creating private channels, to
prevent admin lockout from the newly created channel.

**`--allow-group` and `--can-remove-subscribers-group` syntax**: Both
flags accept a comma-separated, quoted string. Each item is interpreted
as a group name by default. Use `id:NUM` prefix to force ID lookup.
Both system role groups (Owners, Administrators, Moderators, Full
Members, Members, Everyone, Nobody) and custom user groups are valid
inputs. System role groups are standard Zulip user groups with numeric
IDs — the CLI resolves them via the same path as custom groups:
display name → groups API lookup → numeric group ID → group-setting
value payload. System groups are discovered via the `is_system_group`
property on the group object returned by `GET /user_groups`. There is
no separate "role token" path at the API level. Users never type
`role:` prefixes. `Nobody` effectively disables a permission. Examples:

- `--allow-group 'foo, bar, id:123'`
- `--allow-group 'Administrators, Members'` (system role groups)
- `--allow-group 'Nobody'` (disables the permission)
- `--can-remove-subscribers-group 'baz, admin'`

**API Translation**: The CLI resolves each comma-separated group
name/ID to a numeric group ID, then translates to the Zulip API
"group-setting value" format:

- Single group → simple integer (e.g., `42`)
- Multiple groups → complex form:
  `{"direct_members": [], "direct_subgroups": [id1, id2, ...]}`

**Create payload**: Permission fields send the raw group-setting value
directly (integer or complex object) to the POST endpoint.

This translation is transparent to the user.

**Constraints**:

- Private channels MUST specify `--subscribe` or `--allow-group`.
  Note: `--allow-group 'Nobody'` does NOT satisfy lockout prevention
  for private channels — it disables the permission entirely, leaving
  no path for anyone to join. The CLI rejects this combination with an
  error explaining the lockout risk.
- `--allow-group` is valid on ALL channel types (unified semantics: "who
  can join"); server enforces on private, accepts-but-does-not-enforce on
  public/web-public. Maps to Zulip API field `can_access_group`.
- `--can-remove-subscribers-group` is valid on ALL channel types. Maps to
  Zulip API field `can_remove_subscribers_group`. Requires minimum
  feature level (threshold hardcoded during implementation, checked at
  runtime against server's reported level) per FR-019.
- `--subscribe` requires exactly one of `--by-email`/`--by-id`/`--by-name`
- `--announce` and `--no-announce` are mutually exclusive
- `--topic-policy` requires minimum Zulip feature level (threshold
  hardcoded during implementation, checked at runtime against server's
  reported level)
- `--type web-public` requires minimum Zulip feature level (threshold
  hardcoded during implementation, checked at runtime against server's
  reported level) + spectator access

**JSON Output** (success):

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "new-project",
  "operation": "create",
  "type": "public"
}
```

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip channel update [channel]`

**Description**: Update channel settings.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `channel` | positional | No | Channel name (optional if --channel-id) |
| `--channel-id` | int | No | Target by numeric ID |
| `--name` | str | No | New channel name |
| `--description` | str | No | New channel description |
| `--type` | choice | No | public/web-public/private |
| `--topic-policy` | choice | No | allow/deny/follow-default |
| `--subscribe` | str (multi) | Conditional | For private w/o subs |
| `--by-email` | flag | Conditional | Identify users by email |
| `--by-id` | flag | Conditional | Identify users by ID |
| `--by-name` | flag | Conditional | Identify users by name |
| `--allow-group` | str | Conditional | Groups allowed to join |
| `--can-remove-subscribers-group` | str | No | Subscriber removal perm |
| `--include-archived` | flag | No | Search archived channels |

**`--allow-group` and `--can-remove-subscribers-group` syntax**: Same
comma-separated inline syntax as `channel create` (see above). Both
flags translate to group-setting value objects for the Zulip API.
**Update payload**: Permission fields use the group-setting-update
wrapper format: `{"new": <group-setting-value>}`. The `old` field is
omitted (the CLI syncs desired state, not incremental edits). The CLI
wraps automatically; user syntax is identical to `channel create`.

**Constraints**:

- Exactly one of `[channel]` (positional) or `--channel-id` must be
  provided — if neither or both are given, the CLI errors
- At least one setting change must be specified
- `--subscribe` requires exactly one of `--by-email`/`--by-id`/`--by-name`
- Updating to `private` with 0 subscribers requires at least one
  `--subscribe` target OR a non-Nobody `--allow-group` (lockout
  prevention). `--allow-group 'Nobody'` does NOT satisfy this
  requirement — it disables the permission entirely, leaving no path
  for anyone to join.
- `--allow-group` is valid on ALL channel types (unified semantics).
  Maps to Zulip API field `can_access_group`.
- `--can-remove-subscribers-group` is valid on ALL channel types. Maps to
  Zulip API field `can_remove_subscribers_group`. Requires minimum
  feature level (threshold hardcoded during implementation, checked at
  runtime against server's reported level) per FR-019.
- `--topic-policy` requires minimum Zulip feature level (threshold
  hardcoded during implementation, checked at runtime against server's
  reported level)
- `--type web-public` requires minimum Zulip feature level (threshold
  hardcoded during implementation, checked at runtime against server's
  reported level) + spectator access

**JSON Output** (success):

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "renamed-project",
  "operation": "update"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## `lftools-uv zulip channel archive [channel]`

**Description**: Archive (deactivate) a channel.

| Argument/Option      | Type       | Required | Description              |
|----------------------|------------|----------|--------------------------|
| `channel`            | positional | No       | Channel name (see below) |
| `--channel-id`       | int        | No       | Target by ID             |
| `--yes`              | flag       | Yes      | Confirm archival         |
| `--include-archived` | flag       | No       | Search archived channels |

**Constraints**:

- Exactly one of `[channel]` (positional) or `--channel-id` must be
  provided — if neither or both are given, the CLI errors

**JSON Output** (success):

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "old-project",
  "operation": "archive"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## `lftools-uv zulip channel unarchive [channel]`

**Description**: Reactivate an archived channel.

| Argument/Option      | Type       | Required | Description              |
|----------------------|------------|----------|--------------------------|
| `channel`            | positional | No       | Channel name (see below) |
| `--channel-id`       | int        | No       | Target by ID             |
| `--yes`              | flag       | Yes      | Confirm unarchival       |
| `--include-archived` | flag       | No       | Search archived channels |

**Note on `--include-archived`**: Optional, but needed in practice to
find archived channels by name. Without it, target resolution searches
active channels only and fails with a helpful error suggesting the flag
(e.g., "Channel 'foo' not found. Use --include-archived to search
archived channels.").

**Constraints**:

- Exactly one of `[channel]` (positional) or `--channel-id` must be
  provided — if neither or both are given, the CLI errors
- Requires minimum Zulip feature level (threshold hardcoded during
  implementation, checked at runtime against server's reported level)

**JSON Output** (success):

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "restored-project",
  "operation": "unarchive"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## `lftools-uv zulip channel subscribe [channel] USER [USER...]`

**Description**: Subscribe users to a channel.

| Argument/Option      | Type       | Required    | Description             |
|----------------------|------------|-------------|-------------------------|
| `channel`            | positional | No          | Channel name (see below)|
| `USER`               | positional | Yes         | User identifier(s)      |
| `--channel-id`       | int        | No          | Target channel by ID    |
| `--by-email`         | flag       | Conditional | Identify by email       |
| `--by-id`            | flag       | Conditional | Identify by user ID     |
| `--by-name`          | flag       | Conditional | Identify by name        |
| `--include-archived` | flag       | No          | Search archived channels|

**Constraints**:

- Exactly one of `[channel]` (positional) or `--channel-id` must be
  provided — if neither or both are given, the CLI errors.
  The CLI signature is: `subscribe [channel] USER [USER...]`. When
  `--channel-id` is given, ALL positionals are USER values. When
  `--channel-id` is absent, the first positional is the channel name
  and remaining positionals are USER values.
- Exactly one of `--by-email`/`--by-id`/`--by-name` required

**JSON Output** (bulk):

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "general",
  "operation": "subscribe",
  "results": [
    {"user": "alice@example.com", "status": "subscribed"}
  ],
  "errors": []
}
```

**Exit Codes**: 0 = all succeeded (including no-ops), 1 = any error

---

## `lftools-uv zulip channel unsubscribe [channel] USER [USER...]`

**Description**: Unsubscribe users from a channel.

Same interface as `subscribe` but with `"operation": "unsubscribe"`.
Same `[channel]`/`--channel-id` constraint applies.

**Exit Codes**: 0 = all succeeded (including no-ops), 1 = any error

---

## `lftools-uv zulip channel subscribers [channel]`

**Description**: List subscribers of a channel.

| Argument/Option      | Type       | Required | Description              |
|----------------------|------------|----------|--------------------------|
| `channel`            | positional | No       | Channel name (see below) |
| `--channel-id`       | int        | No       | Target by ID             |
| `--include-archived` | flag       | No       | Search archived channels |

**Constraints**:

- Exactly one of `[channel]` (positional) or `--channel-id` must be
  provided — if neither or both are given, the CLI errors

**Human Output**: Table with columns: Full Name, Email, User ID.

**JSON Output**:

```json
{
  "subscribers": [
    {
      "user_id": 10,
      "full_name": "Alice Smith",
      "email": "alice@example.com"
    }
  ]
}
```

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip channel topic-policy [channel]`

**Description**: View or set the topic editing policy for a channel.
Convenience shortcut equivalent to
`channel update [channel] --topic-policy <value>`.

| Argument/Option      | Type       | Required | Description              |
|----------------------|------------|----------|--------------------------|
| `channel`            | positional | No       | Channel name (see below) |
| `--channel-id`       | int        | No       | Target by numeric ID     |
| `--policy`           | choice     | No       | allow/deny/follow-default|
| `--include-archived` | flag       | No       | Search archived channels |

**Constraints**:

- Exactly one of `[channel]` (positional) or `--channel-id` must be
  provided — if neither or both are given, the CLI errors
- If `--policy` is omitted: displays the current topic policy setting
- If `--policy` is provided: updates the topic policy
- Invalid `--policy` values are rejected with an error listing valid
  options (`allow`, `deny`, `follow-default`)
- Requires minimum Zulip feature level (threshold hardcoded during
  implementation, checked at runtime against server's reported level);
  returns a clear feature-level error if unsupported

**Human Output** (read mode — no `--policy`): Plain text showing the
current policy value for the target channel.

**JSON Output** (read mode):

```json
{
  "channel_id": 42,
  "channel_name": "general",
  "topic_policy": "allow"
}
```

**JSON Output** (write mode — `--policy` provided):

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "general",
  "operation": "topic-policy",
  "topic_policy": "deny"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## `lftools-uv zulip user list`

**Description**: List users on the Zulip server.

| Option                  | Type | Required | Description               |
|-------------------------|------|----------|---------------------------|
| `--include-bots`        | flag | No       | Include bot accounts      |
| `--include-deactivated` | flag | No       | Include deactivated users |

**Human Output**: Table with columns: Full Name, Email, User ID,
(Bot/Deactivated indicators when included).

**JSON Output**:

```json
{
  "users": [
    {
      "user_id": 10,
      "full_name": "Alice Smith",
      "email": "alice@example.com",
      "is_bot": false,
      "is_active": true
    }
  ]
}
```

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip group list`

**Description**: List user groups on the Zulip server (both custom user
groups and built-in system role groups).

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--group-name` | str | No | Filter by name (case-insensitive) |
| `--group-id` | int | No | Filter by group ID |

**Human Output**: Table with columns: Name, Group ID, Type, Description,
Members.

**JSON Output**:

```json
{
  "groups": [
    {
      "group_id": 5,
      "name": "engineering",
      "description": "Engineering team",
      "member_count": 15,
      "type": "custom"
    },
    {
      "group_id": 1,
      "name": "Administrators",
      "description": "Administrators of this organization",
      "member_count": 3,
      "type": "system"
    }
  ]
}
```

**Notes**:

- System role groups (Owners, Administrators, Moderators, Full Members,
  Members, Everyone, Nobody) are listed alongside custom groups with
  `"type": "system"`. All groups have numeric IDs and are resolved via
  the same lookup path (display name → groups API → numeric ID). All
  listed groups are valid inputs for `--allow-group` and
  `--can-remove-subscribers-group`.
- `--group-name`/`--group-id` are scoped to filtering this listing only.
  In permission flag contexts (`--allow-group`,
  `--can-remove-subscribers-group`), groups are identified inline via
  comma-separated values with `id:` prefix disambiguation.
- If `--group-name` matches multiple groups (case-insensitive), the
  command MUST fail with an ambiguity error listing matching groups
  (with IDs) and instruct the user to use `--group-id` instead.

**Exit Codes**: 0 = success, 1 = error
