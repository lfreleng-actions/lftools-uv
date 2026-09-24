<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Quickstart: Zulip Show Commands

## Prerequisites

- Python >=3.11, <3.15
- `lftools-uv` installed with the `zulip` extra
- A Zulip server configured through the existing Zulip configuration flow
- Permission to view the target channel, group, user, or folder

## Configuration

Show commands use the same configuration precedence as existing Zulip commands:

```text
--zuliprc PATH > ./zuliprc > lftools.ini [zulip] > ~/.zuliprc
```

Example:

```bash
lftools-uv zulip --zuliprc ./zuliprc channel show general
```

## Inspect a channel

```bash
# Show by channel name and resolve IDs to names
lftools-uv zulip channel show general

# Show by channel ID, including archived channels
lftools-uv zulip channel show --channel-id 42 --include-archived

# Avoid extra user/group/folder lookups and show raw IDs
lftools-uv zulip channel show general --no-resolve

# JSON for automation
lftools-uv zulip channel show general --json
```

Use channel show before updates when you need fields hidden by `channel list`,
such as permission groups, folder assignment, topic policy, retention settings,
and feature-level-gated channel permissions.

## Inspect a group and members

```bash
# Positional group name shorthand
lftools-uv zulip group show Engineering

# Explicit group filters mirror group list
lftools-uv zulip group show --group-name Engineering
lftools-uv zulip group show --group-id 10

# Show raw member and subgroup IDs only
lftools-uv zulip group show --group-id 10 --no-resolve
```

Group show expands the raw `members` array into Full Name, Email, and User ID
rows by default. It shows direct subgroups only; recursive subgroup expansion is
out of scope.

## Inspect a user

```bash
# Resolve by email
lftools-uv zulip user show alice@example.com --by-email

# Resolve by ID
lftools-uv zulip user show 42 --by-id

# Resolve by full name; fails if ambiguous
lftools-uv zulip user show "Alice Admin" --by-name

# Skip derived group membership lookup
lftools-uv zulip user show 42 --by-id --no-resolve
```

User show displays role, bot fields, active state, timezone, avatar fields, and
custom profile fields when Zulip returns them.

## Inspect a folder

```bash
# Resolve a folder by name
lftools-uv zulip folder show Projects

# Resolve by ID with explicit id: prefix
lftools-uv zulip folder show id:10

# Skip creator lookup and channel enumeration
lftools-uv zulip folder show Projects --no-resolve
```

Folder show lists assigned channels by default by reading channels and filtering
on `folder_id`. Use `--no-resolve` when you only need the raw folder object.

## Settable Annotations

Human output includes a `Settable` column:

```text
Field                  Value        Settable             Notes
name                   general      via --name
folder_id              10           via --folder
can_send_message_group Members      not exposed          server-settable FL 333
subscriber_count       125          no
```

`not exposed` means Zulip has an API setting but lftools-uv does not yet expose
a write flag. This specification does not add those write flags.

## Error Handling

All errors go to stderr and exit non-zero:

```text
Error: Exactly one of channel or --channel-id is required
Error: User name 'Alex Kim' matched 2 users; use --by-email or --by-id to disambiguate
Error: No channel folder named '999'. If you meant a numeric folder ID, use 'id:999'.
```

## Development Validation

Implementation PRs should run focused Zulip tests first:

```bash
uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py tests/unit/test_zulip_folders.py
uv run ruff check .
uv run mypy lftools_uv
SKIP=basedpyright pre-commit run --all-files
```
