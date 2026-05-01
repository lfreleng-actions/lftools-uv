<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->
<!-- markdownlint-disable MD013 -- task checklist lines are intentionally long -->

# Tasks: Zulip Channel Management

**Input**: Design documents from `/specs/001-zulip-channel-mgmt/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/cli-commands.md

**Tests**: Included — the plan specifies pytest with `responses` for HTTP mocking and `typer.testing.CliRunner` for CLI tests.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **API layer**: `lftools_uv/api/endpoints/zulip.py`
- **CLI layer**: `lftools_uv/typer_apps/zulip.py`
- **CLI registration**: `lftools_uv/typer_apps/root.py`
- **Tests**: `tests/unit/test_zulip_api.py`, `tests/unit/test_zulip_cli.py`, `tests/unit/test_zulip_config.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization, dependency addition, and basic file structure

- [ ] T001 Add `zulip` as optional dependency under `[project.optional-dependencies]` in pyproject.toml (installed via `lftools-uv[zulip]`) and run `uv lock`
- [ ] T002 [P] Create empty module file lftools_uv/api/endpoints/zulip.py with license header and module docstring
- [ ] T003 [P] Create empty module file lftools_uv/typer_apps/zulip.py with license header, Typer app instantiation, and module docstring
- [ ] T004 [P] Create empty test files tests/unit/test_zulip_api.py, tests/unit/test_zulip_cli.py, and tests/unit/test_zulip_config.py with license headers
- [ ] T005 Register the zulip Typer sub-app in lftools_uv/typer_apps/root.py (add `app.add_typer(zulip_app, name="zulip")`)
- [ ] T005a [P] Implement optional dependency guard in lftools_uv/typer_apps/zulip.py — detect missing `zulip` package at import time, register command group in CLI help regardless, show user-friendly error on invocation if extra not installed (FR-022). Canonical error message:

  ```text
  Zulip support requires the zulip extra. Install with:
    pip install "lftools-uv[zulip]"
  ```

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented — config resolution, Zulip client initialization, feature-level detection, shared helpers

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T006 Implement ZulipConfig resolution logic in lftools_uv/api/endpoints/zulip.py — resolve config from `--zuliprc` flag > `./zuliprc` > lftools.ini `[zulip]` section > `~/.zuliprc` per FR-011/FR-012 precedence
- [ ] T007 Implement Zulip client factory function in lftools_uv/api/endpoints/zulip.py — instantiate `zulip.Client` from resolved config, expose `get_client(zuliprc: Path | None) -> zulip.Client`
- [ ] T008 Implement server feature-level detection in lftools_uv/api/endpoints/zulip.py — call `GET /server_settings`, cache `zulip_feature_level`, expose `check_feature_level(client, required_level, feature_name)` that raises a domain error with FR-019 canonical message format
- [ ] T009 [P] Define domain exception classes in lftools_uv/api/endpoints/zulip.py — `ZulipConfigError`, `ZulipAPIError`, `ZulipFeatureLevelError`, `ZulipAmbiguityError`, `ZulipLockoutError`
- [ ] T010 [P] Implement shared CLI output helpers in lftools_uv/typer_apps/zulip.py — `--zuliprc` callback, `--json` flag handling, table formatting with `tabulate`, error display with non-zero exit, `MutationResult` JSON formatter
- [ ] T011 [P] Implement channel target resolution helper in lftools_uv/api/endpoints/zulip.py — resolve channel by name (case-insensitive) or `--channel-id`, search active-only by default, include-archived if flag set, produce helpful "not found" error with `--include-archived` suggestion per FR-018
- [ ] T012 [P] Implement group resolution helper in lftools_uv/api/endpoints/zulip.py — parse comma-separated group names/IDs from `--allow-group` and `--can-remove-subscribers-group` values, resolve each to numeric group ID, handle `id:NUM` prefix, handle system role group display-name-to-API-name mapping, build group-setting value (simple int or complex form), handle ambiguity errors
- [ ] T013 [P] Implement user resolution helper in lftools_uv/api/endpoints/zulip.py — resolve user by email, user_id, or full_name per `--by-email`/`--by-id`/`--by-name` flags, detect ambiguous `--by-name` matches and raise `ZulipAmbiguityError` with listing of matching users
- [ ] T014 Write unit tests for config resolution in tests/unit/test_zulip_config.py — test all four precedence levels, missing config error, malformed file error
- [ ] T015 [P] Write unit tests for feature-level detection in tests/unit/test_zulip_api.py — test passing/failing feature level checks, canonical error message format
- [ ] T016 [P] Write unit tests for channel target resolution in tests/unit/test_zulip_api.py — test name match (case-insensitive), ID match, not-found with suggestion, include-archived behavior
- [ ] T017 [P] Write unit tests for group resolution in tests/unit/test_zulip_api.py — test single name, multiple names, id: prefix, system role groups, ambiguity error, Nobody detection
- [ ] T018 [P] Write unit tests for user resolution in tests/unit/test_zulip_api.py — test by-email, by-id, by-name, ambiguity error with listing

