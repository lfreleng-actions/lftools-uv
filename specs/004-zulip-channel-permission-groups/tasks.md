<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- task checklist lines are intentionally long -->

# Tasks: Zulip Channel Permission Groups

**Input**: Design documents from `/specs/004-zulip-channel-permission-groups/`
**Prerequisites**: plan.md (required), spec.md (required), research.md,
data-model.md, contracts/cli-commands.md

**Tests**: Included — the plan requires mocked Zulip API tests and Typer CLI
tests for each flag, plus `channel show` annotation tests.

**Organization**: Tasks are grouped by stacked implementation PR. Phase P0 and
P1 land in the first implementation PR. P2 stacks on P1. P3 stacks on P2.
Each flag phase includes its own tests and its own `channel show` annotation
update so reviewers can validate one permission at a time.

## Format: `[ID] [P?] [Phase] Description`

- **[P]**: Can run in parallel (different files or independent tests)
- **[Phase]**: Which implementation phase the task belongs to (P0–P4)
- Include exact file paths in descriptions

## Path Conventions

- **API package**: `lftools_uv/api/endpoints/zulip/`
- **CLI package**: `lftools_uv/typer_apps/zulip/`
- **Tests**: `tests/unit/test_zulip_api.py`, `tests/unit/test_zulip_cli.py`

---

## Phase P0: Shared Foundation (First implementation PR)

**Purpose**: Add common feature-level constants and shared plumbing so each
flag-specific PR does not duplicate group-setting logic.

**Stacking note**: P0 MUST land in the first implementation PR together with
P1. P2 and P3 depend on this foundation.

- [ ] T001 [P0] Add `FEATURE_LEVELS["can-add-subscribers-group"] = 342`, `FEATURE_LEVELS["can-administer-channel-group"] = 325`, and `FEATURE_LEVELS["can-send-message-group"] = 333` in `lftools_uv/api/endpoints/zulip/features.py` (FR-067)
- [ ] T002 [P0] Add a shared permission-flag metadata helper or mapping in `lftools_uv/api/endpoints/zulip/channel_update.py` or a small existing Zulip module so create/update code can check feature levels without duplicating field names (FR-061 through FR-068)
- [ ] T003 [P0] Add a shared API helper for resolving optional permission group specs with `resolve_groups()` and returning `GroupSettingValue | None`, preserving existing `id:NUM`, ambiguity, and numeric-not-found behavior (FR-064)
- [ ] T004 [P0] Extend create/update validation paths to recognize the three new optional settings for at-least-one-setting checks without changing behavior when none are supplied (FR-071)
- [ ] T005 [P] [P0] Add API tests in `tests/unit/test_zulip_api.py` that the new feature-level constants exist with values 342, 325, and 333 (FR-067)
- [ ] T006 [P] [P0] Add unit tests for the shared resolver/helper using a single group, multiple groups, `id:NUM`, ambiguous names, empty specs, and bare numeric not-found hints (FR-064)

**Checkpoint**: Shared feature constants and resolver plumbing are ready for all
three flag PRs.

---

## Phase P1: `--can-add-subscribers-group` (First implementation PR)

**Purpose**: Expose `can_add_subscribers_group`, including its tests and
`channel show` annotation update.

**Stacking note**: P1 ships with P0 in the first implementation PR. Later PRs
stack on this branch.

- [ ] T007 [P1] Add `can_add_subscribers_group_value` to `create_channel()` in `lftools_uv/api/endpoints/zulip/channel_create.py` and send raw `can_add_subscribers_group` when provided (FR-061, FR-065)
- [ ] T008 [P1] Gate `can_add_subscribers_group_value` at `FEATURE_LEVELS["can-add-subscribers-group"]` before the create mutation (FR-068)
- [ ] T009 [P1] Add `can_add_subscribers_group` to `_ChannelUpdate`, update validation, resolve it with the shared helper, and send `{"new": value}` as `can_add_subscribers_group` in `lftools_uv/api/endpoints/zulip/channel_update.py` (FR-061, FR-066)
- [ ] T010 [P1] Gate update usage of `can_add_subscribers_group` at FL 342 before resolving groups or patching (FR-068)
- [ ] T011 [P1] Add `--can-add-subscribers-group` to `lftools_uv/typer_apps/zulip/channel_create.py` help text with `id:NUM` syntax and pass the resolved value to the API layer (FR-061, FR-072)
- [ ] T012 [P1] Add `--can-add-subscribers-group` to `lftools_uv/typer_apps/zulip/channel_update.py` help text with `id:NUM` syntax and pass the raw spec to the API layer (FR-061, FR-072)
- [ ] T013 [P1] Update `CHANNEL_ANNOTATIONS` in `lftools_uv/api/endpoints/zulip/detail.py` so `can_add_subscribers_group` uses setter `--can-add-subscribers-group` and notes `FL 342` (FR-073)
- [ ] T014 [P] [P1] Add API tests in `tests/unit/test_zulip_api.py` for create raw integer/object payloads, update `{"new": ...}` payloads, FL 341 rejection, and no request mutation on gate failure (FR-061, FR-065, FR-066, FR-068)
- [ ] T015 [P] [P1] Add CLI tests in `tests/unit/test_zulip_cli.py` for create/update option forwarding, help text, group-resolution errors, and JSON/human feature-level failures for `--can-add-subscribers-group` (FR-061, FR-072, FR-074)
- [ ] T016 [P1] Add `channel show` annotation tests in `tests/unit/test_zulip_api.py` confirming `can_add_subscribers_group` reports `via --flag` and setter `--can-add-subscribers-group` (FR-073)
- [ ] T017 [P1] Run `uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py` and fix failures for P0/P1 (FR-074)
- [ ] T018 [P1] Run `uv run ruff check .` and `uv run mypy lftools_uv` for P0/P1 changes (FR-074)

