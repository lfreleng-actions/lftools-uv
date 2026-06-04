<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# CLI Command Contracts: Zulip Channel Folders

This document defines the public CLI interface contracts for Zulip channel
folder commands and the updated channel create/update folder flags.

## Optional Dependency

The `zulip` command group requires the `zulip` optional extra. Install with
`pip install "lftools-uv[zulip]"` or `uv pip install "lftools-uv[zulip]"`.
When the extra is not installed, the command group still appears in CLI help
but running any subcommand produces a user-friendly error:

```text
Zulip support requires the zulip extra. Install with:
  pip install "lftools-uv[zulip]"
```

## Global Options (all zulip commands)

Subcommand option tables omit these globals; every subcommand accepts them.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--zuliprc` | PATH | No | Path to zuliprc configuration file |
| `--json` | flag | No | Output in JSON format |

---

## `lftools-uv zulip folder list`

**Description**: List channel folders visible to the authenticated user.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--include-archived` | flag | No | Include archived folders in output |
| `--limit` | int | No | Limit number of folders displayed |

**Human Output**: Table with columns: Folder ID, Name, Order, Description.
Status appears only when `--include-archived` is specified and displays Active
or Archived.

**JSON Output**:

```json
{
  "folders": [
    {
      "id": 10,
      "name": "Projects",
      "order": 1,
      "description": "Project channels",
      "rendered_description": "<p>Project channels</p>",
      "is_archived": false,
      "date_created": 1761955200,
      "creator_id": 42
    }
  ]
}
```

On servers below FL 414, `order` is `null` if Zulip omits the field.

**Exit Codes**: 0 = success, 1 = error (config/connection/feature-level)

---

## `lftools-uv zulip folder create`

**Description**: Create a new channel folder. Admin-only on the Zulip server.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--name` | str | Yes | Folder name, non-empty |
| `--description` | str | No | Folder description; defaults to empty |

**Constraints**:

- Requires Zulip feature level 389.
- `--name` must be non-empty.
- `description` is always sent to Zulip; omitted CLI value becomes `""`.
- Known `/register` length limits are enforced client-side.
- Permission errors are surfaced from Zulip.

**JSON Output** (success):

```json
{
  "status": "success",
  "folder_id": 10,
  "folder_name": "Projects",
  "operation": "create"
}
```

**Human Output**: Prints the created folder ID.

**Exit Codes**: 0 = success, 1 = error

---

## `lftools-uv zulip folder update`

**Description**: Update a channel folder name and/or description. Admin-only on
the Zulip server.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--folder-id` | int | Yes | Target folder ID |
| `--name` | str | No | New folder name |
| `--description` | str | No | New folder description |

**Constraints**:

- Requires Zulip feature level 389.
- At least one of `--name` or `--description` is required.
- Known `/register` length limits are enforced client-side.
- Permission errors are surfaced from Zulip.

**JSON Output** (success):

```json
{
  "status": "success",
  "folder_id": 10,
  "folder_name": "Engineering",
  "operation": "update"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## `lftools-uv zulip folder archive`

**Description**: Archive a channel folder. Admin-only on the Zulip server.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--folder-id` | int | Yes | Target folder ID |

**Constraints**:

- Requires Zulip feature level 389.
- Calls `PATCH /api/v1/channel_folders/{id}` with `is_archived=true`.
- There is no hard-delete command.

**JSON Output** (success):

```json
{
  "status": "success",
  "folder_id": 10,
  "folder_name": "Old Projects",
  "operation": "archive"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## `lftools-uv zulip folder unarchive`

**Description**: Reactivate an archived channel folder. Admin-only on the Zulip
server.

| Option | Type | Required | Description |
| --- | --- | --- | --- |
| `--folder-id` | int | Yes | Target folder ID |

**Constraints**:

- Requires Zulip feature level 389.
- Calls `PATCH /api/v1/channel_folders/{id}` with `is_archived=false`.

**JSON Output** (success):

```json
{
  "status": "success",
  "folder_id": 10,
  "folder_name": "Projects",
  "operation": "unarchive"
}
```

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## Updated `lftools-uv zulip channel create <name>`

**Description**: Create a new channel, optionally assigned to a folder.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `name` | positional | Yes | Channel name |
| `--folder` | str | No | Folder name, `id:N`, or `none` |

All existing channel create options from the channel management contract remain
valid.

**`--folder` syntax**:

- `--folder Projects` resolves a folder by case-insensitive name.
- `--folder id:10` resolves folder ID 10 explicitly.
- `--folder none` sends `folder_id: null`.

A numeric-looking token without `id:` is treated as a folder name. If it is not
found, the CLI errors with a hint to use `--folder id:N` for numeric IDs.

**JSON Output** (success addition): Existing `channel create` JSON remains the
same and may include `folder_id` when a folder was requested.

**Exit Codes**: 0 = success, 1 = error

---

## Updated `lftools-uv zulip channel update [channel]`

**Description**: Update channel settings, including folder assignment.

| Argument/Option | Type | Required | Description |
| --- | --- | --- | --- |
| `channel` | positional | No | Channel name (optional if --channel-id) |
| `--folder` | str | No | Folder name, `id:N`, or `none` |
| `--folder-id` | int | No | Clear-only compatibility form; only `0` |

All existing channel update options from the channel management contract remain
valid.

**Constraints**:

- Requires Zulip feature level 389 when `--folder` or `--folder-id 0` is used.
- `--folder none` and `--folder-id 0` both send `folder_id: null`.
- Non-zero folder IDs use `--folder id:N`; non-zero `--folder-id` values are
  rejected with a message directing the user to `--folder id:N`.
- Permission errors are surfaced from Zulip.

**JSON Output** (success addition): Existing `channel update` JSON remains the
same and may include `folder_id` when a folder change was requested.

**Exit Codes**: 0 = success (including no-op), 1 = error

---

## Feature-Level Error Contract

Folder commands and folder assignment fail before mutation on unsupported
servers:

```text
Error: This operation requires Zulip feature level 389 (server has 388)
```

Folder list keeps a stable `Order` column even when `order` is absent before FL
414. Missing order values are rendered blank in tables and `null` in JSON.