**Checkpoint**: Foundation ready — user story implementation can now begin

---

## Phase 3: User Story 1 — List Available Channels (Priority: P1) 🎯 MVP

**Goal**: Provide `lftools-uv zulip channel list` command showing all active channels with name, description, type, and subscriber count

**Independent Test**: Run `lftools-uv zulip channel list` against a Zulip server; verify all known active channels appear with correct metadata. Test `--include-archived` and `--json` flags.

### Tests for User Story 1

- [ ] T019 [P] [US1] Write CLI tests for `channel list` in tests/unit/test_zulip_cli.py — test table output, `--json` output, `--include-archived` flag, config error display, empty channel list
- [ ] T020 [P] [US1] Write API tests for `list_channels()` in tests/unit/test_zulip_api.py — mock Zulip API response, test active-only filtering, include-archived, response parsing

### Implementation for User Story 1

- [ ] T021 [US1] Implement `list_channels(client, include_archived=False)` in lftools_uv/api/endpoints/zulip.py — call Zulip streams API, parse response into list of channel dicts with stream_id, name, description, type, subscriber_count, is_archived
- [ ] T022 [US1] Implement `channel list` CLI command in lftools_uv/typer_apps/zulip.py — create `channel` sub-app, add `list` command with `--include-archived` and `--json` flags, format table output with tabulate, handle errors

**Checkpoint**: User Story 1 is fully functional — `lftools-uv zulip channel list` works independently

---

## Phase 4: User Story 2 — List Zulip Users (Priority: P1)

**Goal**: Provide `lftools-uv zulip user list` command showing all active users with full name, email, and user ID

**Independent Test**: Run `lftools-uv zulip user list` and verify active human users appear. Test `--include-bots`, `--include-deactivated`, and `--json` flags.

### Tests for User Story 2

- [ ] T023 [P] [US2] Write CLI tests for `user list` in tests/unit/test_zulip_cli.py — test table output, `--json` output, `--include-bots`, `--include-deactivated`, config error
- [ ] T024 [P] [US2] Write API tests for `list_users()` in tests/unit/test_zulip_api.py — mock Zulip users API, test filtering logic

### Implementation for User Story 2

- [ ] T025 [US2] Implement `list_users(client, include_bots=False, include_deactivated=False)` in lftools_uv/api/endpoints/zulip.py — call Zulip users API, parse response into list of user dicts with user_id, full_name, email, is_bot, is_active
- [ ] T026 [US2] Implement `user list` CLI command in lftools_uv/typer_apps/zulip.py — create `user` sub-app, add `list` command with `--include-bots`, `--include-deactivated`, and `--json` flags, format table output

**Checkpoint**: User Story 2 is fully functional — `lftools-uv zulip user list` works independently

