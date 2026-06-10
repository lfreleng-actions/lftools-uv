<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Feature Specification: Zulip Channel Folders

**Feature Branch**: `002-zulip-channel-folders`
**Created**: 2026-06-04
**Status**: Implemented
**Input**: User description: "Add specification artifacts for Zulip channel
folders, including folder lifecycle commands and channel folder assignment."

## Clarifications

### Session 2026-06-04

- Q: What command group should expose folder lifecycle operations? → A:
  Add `lftools-uv zulip folder ...` with `list`, `create`, `update`,
  `archive`, and `unarchive` subcommands.
- Q: Should folder deletion be supported? → A: No. Zulip exposes archive and
  unarchive through `PATCH /api/v1/channel_folders/{id}`. There is no
  hard-delete endpoint.
- Q: How should channels reference folders? → A: `channel create` and
  `channel update` gain a single `--folder` flag accepting a folder name,
  `id:N`, or `none`. The value `none` clears the folder on update. The
  `--folder-id 0` clear form is accepted on `channel update` for
  compatibility with the locked CLI decision and maps to `folder_id: null`;
  non-zero folder IDs use `--folder id:N`.
- Q: How should folder names and IDs be resolved? → A: Names resolve through
  `GET /api/v1/channel_folders`. The `id:N` prefix forces numeric ID lookup.
  A numeric-looking token without `id:` is treated as a name; if no folder is
  found, the error hints to use `id:N`.
- Q: Which feature levels gate this work? → A: Channel folders require Zulip
  feature level 389. The folder `order` field requires feature level 414. All
  folder commands and use of `--folder` short-circuit below FL 389.
- Q: Should the CLI pre-flight admin permissions? → A: No. Folder create,
  update, archive, and unarchive are admin-only per Zulip. The CLI propagates
  server-side permission errors. Folder list is available to all users.
- Q: Should archive/unarchive be flags on update? → A: No. Use separate
  `archive` and `unarchive` commands to match the existing channel UX.

### Session 2026-06-09

- Q: How should administrators reorder folders? → A: Add
  `zulip folder move --folder-id N --before REF` and
  `zulip folder move --folder-id N --after REF`, where `REF` is a folder
  name, `id:N`, or bare numeric ID.
- Q: Should the CLI expose a raw order array? → A: No. Use semantic
  before/after placement and compute the complete order required by Zulip's
  bulk reorder API.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Discover channel folders (Priority: P1)

A Zulip user can list channel folders visible on the server, optionally
including archived folders, and can consume the result as either a table or
JSON for automation.

**Why this priority**: Discovery is the safe MVP and is required before users
can assign channels to existing folders by name.

**Independent Test**: Run `lftools-uv zulip folder list` against mocked folder
API responses and verify active-only output, archived inclusion, table columns,
`--limit`, and JSON shape.

**Acceptance Scenarios**:

1. **Given** a server at FL 389 or newer with active folders, **When** the user
   runs `zulip folder list`, **Then** only active folders appear.
2. **Given** active and archived folders, **When** the user runs
   `zulip folder list --include-archived`, **Then** both active and archived
   folders appear and table output includes a Status column.
3. **Given** a server below FL 414, **When** folder list output is rendered,
   **Then** the Order column is still present but shows an empty value or
   `null` because the server does not provide order data.

---

### User Story 2 - Manage folder lifecycle (Priority: P1)

A Zulip organization administrator can create, rename, describe, archive, and
unarchive channel folders without using the Zulip web UI.

**Why this priority**: Folder lifecycle management is the core administrative
capability for organizing channels.

**Independent Test**: Mock create/update/archive/unarchive API calls and verify
payloads, success output, validation, feature-level gating, and permission error
propagation.

**Acceptance Scenarios**:

1. **Given** an admin on a FL 389 server, **When** the admin runs
   `zulip folder create --name Projects --description "Project channels"`,
   **Then** the CLI calls the create endpoint and prints the created folder ID.
2. **Given** an existing folder, **When** the admin runs
   `zulip folder update --folder-id 10 --name Engineering`, **Then** the CLI
   patches only the requested field.
3. **Given** an existing active folder, **When** the admin runs
   `zulip folder archive --folder-id 10`, **Then** the CLI sets
   `is_archived=true`.
4. **Given** an archived folder, **When** the admin runs
   `zulip folder unarchive --folder-id 10`, **Then** the CLI sets
   `is_archived=false`.

---

### User Story 3 - Assign channels to folders (Priority: P2)

An administrator or channel owner can assign a folder during channel creation
or update and can clear a channel's folder assignment explicitly.

**Why this priority**: The feature is only useful when channels can be placed
into folders through existing channel workflows.