**Checkpoint**: First implementation PR can independently set who can add
subscribers and keeps show annotations accurate.

---

## Phase P2: `--can-administer-channel-group` (Second implementation PR)

**Purpose**: Expose `can_administer_channel_group`, including its tests and
`channel show` annotation update.

**Stacking note**: P2 stacks on the P0/P1 branch and should contain only the
administer-channel flag delta plus tests/docs for that flag.

- [ ] T019 [P2] Add `can_administer_channel_group_value` to `create_channel()` in `lftools_uv/api/endpoints/zulip/channel_create.py` and send raw `can_administer_channel_group` when provided (FR-062, FR-065)
- [ ] T020 [P2] Gate `can_administer_channel_group_value` at `FEATURE_LEVELS["can-administer-channel-group"]` before the create mutation (FR-068)
- [ ] T021 [P2] Add `can_administer_channel_group` to `_ChannelUpdate`, validation, resolver calls, and PATCH request construction in `lftools_uv/api/endpoints/zulip/channel_update.py` (FR-062, FR-066)
- [ ] T022 [P2] Gate update usage of `can_administer_channel_group` at FL 325 before resolving groups or patching (FR-068)
- [ ] T023 [P2] Add `--can-administer-channel-group` to `lftools_uv/typer_apps/zulip/channel_create.py` help text with `id:NUM` syntax and pass the resolved value to the API layer (FR-062, FR-072)
- [ ] T024 [P2] Add `--can-administer-channel-group` to `lftools_uv/typer_apps/zulip/channel_update.py` help text with `id:NUM` syntax and pass the raw spec to the API layer (FR-062, FR-072)
- [ ] T025 [P2] Update `CHANNEL_ANNOTATIONS` in `lftools_uv/api/endpoints/zulip/detail.py` so `can_administer_channel_group` uses setter `--can-administer-channel-group` and notes `FL 325` (FR-073)
- [ ] T026 [P] [P2] Add API tests in `tests/unit/test_zulip_api.py` for create raw integer/object payloads, update `{"new": ...}` payloads, FL 324 rejection, and no `can_add_subscribers_group` regression (FR-062, FR-065, FR-066, FR-068)
- [ ] T027 [P] [P2] Add CLI tests in `tests/unit/test_zulip_cli.py` for create/update option forwarding, help text, group-resolution errors, and JSON/human feature-level failures for `--can-administer-channel-group` (FR-062, FR-072, FR-074)
- [ ] T028 [P2] Add `channel show` annotation tests in `tests/unit/test_zulip_api.py` confirming `can_administer_channel_group` reports `via --flag` and setter `--can-administer-channel-group` (FR-073)
- [ ] T029 [P2] Run `uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py` and fix P2 failures (FR-074)
- [ ] T030 [P2] Run `uv run ruff check .` and `uv run mypy lftools_uv` for P2 changes (FR-074)

**Checkpoint**: Second implementation PR can independently set who can
administer channels and preserves the first PR's behavior.

---

## Phase P3: `--can-send-message-group` (Third implementation PR)

**Purpose**: Expose `can_send_message_group`, including no legacy fallback,
its tests, and `channel show` annotation update.

**Stacking note**: P3 stacks on P2 and should contain only the send-message flag
delta plus tests/docs for that flag.