---

## Phase 5: User Story 3 — List User Groups (Priority: P1)

**Goal**: Provide `lftools-uv zulip group list` command showing all user groups (custom and system role groups) with name, group ID, description, member count, and type

**Independent Test**: Run `lftools-uv zulip group list` and verify both custom and system role groups appear. Test `--group-name`, `--group-id`, `--json` flags and ambiguity handling.

### Tests for User Story 3

- [ ] T027 [P] [US3] Write CLI tests for `group list` in tests/unit/test_zulip_cli.py — test table output, `--json` output, `--group-name` filter, `--group-id` filter, ambiguity error display, config error
- [ ] T028 [P] [US3] Write API tests for `list_groups()` in tests/unit/test_zulip_api.py — mock Zulip user_groups API, test custom/system group parsing, filtering, ambiguity detection

### Implementation for User Story 3

- [ ] T029 [US3] Implement `list_groups(client, group_name=None, group_id=None)` in lftools_uv/api/endpoints/zulip.py — call Zulip user_groups API, parse response into list of group dicts with group_id, name, description, member_count, type (custom/system), handle system role group display name mapping, handle ambiguous name filter
- [ ] T030 [US3] Implement `group list` CLI command in lftools_uv/typer_apps/zulip.py — create `group` sub-app, add `list` command with `--group-name`, `--group-id`, and `--json` flags, format table output

**Checkpoint**: User Story 3 is fully functional — `lftools-uv zulip group list` works independently

---

## Phase 6: User Story 4 — Create a Channel (Priority: P1)

**Goal**: Provide `lftools-uv zulip channel create` command supporting public, web-public, and private channel creation with `--subscribe`, `--allow-group`, `--can-remove-subscribers-group`, `--announce`/`--no-announce`, and `--topic-policy` flags

**Independent Test**: Create channels of each type and verify they appear in `channel list`. Test lockout prevention, feature-level detection, ambiguity errors, and JSON output.

**Dependency**: Requires US2 (user resolution) and US3 (group resolution) for `--subscribe` and `--allow-group` functionality.

### Tests for User Story 4

- [ ] T031 [P] [US4] Write CLI tests for `channel create` in tests/unit/test_zulip_cli.py — test public create success, private create with --subscribe, private create without subscribers (lockout error), --allow-group usage, --allow-group Nobody rejection, ambiguity errors, --announce/--no-announce mutual exclusivity, --topic-policy validation, --json output, web-public feature-level error, --can-remove-subscribers-group usage
- [ ] T032 [P] [US4] Write API tests for `create_channel()` in tests/unit/test_zulip_api.py — mock Zulip subscribe endpoint, test all parameter combinations, lockout validation, feature-level checks, group-setting value construction (simple and complex forms)

### Implementation for User Story 4

- [ ] T033 [US4] Implement `create_channel()` in lftools_uv/api/endpoints/zulip.py — validate inputs (lockout prevention for private, Nobody exclusion, announce mutex, topic-policy values), check feature levels (web-public, topic-policy, group-access, can-remove-subscribers-group), resolve users and groups, build Zulip API payload with correct group-setting value format (raw for POST), call POST `/users/me/subscriptions`, return MutationResult
- [ ] T034 [US4] Implement `channel create` CLI command in lftools_uv/typer_apps/zulip.py — add `create` command to `channel` sub-app with positional `name`, `--description`, `--type`, `--subscribe` (multi), `--by-email`/`--by-id`/`--by-name`, `--allow-group`, `--can-remove-subscribers-group`, `--announce`/`--no-announce`, `--topic-policy` flags, format success/error output, handle `--json` with standard mutation schema

**Checkpoint**: User Story 4 is fully functional — `lftools-uv zulip channel create` works for all channel types

---

## Phase 7: User Story 5 — Subscribe Users to a Channel (Priority: P2)