**Independent Test**: Mock channel create/update calls with `--folder` values
and verify name resolution, `id:N` resolution, `none`/`--folder-id 0` clearing,
feature-level errors, and propagated API permission failures.

**Acceptance Scenarios**:

1. **Given** a folder named Projects, **When** the user creates a channel with
   `--folder Projects`, **Then** the create payload includes that folder ID.
2. **Given** a folder ID 10, **When** the user updates a channel with
   `--folder id:10`, **Then** the update payload includes `folder_id: 10`.
3. **Given** a channel currently assigned to a folder, **When** the user updates
   it with `--folder none` or `--folder-id 0`, **Then** the update payload
   includes `folder_id: null`.

---

### User Story 4 - Reorder channel folders (Priority: P2)

An organization administrator can move one channel folder before or after
another folder without manually constructing the complete folder order.

**Why this priority**: Folder order controls the navigation and organization
experience after folders exist. A semantic move command avoids error-prone raw
bulk order arrays.

**Independent Test**: Mock `GET /api/v1/channel_folders` and
`PATCH /api/v1/channel_folders`, then verify `folder move` resolves references,
plans the complete order, gates at feature level 414, and propagates Zulip
validation or permission errors.

**Acceptance Scenarios**:

1. **Given** folders Projects, Engineering, and Archive, **When** the admin runs
   `zulip folder move --folder-id 12 --before Projects`, **Then** the CLI sends
   an order placing folder 12 before Projects.
2. **Given** folder IDs 10 and 12, **When** the admin runs
   `zulip folder move --folder-id 10 --after id:12`, **Then** the CLI sends an
   order placing folder 10 after folder 12.
3. **Given** a numeric reference `12`, **When** the admin uses it with
   `--before` or `--after`, **Then** the CLI treats it as folder ID 12.

### Edge Cases

- Servers below FL 389 reject all folder commands and `--folder` usage before
  making folder API calls.
- Servers at FL 389 through FL 413 may omit the folder `order` field; output
  remains stable with a blank table value or JSON `null`.
- Folder create requires a non-empty name. Description is a required API field
  but may be an empty string; the CLI defaults omitted descriptions to `""`.
- `folder update` requires at least one of `--name` or `--description`.
- A numeric-looking `--folder` token without `id:` is treated as a name; if not
  found, the CLI suggests `--folder id:N` for numeric IDs.
- Permission errors from admin-only folder mutations are displayed as returned
  by Zulip and are not pre-flight checked by the CLI.
- `folder move` requires FL 414 because it uses the bulk folder reorder API.
- `folder move` requires exactly one of `--before` or `--after`.
- `folder move` rejects moves where the target folder equals the reference
  folder.
- `folder move` lists folders with archived entries included so the complete
  order sent to Zulip preserves every folder ID exactly once.
- Folder length limits come from `/register` fields
  `max_channel_folder_name_length` and
  `max_channel_folder_description_length`; the CLI validates when those limits
  are available and otherwise lets the server enforce them.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-023**: System MUST provide a `lftools-uv zulip folder list` command that
  returns active channel folders visible to the authenticated user. It MUST
  support `--include-archived`, `--json`, and `--limit`. Human-readable output
  MUST use columns `Folder ID`, `Name`, `Order`, and `Description`; it MUST add
  a `Status` column only when `--include-archived` is used. JSON output MUST be
  `{"folders": [...]}` with folder entity fields.
- **FR-024**: System MUST provide a `lftools-uv zulip folder create` command
  with required `--name` and optional `--description` defaulting to `""`. The
  command MUST call `POST /api/v1/channel_folders/create` and print the created
  `channel_folder_id` in human output. JSON output MUST include
  `status`, `folder_id`, `folder_name`, and `operation`.
- **FR-025**: System MUST provide a `lftools-uv zulip folder update` command
  with required `--folder-id` and optional `--name` and `--description`. At
  least one mutable field MUST be provided. The command MUST call
  `PATCH /api/v1/channel_folders/{id}` with only requested fields.
- **FR-026**: System MUST provide a `lftools-uv zulip folder archive` command
  with required `--folder-id`. It MUST call the folder PATCH endpoint with
  `is_archived=true`. No hard-delete command is in scope.
- **FR-027**: System MUST provide a `lftools-uv zulip folder unarchive` command
  with required `--folder-id`. It MUST call the folder PATCH endpoint with
  `is_archived=false`.
- **FR-028**: `lftools-uv zulip channel create` MUST accept `--folder` to assign
  the new channel to a channel folder. The flag MUST accept a folder name,
  `id:N`, or `none`; `none` maps to `folder_id: null`.
