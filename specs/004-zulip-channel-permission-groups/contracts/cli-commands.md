<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- command contracts require exact strings -->

# CLI Command Contracts: Zulip Channel Permission Groups

This document defines the public interface changes for making three channel
permission group settings writable. Existing global Zulip options such as
`--zuliprc` and hidden `--json` behavior remain unchanged.

## Shared Group Value Syntax

All three new flags accept the same value syntax:

```text
GROUP[,GROUP...]
```

Each `GROUP` token is one of:

- a user group name, matched case-insensitively;
- a system role display name such as `Owners`, `Administrators`,
  `Moderators`, `Full Members`, `Members`, `Everyone`, or `Nobody`;
- `id:NUM` for explicit numeric group ID lookup.

Bare numeric-looking tokens are names, not IDs. If a bare numeric token is not
found as a name, the error includes:

```text
If you meant a numeric group ID, use 'id:NUM'.
```

`none` is not a clear sentinel for these permission flags; it is treated as a
group name.

## `lftools-uv zulip channel create NAME`

**New options**:

| Option | Type | Required | Zulip field | Feature level | Description |
| --- | --- | --- | --- | --- | --- |
| `--can-add-subscribers-group` | string | No | `can_add_subscribers_group` | 342 | Group(s) permitted to add other users to the channel |
| `--can-administer-channel-group` | string | No | `can_administer_channel_group` | 325 | Group(s) permitted to administer the channel |
| `--can-send-message-group` | string | No | `can_send_message_group` | 333 | Group(s) permitted to post messages in the channel |

**Signature excerpt**:

```text
lftools-uv zulip channel create NAME
  [--description TEXT]
  [--type public|private|web-public]
  [--subscribe USER --by-email|--by-id|--by-name]
  [--allow-group GROUP[,GROUP...]]
  [--can-remove-subscribers-group GROUP[,GROUP...]]
  [--can-add-subscribers-group GROUP[,GROUP...]]
  [--can-administer-channel-group GROUP[,GROUP...]]
  [--can-send-message-group GROUP[,GROUP...]]
  [--folder FOLDER]
  [--announce|--no-announce]
  [--topic-policy allow|deny|follow-default]
```

**Create request shape**:

Create sends raw group-setting values directly to
`POST /api/v1/users/me/subscriptions`.

Single group example:

```json
{
  "subscriptions": [{"name": "announcements"}],
  "principals": [],
  "invite_only": false,
  "is_web_public": false,
  "can_send_message_group": 20
}
```

Multiple group example:

```json
{
  "subscriptions": [{"name": "project"}],
  "principals": [],
  "invite_only": false,
  "is_web_public": false,
  "can_add_subscribers_group": {
    "direct_members": [],
    "direct_subgroups": [20, 30]
  }
}
```

**Human success output**: unchanged from existing channel create.

```text
Created public channel 'announcements' (ID: 42)
```

**JSON success output**: unchanged mutation schema.

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "announcements",
  "operation": "create",
  "type": "public"
}
```

## `lftools-uv zulip channel update [CHANNEL]`

**New options**:

| Option | Type | Required | Zulip field | Feature level | Description |
| --- | --- | --- | --- | --- | --- |
| `--can-add-subscribers-group` | string | No | `can_add_subscribers_group` | 342 | Group(s) permitted to add other users to the channel |
| `--can-administer-channel-group` | string | No | `can_administer_channel_group` | 325 | Group(s) permitted to administer the channel |
| `--can-send-message-group` | string | No | `can_send_message_group` | 333 | Group(s) permitted to post messages in the channel |

**Signature excerpt**:

```text
lftools-uv zulip channel update [CHANNEL]
  [--channel-id ID]
  [--name TEXT]
  [--description TEXT]
  [--type public|private|web-public]
  [--topic-policy allow|deny|follow-default]
  [--allow-group GROUP[,GROUP...]]
  [--can-remove-subscribers-group GROUP[,GROUP...]]
  [--can-add-subscribers-group GROUP[,GROUP...]]
  [--can-administer-channel-group GROUP[,GROUP...]]
  [--can-send-message-group GROUP[,GROUP...]]
  [--folder FOLDER|--folder-id 0]
  [--subscribe USER --by-email|--by-id|--by-name]
  [--include-archived]
```

**At-least-one-setting validation**:

The local validation list must include the three new flags. An update with only
a target and no setting still fails:

```text
Error: channel update requires at least one setting to change (--name, --description, --type, --topic-policy, --allow-group, --folder, --subscribe, --can-remove-subscribers-group, --can-add-subscribers-group, --can-administer-channel-group, or --can-send-message-group)
```

**Update request shape**:

Update wraps each group-setting value as a group-setting update object before
sending `PATCH /api/v1/streams/{stream_id}`.

Single group example:

```json
{
  "can_send_message_group": {"new": 20}
}
```

Multiple group example:

```json
{
  "can_administer_channel_group": {
    "new": {"direct_members": [], "direct_subgroups": [20, 30]}
  }
}
```

**Human success output**: unchanged from existing channel update.

```text
Updated channel 'announcements' (id=42)
```

**JSON success output**: unchanged mutation schema.

```json
{
  "status": "success",
  "channel_id": 42,
  "channel_name": "announcements",
  "operation": "update"
}
```

## Feature-Level Errors

Each flag is gated independently. The command exits 1 before mutation.

```text
Error: This operation requires Zulip feature level 342 (server has 341)
Error: This operation requires Zulip feature level 325 (server has 324)
Error: This operation requires Zulip feature level 333 (server has 332)
```

`--can-send-message-group` MUST NOT fall back to `stream_post_policy` when the
server is below FL 333.

## Group Resolution Errors

The new flags reuse existing group-resolution errors.

```text
Error: No user group named '123'. If you meant a numeric group ID, use 'id:123'.
Error: Group name 'design' matched 2 groups; use the id:NUM prefix to disambiguate
Error: Group specification must not be empty
```

When ambiguity matches are available, human output lists candidate names and
IDs using the existing pattern.

## `lftools-uv zulip channel show`

Feature 003 output shape remains unchanged. Only the annotations for three
fields change.

**Human settable rows**:

```text
can_add_subscribers_group       Administrators (id=20)  via --flag  --can-add-subscribers-group; FL 342
can_administer_channel_group    Owners (id=21)          via --flag  --can-administer-channel-group; FL 325
can_send_message_group          Full Members (id=22)    via --flag  --can-send-message-group; FL 333
```

**JSON annotation excerpt**:

```json
{
  "annotations": {
    "can_add_subscribers_group": {
      "status": "via --flag",
      "setter": "--can-add-subscribers-group",
      "notes": "FL 342"
    },
    "can_administer_channel_group": {
      "status": "via --flag",
      "setter": "--can-administer-channel-group",
      "notes": "FL 325"
    },
    "can_send_message_group": {
      "status": "via --flag",
      "setter": "--can-send-message-group",
      "notes": "FL 333"
    }
  }
}
```

## Exit Codes

| Condition | Exit code |
| --- | --- |
| Create/update success | 0 |
| Human validation error | 1 |
| Feature-level error | 1 |
| Group not found or ambiguous | 1 |
| Zulip API permission/validation error | 1 |
| Partial create behavior from unrelated existing secondary operations | Existing command behavior |