**Goal**: Provide `lftools-uv zulip channel subscribe` command to add one or more users to a channel by email, ID, or name

**Independent Test**: Subscribe users and verify membership via `channel subscribers` command. Test bulk operations, ambiguity errors, no-op idempotency, and JSON output.

### Tests for User Story 5

- [ ] T035 [P] [US5] Write CLI tests for `channel subscribe` in tests/unit/test_zulip_cli.py — test single user by email, bulk users, --by-id, --by-name, ambiguity error, missing identifier flag error, already-subscribed no-op, --json bulk output, channel-id vs positional, numeric channel name handling
- [ ] T036 [P] [US5] Write API tests for `subscribe_users()` in tests/unit/test_zulip_api.py — mock Zulip subscribe endpoint, test single/bulk, already-subscribed, invalid user, partial success

### Implementation for User Story 5

- [ ] T037 [US5] Implement `subscribe_users(client, channel, users, id_mode)` in lftools_uv/api/endpoints/zulip.py — resolve channel target, resolve user identifiers per id_mode, call Zulip subscribe API (up to 50 users per spec constraint), handle partial results, return bulk MutationResult with results/errors
- [ ] T038 [US5] Implement `channel subscribe` CLI command in lftools_uv/typer_apps/zulip.py — add `subscribe` command with positional `[channel] USER [USER...]` signature, `--channel-id`, `--by-email`/`--by-id`/`--by-name` flags, `--include-archived`, `--json`, handle first-positional-is-channel logic when --channel-id absent

**Checkpoint**: User Story 5 is fully functional — `lftools-uv zulip channel subscribe` works independently

---

## Phase 8: User Story 6 — Unsubscribe Users from a Channel (Priority: P2)

**Goal**: Provide `lftools-uv zulip channel unsubscribe` command to remove one or more users from a channel

**Independent Test**: Unsubscribe users and verify they no longer appear in subscriber list. Test no-op idempotency and JSON output.

### Tests for User Story 6

- [ ] T039 [P] [US6] Write CLI tests for `channel unsubscribe` in tests/unit/test_zulip_cli.py — test single user, bulk, --by-name ambiguity, not-subscribed no-op, --json output
- [ ] T040 [P] [US6] Write API tests for `unsubscribe_users()` in tests/unit/test_zulip_api.py — mock Zulip unsubscribe endpoint, test single/bulk, not-subscribed, partial

### Implementation for User Story 6

- [ ] T041 [US6] Implement `unsubscribe_users(client, channel, users, id_mode)` in lftools_uv/api/endpoints/zulip.py — resolve channel target, resolve user identifiers, call Zulip unsubscribe API, handle partial results, return bulk MutationResult
- [ ] T042 [US6] Implement `channel unsubscribe` CLI command in lftools_uv/typer_apps/zulip.py — add `unsubscribe` command with same signature pattern as subscribe, handle `--json` with bulk mutation schema

**Checkpoint**: User Story 6 is fully functional — `lftools-uv zulip channel unsubscribe` works independently

---

## Phase 9: User Story 7 — List Channel Subscribers (Priority: P2)

**Goal**: Provide `lftools-uv zulip channel subscribers` command to list all subscribers of a specific channel

**Independent Test**: List subscribers of a known channel and verify the output includes expected users with full name, email, and user ID.

### Tests for User Story 7

- [ ] T043 [P] [US7] Write CLI tests for `channel subscribers` in tests/unit/test_zulip_cli.py — test table output, --json output, channel not found error, --channel-id usage, --include-archived
- [ ] T044 [P] [US7] Write API tests for `list_subscribers()` in tests/unit/test_zulip_api.py — mock Zulip subscribers endpoint, test response parsing

### Implementation for User Story 7

