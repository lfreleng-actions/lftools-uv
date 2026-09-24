<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Implementation Plan: Zulip Show Commands

**Branch**: `003-zulip-show-commands` | **Date**: 2026-09-24 |
**Spec**: `specs/003-zulip-show-commands/spec.md`
**Input**: Feature specification from `/specs/003-zulip-show-commands/spec.md`

## Summary

Add read-only detail commands for Zulip channels, groups, users, and channel
folders. The implementation will extend the existing refactored Zulip API and
Typer packages with shared detail rendering, settable annotation metadata, and
resolution helpers. Each command displays all server-returned fields and marks
which fields are settable through current CLI flags, server-settable but not yet
exposed, or read-only. ID-to-name resolution is enabled by default and can be
skipped with `--no-resolve`.

## Technical Context

**Language/Version**: Python >=3.11, <3.15
**Primary Dependencies**: `zulip` (official client), `typer`, `tabulate`
**Storage**: N/A (stateless CLI; all data from Zulip API)
**Testing**: pytest with mocked Zulip client responses and Typer CliRunner
**Target Platform**: Linux (POSIX)
**Project Type**: CLI tool extending existing Zulip command groups
**Performance Goals**: Single-object show commands complete in under 5 seconds
for servers with up to 500 channels, 5,000 users, and 500 groups
**Constraints**: Read-only feature; extra lookup calls must be documented and
skippable with `--no-resolve`; no new dependencies
**Scale/Scope**: One Zulip server per invocation; four detail-view commands

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle            | Status | Notes                           |
| -------------------- | ------ | ------------------------------- |
| I: Quality & Testing | PASS   | Tests planned for every command |
| II: Atomic Commits   | PASS   | Spec artifacts and tasks split  |
| III: Licensing       | PASS   | EPL-1.0 headers in spec files   |
| IV: Pre-Commit       | PASS   | Hooks required before push      |
| V: Co-Author & DCO   | PASS   | Commit rules documented         |
| VI: CLI Consistency  | PASS   | Typer and existing Zulip UX     |
| VII: Security & Deps | PASS   | No new dependency or secrets    |

**Post-Design Re-Check**: ✅ All principles satisfied. The feature is read-only
and introduces no dependency or credential changes.

## Project Structure

### Documentation (this feature)

```text
specs/003-zulip-show-commands/
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
│           ├── channels.py          # Raw channel resolution/listing
│           ├── groups.py            # Raw group fetch and resolution
│           ├── users.py             # Raw user fetch and resolution
│           ├── folders.py           # Raw folder fetch and resolution
│           └── detail.py            # New shared show projections
├── typer_apps/
│   └── zulip/
│       ├── channel_read.py          # channel show
│       ├── groups.py                # group show
│       ├── users.py                 # user show
│       ├── folders.py               # folder show
│       └── detail.py                # New shared table rendering helpers

tests/
└── unit/
    ├── test_zulip_api.py            # Detail projection/resolution tests
    ├── test_zulip_cli.py            # CLI show command tests
    └── test_zulip_folders.py        # Folder show and folder resolver tests
```

**Structure Decision**: Reuse the refactored Zulip packages introduced after
specs 001 and 002. Add focused shared helpers instead of placing all show logic
in the existing list/mutation modules.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

## Phase 0: Research

Research confirms the list endpoints already used by the code return the raw
objects needed for show commands: raw stream dictionaries from `resolve_channel`,
raw user groups from `_fetch_groups`, raw users from `_fetch_users`, and raw
channel folders from `_fetch_channel_folders`. The existing normalized list
commands are intentionally lossy and should not be reused as the source of
truth for detail views.

See `research.md` for the Zulip field inventory, feature levels, and design
decisions.

## Phase 1: Design & Contracts

Design artifacts:

- `data-model.md`: Defines `ChannelDetail`, `GroupDetail`, `UserDetail`,
  `FolderDetail`, group-setting display values, and settable annotations.
- `contracts/cli-commands.md`: Defines command targeting, flags, table
  headers, JSON schemas, exit codes, and error messages.
- `quickstart.md`: Shows common auditing workflows.

## Phase 2: Implementation Planning

Tasks map directly to the new functional requirements:

| Phase | Focus | Requirements |
| ----- | ----- | ------------ |
| S1 | Shared detail renderer and annotations | FR-042, FR-057, FR-058 |
| S2 | Shared resolution helpers and `--no-resolve` | FR-055, FR-056 |
| S3 | `channel show` | FR-039 through FR-043 |
| S4 | `group show` | FR-044 through FR-047 |
| S5 | `user show` | FR-048 through FR-051 |
| S6 | `folder show` | FR-052 through FR-054 |
| S7 | Tests | FR-059 |
| S8 | Documentation and spec sync | FR-060 |

## Testing Approach

- Add API tests for raw-object detail projections and settable annotations.
- Add CLI tests for all four commands covering table output, `--json`,
  targeting variants, `--no-resolve`, missing targets, ambiguous names, and
  resolution failures.
- Add field-shape tests for group-setting values in integer and object forms.
- Add tests that feature-level-gated fields are shown only when present and are
  not invented on older mocked server responses.
- Run focused tests during implementation:
  `uv run pytest tests/unit/test_zulip_api.py tests/unit/test_zulip_cli.py tests/unit/test_zulip_folders.py`.
- Run `uv run ruff check .`, `uv run mypy lftools_uv`, and
  `SKIP=basedpyright pre-commit run --all-files` before implementation PRs.

## Out of Scope

- Adding write flags for `can_add_subscribers_group`,
  `can_administer_channel_group`, or `can_send_message_group`.
- Recursive subgroup expansion.
- Changing existing list, create, update, archive, or move command semantics.
- Stripping existing spec/task identifiers from current help text.
