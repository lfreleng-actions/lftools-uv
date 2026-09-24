<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- command contracts require exact strings -->

# CLI Command Contracts: Zulip Show Commands

This document defines the public interface for read-only Zulip show commands.
All commands use existing Zulip global options such as `--zuliprc` and support
the hidden `--json` convention.

## Shared Output Contract

Human detail output uses two table styles:

```text
Field | Value | Settable | Notes
```

and, for nested lists:

```text
Section-specific columns, for example Full Name | Email | User ID
```

Settable values are ASCII-safe:

- `via --flag` for fields writable by the current CLI
- `via command` for fields writable by an existing subcommand rather than a
  single flag
- `not exposed` for server-settable fields without a current write flag or
  command
- `no` for read-only or derived fields

`--no-resolve` help text MUST state: "Skip extra lookup calls and render raw
IDs where possible. Target lookup still runs as needed."

All errors go to stderr and exit with code 1. Successful show commands exit 0.

---

## `lftools-uv zulip channel show [channel]`

**Description**: Show complete details for one channel.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `channel` | positional | One of channel/channel-id | Channel name, even if numeric-looking |
| `--channel-id` | int | One of channel/channel-id | Target channel by numeric ID |
| `--include-archived` | flag | No | Search archived channels |
| `--no-resolve` | flag | No | Skip extra folder, user, and group lookup calls |
| `--json` | flag | No | Emit machine-readable JSON |

**Human Output**:

Primary table headers: `Field`, `Value`, `Settable`, `Notes`.

Required derived rows when raw data exists:

- `type`: `public`, `private`, or `web-public`
- `folder`: resolved folder name and ID, or raw `folder_id` with
  `--no-resolve`
- permission group rows for every returned channel group-setting permission:
  `can_subscribe_group`, `can_remove_subscribers_group`,
  `can_add_subscribers_group`, `can_administer_channel_group`,
  `can_send_message_group`, `can_delete_any_message_group`,
  `can_delete_own_message_group`, `can_move_messages_out_of_channel_group`,
  `can_move_messages_within_channel_group`, `can_resolve_topics_group`, and
  `can_create_topic_group`
- all other raw stream fields returned by the server

**JSON Output**:

```json
{
  "channel": {
    "stream_id": 42,
    "name": "general",
    "description": "General discussion",
    "invite_only": false,
    "is_web_public": false,
    "folder_id": 10,
    "topics_policy": "inherit",
    "can_subscribe_group": 22,
    "subscriber_count": 150
  },
  "derived": {
    "type": "public"
  },
  "resolved": {
    "folder": {"id": 10, "name": "Projects"},
    "creator": {"user_id": 5, "full_name": "Alice Admin"},
    "groups": {
      "can_subscribe_group": {
        "raw": 22,
        "direct_members": [],
        "direct_subgroups": [22],
        "resolved_members": [],
        "resolved_groups": [{"group_id": 22, "name": "Members"}],
        "display": "Members"
      }
    }
  },
  "annotations": {
    "description": {"status": "via --flag", "setter": "--description"},
    "can_add_subscribers_group": {"status": "not exposed", "setter": null}
  }
}
```

With `--no-resolve`, `resolved` MAY be `{}` or contain only data available from
the raw target object.

**Errors**:

```text
Error: Exactly one of channel or --channel-id is required
Error: --channel-id must be a numeric channel ID.
Error: Channel 'old' is archived. Use --include-archived to operate on archived channels.
Error: Channel 'missing' not found
```

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip group show [group]`

**Description**: Show complete details for one user group, including members.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `group` | positional | One target mechanism | Group name shorthand |
| `--group-name` | str | One target mechanism | Group name, case-insensitive |
| `--group-id` | int | One target mechanism | Group ID |
| `--no-resolve` | flag | No | Skip user and subgroup lookup calls |
| `--json` | flag | No | Emit machine-readable JSON |

Exactly one of positional `group`, `--group-name`, or `--group-id` is required.
A numeric-looking positional group is treated as a name; use `--group-id` for ID
lookup.

**Human Output**:

Primary table headers: `Field`, `Value`, `Settable`, `Notes`.

Member table headers with resolution enabled: `Full Name`, `Email`, `User ID`.

Member table headers with `--no-resolve`: `User ID`.

Direct subgroup table headers with resolution enabled: `Name`, `Group ID`,
`Type`.

Direct subgroup table headers with `--no-resolve`: `Group ID`.

**JSON Output**:

```json
{
  "group": {
    "id": 10,
    "name": "engineering",
    "description": "Engineering team",
    "members": [1, 2],
    "direct_subgroup_ids": [20],
    "deactivated": false
  },
  "derived": {
    "display_name": "engineering",
    "type": "custom",
    "member_count": 2
  },
  "resolved": {
    "members": [
      {"user_id": 1, "full_name": "Alice", "email": "alice@example.com"}
    ],
    "direct_subgroups": [
      {"group_id": 20, "name": "Members", "type": "system"}
    ]
  },
  "annotations": {
    "members": {"status": "not exposed", "setter": null},
    "can_manage_group": {"status": "not exposed", "setter": null}
  }
}
```

**Errors**:

```text
Error: Exactly one group target is required
Error: Group name 'design' matched 2 groups; use --group-id to disambiguate
Error: No user group with id 999
Error: No user group named 'missing'
```

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip user show USER`