- [ ] T045 [US7] Implement `list_subscribers(client, channel, include_archived=False)` in lftools_uv/api/endpoints/zulip.py — resolve channel target, call Zulip subscribers API, cross-reference with users API to get full_name and email for each subscriber ID, return list of subscriber dicts
- [ ] T046 [US7] Implement `channel subscribers` CLI command in lftools_uv/typer_apps/zulip.py — add `subscribers` command with positional `[channel]`, `--channel-id`, `--include-archived`, `--json` flags, format table output

**Checkpoint**: User Story 7 is fully functional — `lftools-uv zulip channel subscribers` works independently

---

## Phase 10: User Story 8 — Update Channel Settings (Priority: P3)

**Goal**: Provide `lftools-uv zulip channel update` command to modify name, description, type, topic policy, `--allow-group`, and `--can-remove-subscribers-group`

**Independent Test**: Update a channel's name/description and verify changes via `channel list`. Test type transitions, lockout prevention, feature-level errors, and JSON output.

### Tests for User Story 8

- [ ] T047 [P] [US8] Write CLI tests for `channel update` in tests/unit/test_zulip_cli.py — test name update, description update, type change (all transitions), topic-policy set/clear, --allow-group with type change to private, lockout prevention, no-op success, --json output, feature-level errors, --can-remove-subscribers-group, at-least-one-setting validation
- [ ] T048 [P] [US8] Write API tests for `update_channel()` in tests/unit/test_zulip_api.py — mock Zulip PATCH endpoint, test all parameter combinations, group-setting-update wrapper format `{"new": value}`, lockout validation for type-to-private, feature-level checks

### Implementation for User Story 8

- [ ] T049 [US8] Implement `update_channel()` in lftools_uv/api/endpoints/zulip.py — validate at least one setting change, check feature levels (topic-policy, web-public, group-access, can-remove-subscribers-group), validate lockout prevention on type-to-private (check subscriber count, require --subscribe or --allow-group), resolve groups with `{"new": value}` wrapper format for PATCH, call PATCH `/streams/{stream_id}`, return MutationResult
- [ ] T050 [US8] Implement `channel update` CLI command in lftools_uv/typer_apps/zulip.py — add `update` command with positional `[channel]`, `--channel-id`, `--name`, `--description`, `--type`, `--topic-policy`, `--subscribe` (multi), `--by-email`/`--by-id`/`--by-name`, `--allow-group`, `--can-remove-subscribers-group`, `--include-archived`, `--json` flags

**Checkpoint**: User Story 8 is fully functional — `lftools-uv zulip channel update` works independently

---

## Phase 11: User Story 9 — Archive a Channel (Priority: P3)

**Goal**: Provide `lftools-uv zulip channel archive` command with `--yes` confirmation requirement

**Independent Test**: Archive a channel and verify it no longer appears in the active channel list. Test `--yes` requirement, no-op idempotency, and JSON output.

### Tests for User Story 9

- [ ] T051 [P] [US9] Write CLI tests for `channel archive` in tests/unit/test_zulip_cli.py — test successful archive with --yes, rejection without --yes, already-archived no-op with --include-archived, channel not found, --json output
- [ ] T052 [P] [US9] Write API tests for `archive_channel()` in tests/unit/test_zulip_api.py — mock Zulip archive endpoint, test success, already-archived

### Implementation for User Story 9

- [ ] T053 [US9] Implement `archive_channel(client, channel, include_archived=False)` in lftools_uv/api/endpoints/zulip.py — resolve channel target, call Zulip archive (deactivate) endpoint, handle already-archived as success, return MutationResult
- [ ] T054 [US9] Implement `channel archive` CLI command in lftools_uv/typer_apps/zulip.py — add `archive` command with positional `[channel]`, `--channel-id`, `--yes` (required), `--include-archived`, `--json` flags, reject without --yes

**Checkpoint**: User Story 9 is fully functional — `lftools-uv zulip channel archive` works independently

---

## Phase 12: User Story 10 — Unarchive a Channel (Priority: P3)