- [ ] T031 [P3] Add `can_send_message_group_value` to `create_channel()` in `lftools_uv/api/endpoints/zulip/channel_create.py` and send raw `can_send_message_group` when provided (FR-063, FR-065)
- [ ] T032 [P3] Gate `can_send_message_group_value` at `FEATURE_LEVELS["can-send-message-group"]` before the create mutation (FR-068)
- [ ] T033 [P3] Add `can_send_message_group` to `_ChannelUpdate`, validation, resolver calls, and PATCH request construction in `lftools_uv/api/endpoints/zulip/channel_update.py` (FR-063, FR-066)
- [ ] T034 [P3] Gate update usage of `can_send_message_group` at FL 333 before resolving groups or patching (FR-068)
- [ ] T035 [P3] Ensure no create or update code path writes `stream_post_policy` for `--can-send-message-group` on any server version (FR-069)
- [ ] T036 [P3] Add `--can-send-message-group` to `lftools_uv/typer_apps/zulip/channel_create.py` help text with `id:NUM` syntax and pass the resolved value to the API layer (FR-063, FR-072)
- [ ] T037 [P3] Add `--can-send-message-group` to `lftools_uv/typer_apps/zulip/channel_update.py` help text with `id:NUM` syntax and pass the raw spec to the API layer (FR-063, FR-072)
- [ ] T038 [P3] Update `CHANNEL_ANNOTATIONS` in `lftools_uv/api/endpoints/zulip/detail.py` so `can_send_message_group` uses setter `--can-send-message-group` and notes `FL 333` (FR-073)
- [ ] T039 [P] [P3] Add API tests in `tests/unit/test_zulip_api.py` for create raw integer/object payloads, update `{"new": ...}` payloads, FL 332 rejection, absence of `stream_post_policy`, and no regressions for the prior two flags (FR-063, FR-066, FR-068, FR-069)
- [ ] T040 [P] [P3] Add CLI tests in `tests/unit/test_zulip_cli.py` for create/update option forwarding, help text, group-resolution errors, and JSON/human feature-level failures for `--can-send-message-group` (FR-063, FR-072, FR-074)
- [ ] T041 [P3] Add `channel show` annotation tests in `tests/unit/test_zulip_api.py` confirming `can_send_message_group` reports `via --flag` and setter `--can-send-message-group` (FR-073)
- [ ] T042 [P3] Run `uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py` and fix P3 failures (FR-074)
- [ ] T043 [P3] Run `uv run ruff check .` and `uv run mypy lftools_uv` for P3 changes (FR-074)

**Checkpoint**: Third implementation PR can independently set who can post and
explicitly avoids legacy posting-policy fallback.

---

## Phase P4: Final Validation and Documentation Sync (Each implementation PR)

**Purpose**: Keep contracts, quickstart, and command behavior aligned as each
stacked PR lands.

- [ ] T044 [P4] For each implementation PR, update any user-facing Zulip docs or quickstart references touched by that PR without adding internal spec/task IDs to help text (FR-072, FR-075)
- [ ] T045 [P4] For each implementation PR, reconcile `specs/004-zulip-channel-permission-groups/` only if implementation discovers a documented API fact that changes this spec; cite official Zulip docs in the change (FR-075)
- [ ] T046 [P4] For each implementation PR, run `SKIP=basedpyright pre-commit run --all-files` and fix reported issues without bypassing hooks (FR-074)

---

## Dependencies & Execution Order

### Stacked PR Order

1. **PR 1**: P0 shared foundation + P1 `--can-add-subscribers-group`.
2. **PR 2**: P2 `--can-administer-channel-group`, stacked on PR 1.
3. **PR 3**: P3 `--can-send-message-group`, stacked on PR 2.

### Phase Dependencies

- **P0 Shared Foundation**: No implementation dependencies beyond existing
  Zulip packages.
- **P1 Add-subscribers flag**: Depends on P0 helper decisions and lands with
  P0.
- **P2 Administer-channel flag**: Depends on P0 and should reuse its helper
  with no duplicate resolver logic.
- **P3 Send-message flag**: Depends on P0 and should reuse its helper with no
  duplicate resolver logic.
- **P4 Validation**: Runs for each implementation PR before push/review.

### Parallel Opportunities

- P0 tests for constants and resolver helper can run in parallel with P1 code
  once helper names are chosen.
- Within each flag phase, API tests and CLI tests can be written in parallel.
- Later stacked PRs should not proceed independently until the prior stack base
  is stable, to avoid repeated rebases over shared create/update signatures.

## Implementation Strategy

### MVP First

1. Implement P0 and P1 together.
2. Validate one full create/update/show path for
   `--can-add-subscribers-group`.
3. Use the merged helper pattern as the template for P2 and P3.

### Incremental Delivery

1. PR 1 proves the shared design and first flag.
2. PR 2 adds the second field with minimal churn.
3. PR 3 adds the send-message field and proves there is no legacy fallback.
4. After all three land, `channel show` annotations for all three fields are
   aligned with writable CLI flags.

## Notes

- The three-way split is sound even though the flags are similar: it minimizes
  review risk for each exact Zulip field after previous silent API-field bugs.
- The split creates some repeated test structure, but P0 should keep code
  duplication low.
- Tasks update documents belong in separate commits when task status changes.
- No implementation PR should rely on Zulip accepting unknown fields; feature
  gates and exact field names are required.
