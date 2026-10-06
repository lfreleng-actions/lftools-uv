<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Quickstart: Zulip Channel Permission Groups

## Prerequisites

- Python >=3.11, <3.15
- `lftools-uv` installed with the `zulip` extra
- A Zulip server configured through the existing Zulip configuration flow
- Permission on the Zulip server to create or administer the target channel
- A server new enough for the permission being set:
  - FL 342 for `can_add_subscribers_group`
  - FL 325 for `can_administer_channel_group`
  - FL 333 for `can_send_message_group`

## Discover Group IDs and Names

```bash
# Human-readable group list
lftools-uv zulip group list

# JSON for automation
lftools-uv zulip group list --json
```

Group permission flags accept names by default and `id:NUM` for explicit group
ID lookup:

```bash
--can-send-message-group Moderators
--can-administer-channel-group "Release Managers"
--can-add-subscribers-group "Engineering, id:22"
```

## Create a Channel with Posting Restricted to Moderators

```bash
lftools-uv zulip channel create announcements \
  --description "Moderated project announcements" \
  --can-send-message-group Moderators
```

The create request sends the raw Zulip group-setting value in
`can_send_message_group`. On servers below FL 333, the command fails before
mutation and does not use `stream_post_policy`.

## Create a Channel with Delegated Administrators

```bash
lftools-uv zulip channel create project-alpha \
  --description "Project Alpha coordination" \
  --can-administer-channel-group "Project Alpha Admins"
```

Use `channel show` to confirm that the field is both set and now annotated as
writable:

```bash
lftools-uv zulip channel show project-alpha
```

## Allow a Group to Add Subscribers

```bash
lftools-uv zulip channel update project-alpha \
  --can-add-subscribers-group "Project Alpha Admins"
```

For multiple groups, use a comma-separated value:

```bash
lftools-uv zulip channel update project-alpha \
  --can-add-subscribers-group "Project Alpha Admins, id:42"
```

Update requests wrap the resolved value as `{"new": ...}` before sending it to
Zulip.

## Combine with Existing Flags

The new flags can be combined with existing channel settings:

```bash
lftools-uv zulip channel update project-alpha \
  --description "Project Alpha private coordination" \
  --type private \
  --allow-group "Project Alpha Members" \
  --can-administer-channel-group "Project Alpha Admins" \
  --can-send-message-group "Project Alpha Members"
```

`--allow-group` keeps its existing meaning: who can subscribe themselves to the
channel. It is not renamed by this feature.

## Feature-Level Failures

If the server is too old, the command exits 1 before mutation:

```text
Error: This operation requires Zulip feature level 333 (server has 332)
```

Use the field's feature level to decide whether to upgrade Zulip or omit the
flag.

## Clearing or Resetting

These permission flags do not support `none` as a clearing value. Official
Zulip docs document only explicit group-setting values for these fields. To set
a restrictive value, use an explicit group such as `Nobody` if the server
accepts it for that permission.

## Validate with `channel show --json`

```bash
lftools-uv zulip channel show project-alpha --json
```

The output includes raw fields, resolved group displays, and annotations like:

```json
{
  "annotations": {
    "can_send_message_group": {
      "status": "via --flag",
      "setter": "--can-send-message-group",
      "notes": "FL 333"
    }
  }
}
```

## Development Validation

Implementation PRs should run focused Zulip tests first:

```bash
uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py
uv run ruff check .
uv run mypy lftools_uv
SKIP=basedpyright pre-commit run --all-files
```
