<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- task checklist lines are intentionally long -->

# Tasks: Zulip Show Commands

**Input**: Design documents from `/specs/003-zulip-show-commands/`
**Prerequisites**: plan.md (required), spec.md (required), research.md,
data-model.md, contracts/cli-commands.md

**Tests**: Included — the plan requires mocked Zulip API tests and Typer CLI
tests for all four read-only show commands.

**Organization**: Tasks are grouped by implementation phase so each phase can be
completed in atomic commits while preserving feature traceability.

## Format: `[ID] [P?] [Phase] Description`

- **[P]**: Can run in parallel (different files or independent tests)
- **[Phase]**: Which implementation phase this task belongs to (S1–S8)
- Include exact file paths in descriptions

## Path Conventions

- **API package**: `lftools_uv/api/endpoints/zulip/`
- **CLI package**: `lftools_uv/typer_apps/zulip/`
- **Tests**: `tests/unit/test_zulip_api.py`, `tests/unit/test_zulip_cli.py`, `tests/unit/test_zulip_folders.py`

---

## Phase S1: Shared Detail Rendering and Annotation Registry

**Purpose**: Create common data structures for detail rows, JSON annotations,
and settable status so the four commands behave consistently.

- [ ] T001 [S1] Add `lftools_uv/api/endpoints/zulip/detail.py` with `SettableAnnotation`, detail row, and JSON annotation helpers (FR-042, FR-057, FR-058)
- [ ] T002 [S1] Define the channel settable registry in `detail.py`, using `via --flag` plus setter metadata for exposed flags, clear-only `--folder-id 0`, `via command` archive/unarchive, and `not exposed` for all unexposed permission fields (FR-042, FR-043)
- [ ] T003 [S1] Define group, user, and folder settable registries in `detail.py`, marking current write flags, command-based setters, and server-settable-but-unexposed fields (FR-045, FR-049, FR-053)
- [ ] T004 [S1] Add `lftools_uv/typer_apps/zulip/detail.py` with ASCII table rendering helpers for `Field`, `Value`, `Settable`, and `Notes` rows (FR-058)
- [ ] T005 [P] [S1] Add unit tests for annotation lookup defaults and stable JSON annotation shape in `tests/unit/test_zulip_api.py` (FR-057, FR-058)

**Checkpoint**: All show commands can share one annotation and rendering model.

---

## Phase S2: Shared Resolution Helpers and `--no-resolve`

**Purpose**: Resolve IDs to names by default while giving users a predictable
raw-ID mode.

- [ ] T006 [S2] Add group-setting display helpers in `lftools_uv/api/endpoints/zulip/detail.py` that support integer and object forms with `direct_members` and `direct_subgroups` (FR-055)
- [ ] T007 [S2] Add user reference resolution helpers that reuse `_fetch_users()` and preserve raw IDs when a user cannot be found under `--no-resolve` (FR-055, FR-056)
- [ ] T008 [S2] Add group reference resolution helpers that reuse `_fetch_groups()` and system-role display mappings from `groups.py` (FR-055)
- [ ] T009 [S2] Add folder reference resolution helpers that reuse channel-folder list data and preserve raw `folder_id` in JSON (FR-055)
- [ ] T010 [P] [S2] Add tests for `--no-resolve` avoiding nonessential user, group, folder, and stream list calls in `tests/unit/test_zulip_api.py` (FR-056)

**Checkpoint**: Detail projections can render raw or resolved references with
one shared switch.

---

## Phase S3: `zulip channel show`

**Purpose**: Expose complete raw stream inspection.

- [ ] T011 [S3] Implement `get_channel_detail()` in `lftools_uv/api/endpoints/zulip/detail.py` using `resolve_channel()` raw stream data and derived `type` (FR-039, FR-040, FR-041)
- [ ] T012 [S3] Resolve channel `folder_id`, `creator_id`, and permission group-setting values by default and preserve raw values in JSON (FR-040, FR-055)
- [ ] T013 [S3] Add `channel show` to `lftools_uv/typer_apps/zulip/channel_read.py` with positional channel or `--channel-id`, `--include-archived`, `--no-resolve`, and hidden `--json` (FR-039, FR-056, FR-057)
- [ ] T014 [P] [S3] Add API tests for all returned raw stream fields, feature-level-gated omissions, missing channels, secondary resolver failures, derived type, all unexposed permission annotations, group-setting JSON shape, and settable annotations in `tests/unit/test_zulip_api.py` (FR-040 through FR-043)
- [ ] T015 [P] [S3] Add CLI tests for channel show table, JSON, channel ID targeting, missing channel errors, archived target handling, secondary resolver failure, and `--no-resolve` skipping secondary lookups in `tests/unit/test_zulip_cli.py` (FR-039, FR-056, FR-057)

