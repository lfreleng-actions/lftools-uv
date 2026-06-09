<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Research: Zulip Channel Folders

## Decision 1: Zulip Channel Folder API Family

**Decision**: Use the Zulip channel folders resource family introduced in
Zulip 11.0 at feature level 389.

| Operation | Endpoint | Notes |
| --- | --- | --- |
| List folders | `GET /api/v1/channel_folders` | Optional `include_archived` |
| Create folder | `POST /api/v1/channel_folders/create` | Admin-only |
| Update folder | `PATCH /api/v1/channel_folders/{id}` | Admin-only |

API references:

- <https://zulip.com/api/get-channel-folders>
- <https://zulip.com/api/create-channel-folder>
- <https://zulip.com/api/update-channel-folder>

**Rationale**: These endpoints are the canonical API surface for channel
folders. The CLI should not emulate folders client-side.

**Alternatives Considered**:

- Store folder metadata locally: Rejected — would diverge from Zulip server
  state and fail for other clients.
- Use undocumented endpoints: Rejected — the documented API supports the
  required lifecycle operations.

## Decision 2: Feature-Level Gates

**Decision**: Add hardcoded feature-level constants:

| Feature | Required Feature Level |
| --- | --- |
| `channel-folders` | 389 |
| `channel-folders-order` | 414 |

All folder commands and `--folder` assignment require FL 389. The folder
`order` field is optional unless the server is at FL 414 or newer.

**Rationale**: Feature-level checks match the existing FR-019 pattern from the
channel management spec and provide clear errors on older servers.

**Alternatives Considered**:

- Minimum Zulip version string checks: Rejected — feature levels are the
  existing runtime compatibility mechanism.
- Try the API and report Zulip's error: Rejected — produces less actionable
  errors and can attempt mutations on unsupported servers.

## Decision 3: Archive Instead of Delete

**Decision**: Provide `folder archive` and `folder unarchive`; do not provide a
folder delete command.

**Rationale**: Zulip does not expose a hard-delete endpoint for channel folders.
The update endpoint changes `is_archived` to hide or restore folders.

**Alternatives Considered**:

- `folder delete` alias for archive: Rejected — misleading because the folder
  remains recoverable.
- `--archive` flag on update: Rejected — inconsistent with the existing channel
  UX, which uses standalone archive/unarchive commands.

## Decision 4: Channel Assignment Through `folder_id`

**Decision**: Use existing channel create/update API surfaces with a
`folder_id` integer parameter. Passing an integer assigns a folder; passing
`null` clears it.

**Rationale**: Zulip documents `folder_id` on `PATCH /api/v1/streams/{stream_id}`
and `POST /api/v1/users/me/subscriptions`, so channel folder assignment belongs
in the existing channel workflows.

**Alternatives Considered**:

- Separate `folder add-channel` command: Rejected — duplicates channel update
  semantics and creates another targeting model.

## Decision 5: Single `--folder` Flag

**Decision**: Add one `--folder` flag to channel create/update. It accepts a
folder name by default, `id:N` for explicit numeric lookup, or `none` to clear.
`--folder-id 0` is accepted for the locked explicit-clear UX and maps to
`folder_id: null`; non-zero IDs should use `--folder id:N`.

**Rationale**: This mirrors the inline `--allow-group` resolution UX after the
recent group-resolution fix and avoids duplicating `--folder-name` and
`--folder-id` flags for normal assignment.

**Alternatives Considered**:

- Split `--folder-id` and `--folder-name`: Rejected — duplicates concepts and
  makes scripts more verbose.
- Separate `--clear-folder` boolean: Rejected — the locked decision chose
  explicit-none (`--folder none`) instead.

## Decision 6: Length Limits From `/register`

**Decision**: Validate folder name and description lengths against
`max_channel_folder_name_length` and
`max_channel_folder_description_length` when those `/register` values are
available.

**Rationale**: Zulip exposes server-specific limits. Client-side validation
provides faster feedback while preserving server authority when limits are not
available.

**Alternatives Considered**:

- Hardcode limits: Rejected — limits are server-provided and may change.
- Rely only on server errors: Rejected — worse UX when limits are known.

## Decision 7: Permission Handling

**Decision**: Do not pre-flight role checks. Surface Zulip permission errors
from folder mutations and channel assignment as-is.

**Rationale**: Folder create/update/archive/unarchive are admin-only, while
channel assignment permissions vary by server policy and channel type. Zulip is
the source of truth.

**Alternatives Considered**:

- Fetch user role and reject locally: Rejected — duplicates server policy and
  risks false negatives.

## Decision 8: Folder Move Uses Bulk Reorder API

**Decision**: Implement folder reordering with
`PATCH /api/v1/channel_folders`, sending `order` as a JSON-encoded form value
containing every channel folder ID exactly once. Expose this through
`zulip folder move --folder-id N --before REF` and
`zulip folder move --folder-id N --after REF`, where `REF` accepts a folder
name, `id:N`, or a bare numeric folder ID.

**Rationale**: Zulip's API only accepts complete bulk order mappings; it does
not provide a single-folder move endpoint. The CLI can safely derive the
complete order from the current folder list while presenting a semantic UX that
matches how administrators think about moving one folder relative to another.

**Alternatives Considered**:

- Raw `folder reorder --order ID,ID,ID`: Rejected — it exposes the low-level API
  shape and makes it easy for users to omit or duplicate IDs.
- Per-user folder ordering: Rejected — the API updates organization-wide folder
  order, and per-user ordering is outside this command's scope.