- **FR-029**: `lftools-uv zulip channel update` MUST accept `--folder` to assign
  or change a channel folder. The command MUST also accept `--folder none` and
  `--folder-id 0` to clear the channel folder by sending `folder_id: null`.
- **FR-030**: Folder operations and `--folder` usage MUST require Zulip feature
  level 389. Unsupported servers MUST fail before mutation with the canonical
  feature-level error: `This operation requires Zulip feature level 389 (server
  has Y)`.
- **FR-031**: System MUST define `FEATURE_LEVELS["channel-folders"] = 389` and
  `FEATURE_LEVELS["channel-folders-order"] = 414` in
  `lftools_uv/api/endpoints/zulip.py` during implementation.
- **FR-032**: Folder resolution MUST use `GET /api/v1/channel_folders` for
  case-insensitive name lookup and `id:N` lookup. Numeric-looking names without
  `id:` MUST be treated as names; if not found, errors MUST hint to pass
  `id:N` for numeric folder IDs, matching the group resolution UX. The
  `none` token and update-only `--folder-id 0` clear form MUST short-circuit
  lookup and yield `folder_id: null`.
- **FR-033**: The CLI MUST respect `max_channel_folder_name_length` and
  `max_channel_folder_description_length` from `/register` when available.
  Values exceeding known limits MUST fail client-side with a clear validation
  error; otherwise the server response is authoritative.
- **FR-034**: Folder list MUST tolerate missing `order` on servers below FL
  414. The table still includes `Order`, and JSON uses `null` when the API
  omits the field. The `channel-folders-order` constant documents this
  threshold for output handling and future order-specific behavior; it does not
  block folder list on FL 389 through FL 413.
- **FR-035**: Folder create/update/archive/unarchive MUST surface Zulip
  permission errors as-is. The CLI MUST NOT perform client-side role checks.
- **FR-036**: Folder mutations MUST be idempotent for no-op archive state
  changes when the server reports success or already-current state; JSON no-ops
  MUST return `"status": "success"`. Folder update sends requested fields and
  treats the server response as authoritative for same-value updates.
- **FR-037**: Contracts and quickstart documentation MUST describe the new
  folder commands, updated channel flags, feature-level gates, and API facts
  from the Zulip channel folders documentation.
- **FR-038**: System MUST provide a `lftools-uv zulip folder move` command with
  required `--folder-id` and exactly one of `--before REF` or `--after REF`.
  `REF` MUST accept a folder name, `id:N`, or bare numeric folder ID. The
  command MUST fetch the complete folder list including archived folders,
  compute a complete ID order containing every folder exactly once, and call
  `PATCH /api/v1/channel_folders` with `order` as a JSON-encoded form value.
  The command MUST require feature level 414 using the existing
  `channel-folders-order` gate, reject missing targets or references, reject
  self-relative moves, and surface server permission or validation errors
  as-is.

### Key Entities

- **ChannelFolder**: A Zulip channel folder with server-assigned ID, name,
  description, optional order, archived status, creation metadata, and rendered
  HTML description.
- **Channel (Stream)**: Existing channel entity gains `folder_id: int | None`,
  referencing `ChannelFolder.id` when assigned.
- **Zulip Configuration**: Existing Zulip configuration resolution applies to
  all folder commands.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-009**: Users can list 100 channel folders in under 5 seconds with table
  or JSON output.
- **SC-010**: Administrators can create, update, archive, and unarchive a
  channel folder with one CLI invocation per operation.
- **SC-011**: Users can assign or clear a channel folder during channel create
  or update without using the Zulip web UI.
- **SC-012**: Servers below FL 389 produce a clear feature-level error for all
  folder commands and `--folder` usage.
- **SC-013**: JSON output from folder commands is valid parseable JSON and uses
  stable field names for scripting.
- **SC-014**: Administrators can move a folder before or after another folder
  with one command, and the server receives a complete valid order array.

## Assumptions

- The existing Zulip optional dependency, configuration resolution, API layer,
  and Typer command group from `001-zulip-channel-mgmt` are present.
- Folder commands use Zulip REST API v1 endpoints documented at
  <https://zulip.com/api/get-channel-folders>,
  <https://zulip.com/api/create-channel-folder>,
  <https://zulip.com/api/update-channel-folder>, and the bulk reorder
  `PATCH /api/v1/channel_folders` endpoint.
- Channel folder APIs are new in Zulip 11.0 at feature level 389. Folder order
  data is available starting at feature level 414.
- Folder list is available to all authenticated users. Folder mutations are
  admin-only, and channel folder assignment permissions are enforced by Zulip.
- Per-user folder ordering is out of scope; the bulk reorder endpoint updates
  the organization-wide folder order.