**Checkpoint**: `lftools-uv zulip channel show` works independently.

---

## Phase S4: `zulip group show`

**Purpose**: Expose full user-group inspection, including members.

- [ ] T016 [S4] Implement `get_group_detail()` in `lftools_uv/api/endpoints/zulip/detail.py` using raw `_fetch_groups()` objects and existing group filter behavior (FR-044, FR-045)
- [ ] T017 [S4] Add positional group-name targeting and exactly-one validation across positional group, `--group-name`, and `--group-id` in `lftools_uv/typer_apps/zulip/groups.py` (FR-044)
- [ ] T018 [S4] Resolve group members to Full Name, Email, and User ID rows by default; render raw IDs with `--no-resolve` (FR-046)
- [ ] T019 [S4] Resolve `direct_subgroup_ids` to direct subgroup display names only; do not recurse (FR-047)
- [ ] T020 [P] [S4] Add API tests for custom group, system group, deactivated group, missing group, secondary resolver failures, permissions, members, direct subgroups, and ambiguity in `tests/unit/test_zulip_api.py` (FR-045 through FR-047)
- [ ] T021 [P] [S4] Add CLI tests for group show positional, `--group-name`, `--group-id`, no target, positional-plus-flag conflicts, numeric-looking positional-as-name, table output, JSON, missing group, secondary resolver failure, and `--no-resolve` skipping secondary lookups in `tests/unit/test_zulip_cli.py` (FR-044, FR-057)

**Checkpoint**: `lftools-uv zulip group show` works independently.

---

## Phase S5: `zulip user show`

**Purpose**: Expose full user-account inspection.

- [ ] T022 [S5] Implement raw user detail fetching in `lftools_uv/api/endpoints/zulip/detail.py`, requesting custom profile fields where supported (FR-048, FR-049)
- [ ] T023 [S5] Reuse `_resolve_single_user()` semantics for email, ID, and full-name targeting, including ambiguity errors (FR-048)
- [ ] T024 [S5] Add role label derivation for Zulip role values 100, 200, 300, 400, and 600, using `administrator` for role 200 (FR-050)
- [ ] T025 [S5] Add derived group membership by scanning raw groups for the user ID when resolution is enabled; skip with `--no-resolve` (FR-051, FR-056)
- [ ] T026 [S5] Add `user show` to `lftools_uv/typer_apps/zulip/users.py` with `--by-email`, `--by-id`, `--by-name`, `--no-resolve`, and hidden `--json` (FR-048, FR-057)
- [ ] T027 [P] [S5] Add API tests for missing users, role labels, bot fields, profile fields, deleted/imported-stub markers, membership, secondary group resolver failures, and `--no-resolve` in `tests/unit/test_zulip_api.py` (FR-049 through FR-051)
- [ ] T028 [P] [S5] Add CLI tests for user show by email, by ID, by name, missing user, ambiguous name, table output, JSON, secondary resolver failure, and `--no-resolve` skipping group lookup in `tests/unit/test_zulip_cli.py` (FR-048, FR-057)

**Checkpoint**: `lftools-uv zulip user show` works independently.

---

## Phase S6: `zulip folder show`

**Purpose**: Expose full channel-folder inspection.