**Description**: Show complete details for one user account.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `USER` | positional | Yes | Email, user ID, or full name according to mode |
| `--by-email` | flag | One required | Resolve USER by email |
| `--by-id` | flag | One required | Resolve USER by numeric user ID |
| `--by-name` | flag | One required | Resolve USER by full name |
| `--no-resolve` | flag | No | Skip group membership lookup |
| `--json` | flag | No | Emit machine-readable JSON |

**Human Output**:

Primary table headers: `Field`, `Value`, `Settable`, `Notes`.

Profile-field table headers: `Field ID`, `Value`, `Rendered Value`.

Group-membership table headers when resolution is enabled: `Name`, `Group ID`,
`Type`.

**JSON Output**:

```json
{
  "user": {
    "user_id": 42,
    "full_name": "Alice Admin",
    "email": "alice@example.com",
    "delivery_email": "alice@example.com",
    "role": 100,
    "is_bot": false,
    "profile_data": {
      "1": {"value": "Release Engineering"}
    }
  },
  "derived": {
    "role_label": "owner"
  },
  "resolved": {
    "groups": [
      {"group_id": 10, "name": "Engineering", "type": "custom"}
    ]
  },
  "annotations": {
    "full_name": {"status": "not exposed", "setter": null},
    "email": {"status": "not exposed", "setter": null, "notes": "server setter new_email"},
    "delivery_email": {"status": "not exposed", "setter": null, "notes": "server setter new_email"},
    "role": {"status": "not exposed", "setter": null},
    "is_active": {"status": "not exposed", "setter": null},
    "profile_data": {"status": "not exposed", "setter": null}
  }
}
```

**Errors**:

```text
Error: Specify exactly one of --by-email, --by-id, --by-name
Error: --by-id requires a numeric identifier, got 'abc'
Error: No user found matching 'missing@example.com' (--by-email)
Error: User name 'Alex Kim' matched 2 users; use --by-email or --by-id to disambiguate
```

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip folder show FOLDER`

**Description**: Show complete details for one channel folder.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `FOLDER` | positional | Yes | Folder name or `id:N` |
| `--no-resolve` | flag | No | Skip creator lookup and assigned-channel enumeration |
| `--json` | flag | No | Emit machine-readable JSON |

A numeric-looking folder token without `id:` is treated as a name. If not found,
the error hints to use `id:N` for numeric IDs.

**Human Output**:

Primary table headers: `Field`, `Value`, `Settable`, `Notes`.

Assigned-channel table headers when resolution is enabled: `Name`, `Channel ID`,
`Type`, `Archived`.

**JSON Output**:

```json
{
  "folder": {
    "id": 10,
    "name": "Projects",
    "description": "Project channels",
    "rendered_description": "<p>Project channels</p>",
    "order": 1,
    "is_archived": false,
    "date_created": 1761955200,
    "creator_id": 42
  },
  "resolved": {
    "creator": {"user_id": 42, "full_name": "Alice Admin"},
    "channels": [
      {"stream_id": 100, "name": "project-alpha", "type": "public"}
    ]
  },
  "annotations": {
    "name": {"status": "via --flag", "setter": "--name"},
    "order": {"status": "via command", "setter": "folder move"}
  }
}
```

**Errors**:

```text
Error: folder reference must not be empty
Error: No channel folder named '999'. If you meant a numeric folder ID, use 'id:999'.
Error: No channel folder with id 999
Error: Channel folder name 'Projects' matched 2 folders; use the id:NUM prefix to disambiguate
```

**Exit Codes**: 0 = success, 1 = error

---

## Resolution Call Expectations

The implementation MAY reuse cached list responses within one command
invocation, but the observable behavior must match this contract.

| Command | Default extra calls | Skipped by `--no-resolve` |
| --- | --- | --- |
| `channel show` | groups, users, folders as needed for IDs present | yes |
| `group show` | users for members, groups for subgroup names | yes |
| `user show` | groups for membership | yes |
| `folder show` | users for creator, streams for assigned channels | yes |

Target lookup calls are not considered optional and still happen with
`--no-resolve`.
