<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Quickstart: Zulip Channel Management

## Prerequisites

- Python >=3.11, <3.15
- `lftools-uv` installed (the `zulip` dependency will be added during
  implementation)
- A Zulip bot or user account with organization admin permissions
- A zuliprc file or equivalent configuration

## Configuration

Create a `~/.zuliprc` file (or place in current directory as `./zuliprc`):

```ini
[api]
email=your-bot@your-org.zulipchat.com
key=your-api-key-here
site=https://your-org.zulipchat.com
```

Alternatively, add a `[zulip]` section to your `lftools.ini`:

```ini
[zulip]
email=your-bot@your-org.zulipchat.com
key=your-api-key-here
site=https://your-org.zulipchat.com
```

Or specify a path explicitly on every command:

```bash
lftools-uv zulip --zuliprc /path/to/zuliprc channel list
```

**Precedence**: `--zuliprc` > `./zuliprc` > lftools.ini `[zulip]` > `~/.zuliprc`

## Common Workflows

### Discover existing channels

```bash
# List all active channels
lftools-uv zulip channel list

# Include archived channels
lftools-uv zulip channel list --include-archived

# JSON output for scripting
lftools-uv zulip channel list --json
```

### Discover users and groups

```bash
# List active users
lftools-uv zulip user list

# Include bots and deactivated users
lftools-uv zulip user list --include-bots --include-deactivated

# List user groups
lftools-uv zulip group list
```

### Create a public channel

```bash
lftools-uv zulip channel create "new-project" \
  --description "Discussion for New Project" \
  --type public
```

### Create a private channel with subscribers

```bash
# By email
lftools-uv zulip channel create "team-secret" \
  --description "Private team channel" \
  --type private \
  --subscribe alice@example.com \
  --subscribe bob@example.com \
  --by-email

# By user ID
lftools-uv zulip channel create "team-secret" \
  --description "Private team channel" \
  --type private \
  --subscribe 42 \
  --subscribe 55 \
  --by-id
```

### Create a private channel with group access

```bash
lftools-uv zulip channel create "engineering-only" \
  --description "Engineering team channel" \
  --type private \
  --allow-group 'Engineering, id:123'
```

### Manage subscriptions

```bash
# Subscribe users by email
lftools-uv zulip channel subscribe general \
  alice@example.com bob@example.com \
  --by-email

# Unsubscribe by user ID
lftools-uv zulip channel unsubscribe general 42 55 --by-id

# List subscribers
lftools-uv zulip channel subscribers general
```

### Update channel settings

```bash
# Rename a channel
lftools-uv zulip channel update old-name --name new-name

# Change description
lftools-uv zulip channel update general --description "Updated description"

# Change type to private (requires --subscribe OR non-Nobody --allow-group)
lftools-uv zulip channel update public-channel --type private \
  --allow-group 'Engineering'

# Set topic policy
lftools-uv zulip channel update general --topic-policy deny
```

### Archive and unarchive

```bash
# Archive a channel (requires --yes)
lftools-uv zulip channel archive unused-channel --yes

# Unarchive (use --include-archived if channel isn't found by default)
lftools-uv zulip channel unarchive old-channel --include-archived --yes
```

## JSON Output for Automation

All commands support `--json` for pipeline integration:

```bash
# Create and capture channel ID
RESULT=$(lftools-uv zulip channel create "auto-project" \
  --type public --json)
CHANNEL_ID=$(echo "$RESULT" | jq '.channel_id')

# Bulk subscribe from a file
while IFS= read -r email; do
  lftools-uv zulip channel subscribe "auto-project" "$email" \
    --by-email --json
done < users.txt
```

## Error Handling

All errors go to stderr with non-zero exit codes:

```bash
# Check if command succeeded
if lftools-uv zulip channel create "test" --type private; then
  echo "Created"
else
  echo "Failed (missing --subscribe or --allow-group for private channel)"
fi
```

Feature-level errors are clearly reported:

```text
Error: This operation requires Zulip feature level N (server has M)
```

## Development

> **Note**: The paths below are planned locations; files will be
> created during implementation.

```bash
# Run tests (once implementation exists)
uv run pytest tests/unit/test_zulip_api.py
uv run pytest tests/unit/test_zulip_cli.py

# Type checking (once implementation exists)
uv run mypy lftools_uv/api/endpoints/zulip.py
uv run basedpyright lftools_uv/typer_apps/zulip.py
```