**Goal**: Provide `lftools-uv zulip channel unarchive` command with `--yes` confirmation and feature-level detection

**Independent Test**: Unarchive a previously archived channel and verify it reappears in active list. Test feature-level error, `--include-archived` suggestion, and JSON output.

### Tests for User Story 10

- [ ] T055 [P] [US10] Write CLI tests for `channel unarchive` in tests/unit/test_zulip_cli.py — test successful unarchive with --include-archived --yes, rejection without --yes, not-found suggestion to use --include-archived, already-active no-op, feature-level error, --json output
- [ ] T056 [P] [US10] Write API tests for `unarchive_channel()` in tests/unit/test_zulip_api.py — mock Zulip reactivate endpoint, test success, already-active no-op, feature-level check

### Implementation for User Story 10

- [ ] T057 [US10] Implement `unarchive_channel(client, channel, include_archived=False)` in lftools_uv/api/endpoints/zulip.py — check feature level for unarchive capability, resolve channel target (with include-archived awareness), call Zulip reactivate endpoint, handle already-active as success, return MutationResult
- [ ] T058 [US10] Implement `channel unarchive` CLI command in lftools_uv/typer_apps/zulip.py — add `unarchive` command with positional `[channel]`, `--channel-id`, `--yes` (required), `--include-archived`, `--json` flags, reject without --yes

**Checkpoint**: User Story 10 is fully functional — `lftools-uv zulip channel unarchive` works independently

---

## Phase 13: Topic Policy Convenience Command (Cross-Cutting — FR-021)

**Goal**: Provide `lftools-uv zulip channel topic-policy` convenience command for viewing/setting topic policy

- [ ] T059 [P] Write CLI tests for `channel topic-policy` in tests/unit/test_zulip_cli.py — test read mode (no --policy), write mode (--policy allow/deny/follow-default), invalid policy value rejection, feature-level error, --json output for both modes
- [ ] T060 [P] Write API tests for `get_topic_policy()` and `set_topic_policy()` in tests/unit/test_zulip_api.py — mock Zulip stream info endpoint for read, PATCH for write
- [ ] T061 Implement `get_topic_policy(client, channel)` and `set_topic_policy(client, channel, policy)` in lftools_uv/api/endpoints/zulip.py — check feature level, read or update topic policy field, return result
- [ ] T062 Implement `channel topic-policy` CLI command in lftools_uv/typer_apps/zulip.py — add `topic-policy` command with positional `[channel]`, `--channel-id`, `--policy` (optional), `--include-archived`, `--json` flags, display current policy in read mode, update in write mode

---

## Phase 14: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, integration validation, and quality assurance

- [ ] T063 [P] Add CLI help text and docstrings to all commands in lftools_uv/typer_apps/zulip.py — ensure `--help` output is clear and complete for all subcommands
- [ ] T064 [P] Add inline documentation and type annotations to all public functions in lftools_uv/api/endpoints/zulip.py
- [ ] T065 [P] Update REUSE.toml if needed — ensure new files have correct license annotations
- [ ] T066 Run full test suite and fix any failures — `tox` or `pytest` from repository root
- [ ] T067 Run pre-commit hooks (ruff lint + format) and fix any issues across all new files
- [ ] T068 Run quickstart.md validation — manually verify the documented workflows work end-to-end against a test Zulip server

---

## Dependencies & Execution Order

### Phase Dependencies (5 logical groups, 14 numbered phases)

- **Setup (Phase 1)**: No dependencies — can start immediately
- **Foundational (Phase 2)**: Depends on Setup — BLOCKS all stories
- **User Stories (Phases 3–12)**: Depend on Foundational
  - US1, US2, US3: Can proceed in parallel
  - US4: Depends on US2 + US3 (user/group resolution)
  - US5, US6, US7: Can proceed in parallel after Foundation
  - US8: Can proceed after Foundation
  - US9, US10: Can proceed in parallel after Foundation
