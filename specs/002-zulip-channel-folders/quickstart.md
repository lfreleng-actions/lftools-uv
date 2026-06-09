<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Quickstart: Zulip Channel Folders

## Prerequisites

- Python >=3.11, <3.15
- `lftools-uv` installed with the `zulip` extra:

  ```bash
  pip install "lftools-uv[zulip]"
  # or
  uv pip install "lftools-uv[zulip]"
  ```

- A Zulip server at feature level 389 or newer for channel folders
- A Zulip server at feature level 414 or newer for folder move
- Organization admin permissions for folder create/update/archive/unarchive/move
- A zuliprc file or equivalent configuration

## Configuration

Use the same Zulip configuration as channel management:

```ini
[api]
email=your-bot@your-org.zulipchat.com
key=your-api-key-here
site=https://your-org.zulipchat.com
```

Or specify a path explicitly:

```bash
lftools-uv zulip --zuliprc /path/to/zuliprc folder list
```

**Precedence**: `--zuliprc` > `./zuliprc` > lftools.ini `[zulip]` > `~/.zuliprc`

## Common Workflows

### Discover folders

```bash
# List active folders
lftools-uv zulip folder list

# Include archived folders and show Status
lftools-uv zulip folder list --include-archived

# JSON output for scripts
lftools-uv zulip folder list --json
```

### Create and update folders

```bash
# Create a folder
lftools-uv zulip folder create \
  --name "Projects" \
  --description "Project discussion channels"

# Rename or redescribe a folder
lftools-uv zulip folder update \
  --folder-id 10 \
  --name "Engineering Projects"
```

### Archive and unarchive folders

```bash
# Archive a folder; Zulip has no hard-delete endpoint
lftools-uv zulip folder archive --folder-id 10

# Restore an archived folder
lftools-uv zulip folder unarchive --folder-id 10
```

### Move folders

```bash
# Move a folder before another folder by name
lftools-uv zulip folder move \
  --folder-id 12 \
  --before "Projects"

# Move a folder after another folder by ID
lftools-uv zulip folder move \
  --folder-id 10 \
  --after id:12
```

### Create a channel in a folder

```bash
# Resolve by folder name
lftools-uv zulip channel create "project-alpha" \
  --description "Project Alpha" \
  --type public \
  --folder "Projects"

# Resolve by folder ID
lftools-uv zulip channel create "project-beta" \
  --description "Project Beta" \
  --type public \
  --folder id:10
```

### Change or clear a channel folder

```bash
# Move channel to another folder
lftools-uv zulip channel update project-alpha --folder "Engineering"

# Clear folder assignment explicitly
lftools-uv zulip channel update project-alpha --folder none

# Compatibility clear form
lftools-uv zulip channel update project-alpha --folder-id 0
```

## Error Handling

All errors go to stderr with non-zero exit codes. Feature-level errors use the
existing Zulip command pattern:

```text
Error: This operation requires Zulip feature level 389 (server has 388)
```

Folder mutation permission errors are returned by Zulip and displayed by the
CLI. The CLI does not pre-flight admin role checks.

## Development

```bash
# Run folder-focused tests once implementation exists
uv run pytest tests/unit/test_zulip_folders.py

# Run broader Zulip unit tests
uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py
```
