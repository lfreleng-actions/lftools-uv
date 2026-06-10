<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- table rows mirror existing spec style -->

# Data Model: Zulip Channel Folders

## Entities

### ChannelFolder

Represents a Zulip channel folder returned by the channel folders API.

| Field | Type | Description |
| --- | --- | --- |
| `id` | `int` | Server-assigned channel folder ID |
| `name` | `str` | Non-empty folder name |
| `description` | `str` | Plain-text description; may be empty |
| `order` | `int \| None` | Server-assigned order; present at FL 414+ |
| `is_archived` | `bool` | Folder is archived when true |
| `date_created` | `int \| None` | UNIX timestamp in UTC seconds |
| `creator_id` | `int \| None` | User ID that created the folder |
| `rendered_description` | `str` | HTML rendering; pass-through from Zulip |

**Validation Rules**:

- `name` MUST NOT be empty.
- `name` length MUST be less than or equal to
  `max_channel_folder_name_length` when that `/register` value is available.
- `description` may be empty but MUST be supplied to the create API.
- `description` length MUST be less than or equal to
  `max_channel_folder_description_length` when that `/register` value is
  available.
- `order` may be `None` when connected to servers at FL 389 through FL 413.
- `order` is mutable at FL 414 and newer through the bulk reorder endpoint.
  Reorder requests must include every channel folder ID exactly once.
- Folder mutation commands require Zulip feature level 389 and admin
  permissions enforced by the server.
- Folder move requires Zulip feature level 414 and admin permissions enforced
  by the server.

**State Transitions**:

```text
┌──────────┐   archive    ┌──────────┐
│  Active  │─────────────▶│ Archived │
│          │◀─────────────│          │
└──────────┘  unarchive   └──────────┘
      (PATCH is_archived=true/false)
```

There is no hard-delete transition. Zulip only exposes archival.
Moving a folder changes its relative `order` value through
`PATCH /api/v1/channel_folders`; it does not change the active/archive state.

---

### Channel (Stream) Extension

Feature 001 defines the `Channel` entity. This feature extends it with the
folder relationship.

| Field | Type | Description |
| --- | --- | --- |
| `folder_id` | `int \| None` | References `ChannelFolder.id`; None means no folder |

**Validation Rules**:

- `folder_id` is assigned on channel create/update through existing Zulip
  stream endpoints.
- A non-null `folder_id` MUST reference an existing folder visible through
  `GET /api/v1/channel_folders` or be provided explicitly with `id:N`.
- `folder_id: null` clears the relationship.
- Channel assignment requires Zulip feature level 389; server permissions are
  enforced by Zulip and surfaced by the CLI.

---

### FolderMutationResult

Standard response schema for folder mutation operations.

| Field | Type | Description |
| --- | --- | --- |
| `status` | `str (enum)` | Outcome: success or error |
| `folder_id` | `int \| None` | Folder ID, if known |
| `folder_name` | `str \| None` | Folder name, if known |
| `operation` | `str` | create/update/archive/unarchive/move |

## Relationships

```text
ChannelFolder 1──────* Channel (via folder_id)
ZulipConfig 1──────── Client Session
```

- A ChannelFolder may contain zero or more channels.
- A Channel may reference zero or one ChannelFolder.
- Folder list and folder assignment use the same authenticated Zulip client
  session as existing channel management commands.