- [ ] T029 [S6] Implement `get_folder_detail()` in `lftools_uv/api/endpoints/zulip/detail.py` using raw channel-folder objects and a show-specific folder resolver that treats `none` as an ordinary name, accepts `id:N`, and treats bare numeric tokens as names (FR-052, FR-053)
- [ ] T030 [S6] Resolve `creator_id` to a user display by default and preserve raw ID in JSON (FR-053, FR-055)
- [ ] T031 [S6] Enumerate assigned channels by listing streams and filtering on raw `folder_id`; skip enumeration with `--no-resolve` (FR-054, FR-056)
- [ ] T032 [S6] Add `folder show` to `lftools_uv/typer_apps/zulip/folders.py` with folder token, `--no-resolve`, and hidden `--json` (FR-052, FR-057)
- [ ] T033 [P] [S6] Add API tests for folder name, `id:N`, numeric-name hint, `none` not being special, missing folders, secondary resolver failures, creator resolution, assigned-channel filtering, FL 414 `order` absence, and `--no-resolve` in `tests/unit/test_zulip_folders.py` (FR-052 through FR-056)
- [ ] T034 [P] [S6] Add CLI tests for folder show table, JSON, missing folder errors, `none` as a normal name, ambiguity, secondary resolver failure, and `--no-resolve` skipping creator/channel lookups in `tests/unit/test_zulip_folders.py` (FR-052, FR-057)

**Checkpoint**: `lftools-uv zulip folder show` works independently.

---

## Phase S7: Tests and Integration Validation

**Purpose**: Ensure all show commands are covered together and do not regress
existing list or mutation behavior.

- [ ] T035 [S7] Add cross-command JSON schema tests ensuring raw objects, derived sections, resolved sections, group-setting display shape, and annotations are stable for all four commands (FR-057)
- [ ] T036 [S7] Add tests that existing `channel list`, `group list`, `user list`, and `folder list` output remains unchanged (FR-059)
- [ ] T037 [S7] Run `uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py tests/unit/test_zulip_folders.py` and fix failures (FR-059)
- [ ] T038 [S7] Run `uv run ruff check .` and `uv run mypy lftools_uv` and fix failures (FR-059)
- [ ] T039 [S7] Run `SKIP=basedpyright pre-commit run --all-files` and fix reported issues without bypassing hooks (FR-059)

---

## Phase S8: Documentation and Spec Sync

**Purpose**: Keep help text, quickstart, and implementation details aligned.

- [ ] T040 [P] [S8] Update `--help` text for each show command to mention `--no-resolve` lookup cost without adding new internal spec IDs to user-facing strings (FR-056, FR-060)
- [ ] T041 [P] [S8] Update any Zulip quickstart or docs that list available Zulip commands to include the four show commands (FR-060)
- [ ] T042 [S8] Reconcile `specs/003-zulip-show-commands/` with implemented behavior before final implementation PR review (FR-060)

---

## Dependencies & Execution Order

### Phase Dependencies

- **S1 Shared Rendering**: No implementation dependencies beyond existing Zulip
  packages.
- **S2 Resolution Helpers**: Depends on S1 annotation/data shapes.
- **S3 Channel Show**: Depends on S1 and S2.
- **S4 Group Show**: Depends on S1 and S2.
- **S5 User Show**: Depends on S1 and S2.
- **S6 Folder Show**: Depends on S1 and S2.
- **S7 Tests**: Command-specific tests can be written with each command; final
  validation depends on S3 through S6.
- **S8 Docs/Spec Sync**: Depends on selected implementation behavior.

### Parallel Opportunities

- S3, S4, S5, and S6 can proceed in parallel after S1 and S2 define shared
  contracts.
- T014/T015, T020/T021, T027/T028, and T033/T034 can run in parallel by test
  file and command group.
- Documentation updates in S8 can run alongside final test cleanup.

## Implementation Strategy

### MVP First

1. Complete S1 and S2.
2. Implement `channel show` (S3) because it addresses the largest lossy-list
   gap.
3. Validate channel show independently with API and CLI tests.

### Incremental Delivery

1. Add `group show` with member expansion.
2. Add `user show` with profile and membership detail.
3. Add `folder show` with assigned-channel enumeration.
4. Run focused and pre-commit validation.
5. Sync docs and help text.

## Notes

- Tasks update documents belong in separate commits when task status changes.
- Show commands must not mutate Zulip state.
- Do not add write flags for currently unexposed channel permission fields,
  including add/administer/send, delete-message, move-message, resolve-topic,
  and create-topic group settings, in this feature.
- Do not implement recursive subgroup expansion.
