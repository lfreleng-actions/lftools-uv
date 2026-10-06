<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Implementation Plan: Zulip Channel Permission Groups

**Branch**: `004-zulip-channel-permission-groups` | **Date**: 2026-10-06 |
**Spec**: `specs/004-zulip-channel-permission-groups/spec.md`
**Input**: Feature specification from
`/specs/004-zulip-channel-permission-groups/spec.md`

## Summary

Expose three Zulip channel permission-group settings as writable flags on
`channel create` and `channel update`: `can_add_subscribers_group`,
`can_administer_channel_group`, and `can_send_message_group`. The implementation
will reuse existing group resolution and group-setting value construction, add
feature-level gates for each field, and update feature 003's `channel show`
settability annotations from `not exposed` to the new setters. This PR is
specification only; implementation follows in three stacked PRs.

## Technical Context

**Language/Version**: Python >=3.11, <3.15
**Primary Dependencies**: `zulip` (official client), `typer`, `tabulate`
**Storage**: N/A (stateless CLI; all data from Zulip API)
**Testing**: pytest with mocked Zulip client responses and Typer CliRunner
**Target Platform**: Linux (POSIX)
**Project Type**: CLI tool extending existing Zulip command groups
**Performance Goals**: No additional list calls beyond the existing group
resolution path for supplied flags; feature-level checks use the existing
per-client cache
**Constraints**: Spec-only PR; no implementation code; exact Zulip API facts
must be cited; no `stream_post_policy` fallback; no rename/removal of
`--allow-group`
**Scale/Scope**: One Zulip server per invocation; three new channel permission
settings

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle            | Status | Notes                                  |
| -------------------- | ------ | -------------------------------------- |
| I: Quality & Testing | PASS   | Tests planned for each flag            |
| II: Atomic Commits   | PASS   | Spec artifacts and tasks split         |
| III: Licensing       | PASS   | EPL-1.0 headers in spec files          |
| IV: Pre-Commit       | PASS   | Hooks required before push             |
| V: Co-Author & DCO   | PASS   | Commit rules documented                |
| VI: CLI Consistency  | PASS   | Typer and existing Zulip UX reused     |
| VII: Security & Deps | PASS   | No new dependency or credential change |

**Post-Design Re-Check**: ✅ All principles satisfied. The design reuses
existing Zulip optional dependency handling, group resolution, and
feature-level checking.

## Project Structure

### Documentation (this feature)

```text
specs/004-zulip-channel-permission-groups/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── cli-commands.md  # CLI interface contract
└── tasks.md             # Phase 2 output
```

### Source Code (repository root)

```text
lftools_uv/
├── api/
│   └── endpoints/
│       └── zulip/
│           ├── features.py        # New feature-level constants
│           ├── groups.py          # Existing resolver/value builder reused
│           ├── channel_create.py  # Create request fields
│           ├── channel_update.py  # Update request fields
│           └── detail.py          # channel show annotation updates
├── typer_apps/
│   └── zulip/
│       ├── channel_create.py      # New create flags
│       └── channel_update.py      # New update flags

tests/
└── unit/
    ├── test_zulip_api.py          # API payload/gate/annotation tests
    └── test_zulip_cli.py          # CLI flag/help/error tests
```

**Structure Decision**: Reuse the refactored Zulip packages introduced by the
previous Zulip specs. No new top-level modules are needed; shared helpers should
live near the existing group-setting and feature-level code.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

## Phase 0: Research

Research confirms that the official Zulip docs expose all three fields on both
create (`POST /api/v1/users/me/subscriptions`) and update
(`PATCH /api/v1/streams/{stream_id}`), with the same semantic group-setting
value but different payload wrappers. It also confirms the feature levels:
FL 342 for `can_add_subscribers_group`, FL 325 for
`can_administer_channel_group`, and FL 333 for `can_send_message_group`.

See `research.md` for citations, value-shape details, and design decisions.

## Phase 1: Design & Contracts

Design artifacts:

- `data-model.md`: Defines `ChannelPermissionFlag`, group-setting value and
  update shapes, feature gates, and updated settable annotations.
- `contracts/cli-commands.md`: Defines command signatures, request payloads,
  JSON output, error messages, and exit codes.
- `quickstart.md`: Shows common workflows and verification with `channel show`.

## Phase 2: Implementation Planning

Implementation must be stacked as three PRs. The first PR carries the shared
foundation so later PRs only add their own flag-specific plumbing.

| Phase | Stacked PR | Focus | Requirements |
| ----- | ---------- | ----- | ------------ |
| P0 | PR 1 | Shared constants/helpers | FR-064 through FR-068 |
| P1 | PR 1 | `--can-add-subscribers-group` | FR-061, FR-073, FR-074 |
| P2 | PR 2 | `--can-administer-channel-group` | FR-062, FR-073, FR-074 |
| P3 | PR 3 | `--can-send-message-group` | FR-063, FR-069, FR-073, FR-074 |
| P4 | Each PR | Docs/help/tests for that flag | FR-072, FR-075 |

## Testing Approach

- Add API tests for create raw group-setting payloads and update
  `{"new": ...}` payloads for each field.
- Add API tests for feature-level gates below FL 342, FL 325, and FL 333.
- Add CLI tests verifying create options pass resolved `GroupSettingValue`
  values to the API layer, update options forward raw group specifications for
  API-layer resolution, and help includes `id:NUM` syntax.
- Add tests that group ambiguity and numeric-not-found hints are reused by each
  flag path.
- Add tests that `CHANNEL_ANNOTATIONS` reports each field as `via --flag` with
  the new setter once that flag's PR lands.
- Run focused tests during implementation:
  `uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py`.
- Run `uv run ruff check .`, `uv run mypy lftools_uv`, and
  `prek run --files <changed files>` before implementation PRs.

## Cross-Feature Dependency

Feature 003 (`specs/003-zulip-show-commands/`) intentionally annotated
`can_add_subscribers_group`, `can_administer_channel_group`, and
`can_send_message_group` as `not exposed` because no write flags existed at the
time. This feature changes that state. Each implementation PR must update the
annotation for its own field in `lftools_uv/api/endpoints/zulip/detail.py` and
its related tests so `channel show` remains an accurate source of truth.

## Out of Scope

- Implementation code in this spec-only PR.
- Renaming or removing `--allow-group`.
- Adding write flags for delete-message, move-message, resolve-topic, or
  create-topic permission fields.
- Adding a `none` clear/reset sentinel for these group settings.
- Falling back from `can_send_message_group` to legacy `stream_post_policy`.
- Stripping existing spec/task identifiers from unrelated help text.
