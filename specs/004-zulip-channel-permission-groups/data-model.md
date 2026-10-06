<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- tables preserve exact Zulip field names -->

# Data Model: Zulip Channel Permission Groups

## Shared Concepts

### ChannelPermissionFlag

Represents one CLI flag that writes one Zulip channel permission group setting.

| Field | Type | Description |
| --- | --- | --- |
| `flag` | `str` | CLI option name, e.g. `--can-add-subscribers-group` |
| `zulip_field` | `str` | Exact Zulip API field name |
| `feature_key` | `str` | Key in `FEATURE_LEVELS` |
| `required_feature_level` | `int` | Minimum `zulip_feature_level` |
| `meaning` | `str` | Human description shown in help/docs |
| `value_spec` | `str` | Raw user input before group resolution |

Required instances:

| Flag | Zulip field | Feature key | Required FL | Meaning |
| --- | --- | --- | --- | --- |
| `--can-add-subscribers-group` | `can_add_subscribers_group` | `can-add-subscribers-group` | 342 | Who can add other users to the channel |
| `--can-administer-channel-group` | `can_administer_channel_group` | `can-administer-channel-group` | 325 | Who can administer the channel |
| `--can-send-message-group` | `can_send_message_group` | `can-send-message-group` | 333 | Who can post messages in the channel |

### GroupSpec

User-facing syntax reused from existing permission flags.

| Input | Meaning |
| --- | --- |
| `Engineering` | Case-insensitive group name lookup |
| `Administrators` | System role display-name lookup |
| `id:22` | Explicit numeric group ID lookup |
| `Engineering, id:22` | Multiple groups, resolved in order |

Rules:

- Empty comma segments are ignored.
- A wholly empty value is invalid.
- Bare numeric-looking tokens are names, not IDs; if missing, the error hints
  to use `id:NUM`.
- Ambiguous custom group names fail with candidate IDs.
- `Nobody` is resolved through the same system-role path as other groups.

### GroupSettingValue

Zulip value shape used by create requests and returned by read endpoints.

| Shape | JSON example | Meaning |
| --- | --- | --- |
| Single group integer | `22` | The group with ID 22 has the permission |
| Object form | `{"direct_members": [], "direct_subgroups": [22, 30]}` | Union of listed users and groups has the permission |

The implementation's resolver may continue to build only integer single-group
values and object-form multi-group values with `direct_members: []`, matching
existing `--allow-group` behavior. The show command must still render both
integer and object forms returned by Zulip.

### GroupSettingUpdate

Zulip value shape used by update requests.

| Field | Type | Required | Description |
| --- | --- | --- | --- |
| `new` | `GroupSettingValue` | Yes | Desired complete permission value |
| `old` | `GroupSettingValue` | No | Optimistic concurrency guard |

The CLI omits `old` because each invocation is a desired-state update rather
than an interactive edit of a previously fetched value.

## Channel Create Model Changes

`create_channel()` gains optional resolved values for each permission field:

| Parameter | Type | Zulip request key |
| --- | --- | --- |
| `can_add_subscribers_group_value` | `GroupSettingValue \| None` | `can_add_subscribers_group` |
| `can_administer_channel_group_value` | `GroupSettingValue \| None` | `can_administer_channel_group` |
| `can_send_message_group_value` | `GroupSettingValue \| None` | `can_send_message_group` |

When a parameter is `None`, the request omits that key and preserves existing
server defaults. When present, create sends the raw group-setting value.

Example create fragment:

```json
{
  "subscriptions": [{"name": "announcements"}],
  "principals": [],
  "invite_only": false,
  "is_web_public": false,
  "can_send_message_group": 20
}
```

## Channel Update Model Changes

`update_channel()` gains optional raw user input strings for each permission
field:

| Parameter | Type | Zulip request key |
| --- | --- | --- |
| `can_add_subscribers_group` | `str \| None` | `can_add_subscribers_group` |
| `can_administer_channel_group` | `str \| None` | `can_administer_channel_group` |
| `can_send_message_group` | `str \| None` | `can_send_message_group` |

When a parameter is present, the API layer resolves it to a `GroupSettingValue`
and wraps it in `{"new": ...}`.

Example update fragment:

```json
{
  "can_administer_channel_group": {
    "new": {"direct_members": [], "direct_subgroups": [20, 30]}
  }
}
```

## Feature Gates

| Feature key | Required FL | Checked when |
| --- | --- | --- |
| `can-add-subscribers-group` | 342 | `--can-add-subscribers-group` supplied to create or update |
| `can-administer-channel-group` | 325 | `--can-administer-channel-group` supplied to create or update |
| `can-send-message-group` | 333 | `--can-send-message-group` supplied to create or update |

Feature-level checks must run before resolving groups or sending mutation
requests when possible. This avoids unnecessary group list calls on unsupported
servers and prevents Zulip from silently ignoring unsupported fields.

## Updated Channel Settable Annotations

Feature 003 currently marks these fields as `not exposed`. This feature changes
only the three rows below.

| Channel field | Old annotation | New annotation |
| --- | --- | --- |
| `can_add_subscribers_group` | `not exposed`, notes `server-settable FL 342` | `via --flag`, setter `--can-add-subscribers-group`, notes `FL 342` |
| `can_administer_channel_group` | `not exposed`, notes `server-settable FL 325` | `via --flag`, setter `--can-administer-channel-group`, notes `FL 325` |
| `can_send_message_group` | `not exposed`, notes `server-settable FL 333` | `via --flag`, setter `--can-send-message-group`, notes `FL 333` |

All other channel permission fields remain unchanged unless a future feature
adds write flags for them.

## Validation Rules

- Each new flag validates with the same group resolver as existing permission
  flags.
- Unknown or ambiguous groups fail before mutation.
- Unsupported feature levels fail before mutation.
- `none` is not special for these flags and must not clear or reset a setting.
- `can_send_message_group` never maps to `stream_post_policy`.
- Existing private-channel lockout prevention continues to depend only on
  `--subscribe` and `--allow-group`; the three new flags do not grant channel
  content access for lockout prevention.