- **Topic Policy (Phase 13)**: Depends on US8
- **Polish (Phase 14)**: Depends on all stories being complete

### User Story Dependencies

- **US1 (P1)** — List Channels: No story dependencies
- **US2 (P1)** — List Users: No story dependencies
- **US3 (P1)** — List Groups: No story dependencies
- **US4 (P1)** — Create Channel: Depends on US2 (user resolution) and US3 (group resolution) being testable
- **US5 (P2)** — Subscribe: No strict story dependency (uses foundational user resolution)
- **US6 (P2)** — Unsubscribe: No strict story dependency
- **US7 (P2)** — List Subscribers: No strict story dependency
- **US8 (P3)** — Update Channel: No strict story dependency (uses foundational helpers)
- **US9 (P3)** — Archive: No story dependencies
- **US10 (P3)** — Unarchive: No story dependencies

### Within Each User Story

- Tests MUST be written and FAIL before implementation
- API layer before CLI layer
- Core implementation before integration
- Story complete before moving to next priority

### Parallel Opportunities

- **Phase 2**: T009, T010, T011, T012, T013 can all run in parallel (different functions/files)
- **Phase 2 tests**: T015, T016, T017, T018 can all run in parallel
- **P1 stories**: US1, US2, US3 can run in parallel (independent listing commands)
- **P2 stories**: US5, US6, US7 can run in parallel (independent operations)
- **P3 stories**: US8, US9, US10 can run in parallel (independent mutations)
- **Within stories**: Test tasks marked [P] can run in parallel with each other

---

## Parallel Example: P1 Stories (US1 + US2 + US3)

```bash
# After Phase 2 completes, launch all P1 stories in parallel:

# Developer A: User Story 1 (List Channels)
Task: T019 — CLI tests for channel list
Task: T020 — API tests for list_channels
Task: T021 — Implement list_channels API
Task: T022 — Implement channel list CLI

# Developer B: User Story 2 (List Users)
Task: T023 — CLI tests for user list
Task: T024 — API tests for list_users
Task: T025 — Implement list_users API
Task: T026 — Implement user list CLI

# Developer C: User Story 3 (List Groups)
Task: T027 — CLI tests for group list
Task: T028 — API tests for list_groups
Task: T029 — Implement list_groups API
Task: T030 — Implement group list CLI
```

---

## Implementation Strategy

### MVP First (User Stories 1–3)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL — blocks all stories)
3. Complete Phases 3–5: US1 + US2 + US3 (all P1, can run in parallel)
4. **STOP and VALIDATE**: Test all three listing commands independently
5. Deploy/demo if ready — provides full channel/user/group discovery

### Incremental Delivery

1. Setup + Foundational → Foundation ready
2. Add US1 + US2 + US3 → Test independently → Deploy (MVP — discovery)
3. Add US4 → Test independently → Deploy (channel provisioning)
4. Add US5 + US6 + US7 → Test independently → Deploy (membership management)
5. Add US8 + US9 + US10 → Test independently → Deploy (full lifecycle)
6. Add Topic Policy + Polish → Final release

### Parallel Team Strategy

With multiple developers after Foundation completes:

1. Team completes Setup + Foundational together
2. **Sprint 1** (P1): US1 ∥ US2 ∥ US3
3. **Sprint 2** (P1 continued): US4 (depends on US2+US3)
4. **Sprint 3** (P2): US5 ∥ US6 ∥ US7
5. **Sprint 4** (P3): US8 ∥ US9 ∥ US10 + Topic Policy
6. **Sprint 5**: Polish

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story is independently completable and testable
- Verify tests fail before implementing (TDD)
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Feature level thresholds are hardcoded constants determined during implementation by consulting the Zulip changelog
- The `zulip` Python client provides `call_endpoint()` for all REST API access
- Group-setting values differ between POST (raw) and PATCH (`{"new": value}`) endpoints
