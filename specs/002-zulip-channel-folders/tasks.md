<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- task checklist lines are intentionally long -->

# Tasks: Zulip Channel Folders

**Input**: Design documents from `/specs/002-zulip-channel-folders/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli-commands.md

**Tests**: Included — the plan specifies pytest with `responses` for HTTP mocking and `typer.testing.CliRunner` for CLI tests.

**Organization**: Tasks are grouped by implementation phase so each phase can be
completed in atomic commits while preserving feature traceability.

## Format: `[ID] [P?] [Phase] Description`

- **[P]**: Can run in parallel (different files or independent tests)
- **[Phase]**: Which implementation phase this task belongs to (F1–F7)
- Include exact file paths in descriptions

## Path Conventions

- **API layer**: `lftools_uv/api/endpoints/zulip.py`
- **CLI layer**: `lftools_uv/typer_apps/zulip.py`
- **Tests**: `tests/unit/test_zulip_api.py`, `tests/unit/test_zulip_cli.py`, `tests/unit/test_zulip_folders.py`

---

## Phase F1: API Helpers

**Purpose**: Add reusable API functions for the channel folder endpoints.

- [x] T001 [F1] Add `ChannelFolder` parsing helpers in `lftools_uv/api/endpoints/zulip.py` for id, name, order, description, rendered_description, is_archived, date_created, and creator_id (FR-023, FR-034)
- [x] T002 [F1] Implement `list_channel_folders(client, include_archived=False, limit=None)` using `GET /api/v1/channel_folders` (FR-023)
- [x] T003 [F1] Implement `create_channel_folder(client, name, description="")` using `POST /api/v1/channel_folders/create` and returning `channel_folder_id` (FR-024)
- [x] T004 [F1] Implement `update_channel_folder(client, folder_id, *, name=None, description=None, is_archived=None)` using `PATCH /api/v1/channel_folders/{id}` (FR-025, FR-026, FR-027)
- [x] T005 [F1] Add thin `archive_channel_folder()` and `unarchive_channel_folder()` wrappers that call `update_channel_folder()` with `is_archived` true or false (FR-026, FR-027)

**Checkpoint**: API layer can call all documented channel folder endpoints.

---

## Phase F2: Feature-Level Gating and Validation

**Purpose**: Enforce server compatibility and server-provided folder limits.

- [x] T006 [F2] Add `FEATURE_LEVELS["channel-folders"] = 389` and `FEATURE_LEVELS["channel-folders-order"] = 414` in `lftools_uv/api/endpoints/zulip.py` (FR-031)
- [x] T007 [F2] Gate all folder API helpers and channel folder assignment paths with `check_feature_level(..., 389, "channel-folders")` (FR-030)
- [x] T008 [P] [F2] Add `/register` limit lookup helpers for `max_channel_folder_name_length` and `max_channel_folder_description_length` with per-client caching (FR-033)
- [x] T009 [F2] Validate folder create/update names and descriptions against known limits and produce clear validation errors before API calls (FR-024, FR-025, FR-033)
- [x] T010 [P] [F2] Ensure missing `order` on servers below FL 414 renders as `None` instead of raising parsing errors (FR-034)

**Checkpoint**: Unsupported servers and invalid folder values fail safely.

---

## Phase F3: `zulip folder` Typer Subcommands

**Purpose**: Expose folder lifecycle operations in the CLI.

- [x] T011 [F3] Create `folder` Typer sub-app in `lftools_uv/typer_apps/zulip.py` and register it under the existing `zulip` app (FR-023)
- [x] T012 [F3] Implement `folder list` with `--include-archived`, `--limit`, `--json`, stable table columns, and conditional Status column (FR-023, FR-034)
- [x] T013 [F3] Implement `folder create` with required `--name`, optional `--description`, human ID output, and JSON mutation output (FR-024)
- [x] T014 [F3] Implement `folder update` with required `--folder-id`, optional `--name`/`--description`, and at-least-one-field validation (FR-025)
- [x] T015 [F3] Implement `folder archive` and `folder unarchive` commands using required `--folder-id` and JSON mutation output (FR-026, FR-027, FR-036)
- [x] T016 [P] [F3] Add help text and error messages documenting admin-only mutations and server-side permission handling (FR-035, FR-037)

**Checkpoint**: `lftools-uv zulip folder ...` commands work independently.

---

## Phase F4: Folder Resolution Helper

**Purpose**: Resolve folder names and explicit IDs consistently for channel
assignment.

- [x] T017 [F4] Implement `resolve_channel_folder_token(client, token)` in `lftools_uv/api/endpoints/zulip.py` accepting names, `id:N`, and `none` (FR-028, FR-029, FR-032)
- [x] T018 [F4] Add numeric-looking-name not-found errors that hint to use `id:N` for numeric folder IDs (FR-032)
- [x] T019 [P] [F4] Add ambiguity and archived-folder behavior tests for folder resolution if Zulip responses can include duplicate or archived names (FR-032)

**Checkpoint**: Channel workflows can convert user folder input to `folder_id`.

---

## Phase F5: Channel Create/Update `--folder` Integration

**Purpose**: Add folder assignment to existing channel workflows.

- [x] T020 [F5] Add `--folder` option to `channel create` in `lftools_uv/typer_apps/zulip.py` and pass resolved `folder_id` to the create API payload (FR-028)
- [x] T021 [F5] Add `--folder` option to `channel update` and pass resolved `folder_id` to the stream PATCH payload (FR-029)
- [x] T022 [F5] Add `channel update` clear handling for `--folder none` and `--folder-id 0`, both mapping to `folder_id: null`; reject non-zero `--folder-id` with guidance to use `--folder id:N` (FR-029)
- [x] T023 [F5] Ensure channel create/update with folder assignment short-circuits below FL 389 before mutation (FR-030)
- [x] T024 [F5] Preserve existing channel create/update behavior when no folder flag is supplied (FR-028, FR-029)

**Checkpoint**: Existing channel workflows support folder assignment safely.

---

## Phase F6: Tests

**Purpose**: Cover API helpers, CLI commands, feature gates, and channel
integration.

- [x] T025 [P] [F6] Add API tests for folder list/create/update/archive/unarchive in `tests/unit/test_zulip_folders.py` or `tests/unit/test_zulip_api.py` (FR-023 through FR-027)
- [x] T026 [P] [F6] Add CLI tests for `folder list` table output, JSON output, `--include-archived`, `--limit`, FL 388 rejection, and missing-order behavior below FL 414 (FR-023, FR-030, FR-034)
- [x] T027 [P] [F6] Add CLI tests for folder create/update/archive/unarchive success, validation failures, feature-level errors, no-op archive/unarchive JSON success, and permission error propagation (FR-024 through FR-027, FR-030, FR-035, FR-036)
- [x] T028 [P] [F6] Add folder resolution tests for name, `id:N`, `none`, numeric not-found hints, and missing folder errors (FR-032)
- [x] T029 [P] [F6] Add channel create/update tests for `--folder` name, `id:N`, `none`, `--folder-id 0`, FL 389 gate, and unchanged behavior without folder flags (FR-028 through FR-030)
- [x] T030 [F6] Run `uv run pytest tests/unit/test_zulip_folders.py tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py` and fix failures (FR-023 through FR-036)

**Checkpoint**: Folder feature behavior is covered by unit and CLI tests.

---

## Phase F7: Spec Sync and Docstring Polish

**Purpose**: Keep user-facing docs and implementation comments aligned.

- [x] T031 [P] [F7] Update command docstrings and `--help` text for folder commands and channel `--folder` flags in `lftools_uv/typer_apps/zulip.py` (FR-037)
- [x] T032 [P] [F7] Ensure API helper docstrings cite FL 389, FL 414, and no hard-delete behavior in `lftools_uv/api/endpoints/zulip.py` (FR-030, FR-034, FR-037)
- [x] T033 [F7] Reconcile `specs/002-zulip-channel-folders/` with implemented behavior before final implementation PR review (FR-037)
- [x] T034 [F7] Run `SKIP=basedpyright pre-commit run --all-files` and fix all reported issues without bypassing hooks (FR-037)

---

## Phase F8: Folder Move and Bulk Reorder

**Purpose**: Expose Zulip's bulk channel-folder reordering API through a
semantic move command.

- [x] T035 [F8] Implement `reorder_channel_folders(client, order)` in `lftools_uv/api/endpoints/zulip.py` using `PATCH /api/v1/channel_folders` with JSON-encoded `order` and the existing `channel-folders-order` FL 414 gate (FR-038)
- [x] T036 [F8] Add pure `plan_folder_move(current_order, target_id, reference_id, position)` helper in `lftools_uv/api/endpoints/zulip.py` for before/after move planning (FR-038)
- [x] T037 [F8] Extract shared folder token resolution in `lftools_uv/api/endpoints/zulip.py` and add move-reference support for name, `id:N`, and bare integer IDs (FR-038)
- [x] T038 [F8] Add `zulip folder move --folder-id N --before REF|--after REF` in `lftools_uv/typer_apps/zulip.py`, including mutual exclusion, target/reference validation, archived-folder-inclusive ordering, and success output (FR-038)
- [x] T039 [P] [F8] Add API tests in `tests/unit/test_zulip_api.py` for reorder payloads, FL 414 gating, API error propagation, and direct move-planner cases (FR-038)
- [x] T040 [P] [F8] Add CLI tests in `tests/unit/test_zulip_cli.py` for move before/after, reference resolution by name/`id:N`/bare ID, self-move, missing target, missing numeric reference, and before/after mutex errors (FR-038)
- [x] T041 [F8] Update `specs/002-zulip-channel-folders/` design artifacts to document `folder move`, the bulk reorder API, FL 414 behavior, and quickstart examples (FR-038)

---

## Dependencies & Execution Order

### Phase Dependencies

- **F1 API Helpers**: No implementation dependencies beyond existing Zulip API
  layer from feature 001.
- **F2 Feature-Level Gating and Validation**: Depends on F1 helper shapes.
- **F3 `zulip folder` Commands**: Depends on F1 and F2.
- **F4 Folder Resolution Helper**: Depends on F1 list helper and F2 gate.
- **F5 Channel Integration**: Depends on F4.
- **F6 Tests**: Test tasks can be written before implementation and completed
  alongside each phase.
- **F7 Polish**: Depends on all selected implementation phases.
- **F8 Folder Move**: Depends on F1 list helpers and F4 folder resolution
  patterns; tests and spec sync complete alongside implementation.

### Parallel Opportunities

- T008 and T010 can run in parallel after T006.
- T025 through T029 can be split across API, CLI, resolution, and channel
  integration test files.
- F3 folder commands can be implemented in parallel with F4 resolution after
  the shared API helpers exist, as long as final integration waits for F4.
- T039 and T040 can be implemented in parallel after T035 through T038 define
  the helper and CLI surfaces.

## Implementation Strategy

### MVP First

1. Complete F1 and F2.
2. Complete `folder list` from F3.
3. Validate active/archived listing, JSON output, and FL 389/414 behavior.

### Incremental Delivery

1. Add folder lifecycle helpers and commands.
2. Add folder resolution.
3. Integrate `--folder` into channel create/update.
4. Add `folder move` on top of the existing folder list and resolver helpers.
5. Complete tests and polish.

## Notes

- Each task should be small enough to review as a single commit.
- Tasks that update `tasks.md` remain separate commits per project rules.
- Use Zulip docs for source facts:
  <https://zulip.com/api/get-channel-folders>,
  <https://zulip.com/api/create-channel-folder>, and
  <https://zulip.com/api/update-channel-folder>.
- `folder move` follows the Zulip bulk reorder API at
  `PATCH /api/v1/channel_folders` and deliberately avoids a raw order-array CLI.
