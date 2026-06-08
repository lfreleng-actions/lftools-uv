<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Implementation Plan: Zulip Channel Folders

**Branch**: `002-zulip-channel-folders` | **Date**: 2026-06-04 |
**Spec**: `specs/002-zulip-channel-folders/spec.md`
**Input**: Feature specification from `/specs/002-zulip-channel-folders/spec.md`

## Summary

Add Zulip channel folder management commands to lftools-uv, providing CLI
commands for listing, creating, updating, archiving, and unarchiving channel
folders, plus folder assignment on existing channel create/update workflows.
The implementation extends the existing Zulip API layer
(`lftools_uv/api/endpoints/zulip.py`) and Typer presentation layer
(`lftools_uv/typer_apps/zulip.py`). Runtime feature-level detection gates all
folder behavior at Zulip feature level 389, while folder ordering is treated as
optional until feature level 414. The CLI uses one `--folder` assignment flag
accepting names, `id:N`, or `none`; `--folder-id 0` is accepted only for the
explicit clear behavior locked by the spec.

## Technical Context

**Language/Version**: Python >=3.11, <3.15
**Primary Dependencies**: `zulip` (official client), `typer` (CLI), `tabulate`
(output formatting)
**Storage**: N/A (stateless CLI — all data from Zulip API)
**Testing**: pytest with `responses` for HTTP mocking, `typer.testing.CliRunner`
for CLI tests
**Target Platform**: Linux (POSIX)
**Project Type**: CLI tool (extending existing multi-command CLI)
**Performance Goals**: List operations <5s for 100 folders (SC-009)
**Constraints**: Feature-level gate at FL 389; folder `order` optional before
FL 414; no hard-delete endpoint
**Scale/Scope**: Single Zulip server per invocation; channel folder lifecycle
and channel assignment only

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle            | Status | Notes                         |
| -------------------- | ------ | ----------------------------- |
| I: Quality & Testing | PASS   | pytest; type hints; ruff      |
| II: Atomic Commits   | PASS   | Tasks are commit-sized        |
| III: Licensing       | PASS   | EPL-1.0 per REUSE.toml        |
| IV: Pre-Commit       | PASS   | Hooks pass before commit      |
| V: Co-Author & DCO   | PASS   | Co-authored-by + `-s`         |
| VI: CLI Consistency  | PASS   | Typer; existing Zulip patterns|
| VII: Security & Deps | PASS   | No new dependency or secrets  |

**Post-Design Re-Check**: ✅ All principles satisfied. No violations requiring
justification.

## Project Structure

### Documentation (this feature)

```text
specs/002-zulip-channel-folders/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── cli-commands.md  # CLI interface contract
└── tasks.md             # Phase 2 output (/speckit.tasks command)
```

### Source Code (repository root)

```text
lftools_uv/
├── api/
│   └── endpoints/
│       └── zulip.py           # Folder API helpers and resolution
├── typer_apps/
│   └── zulip.py               # `zulip folder` commands and flags

tests/
└── unit/
    ├── test_zulip_api.py      # Existing API layer tests
    ├── test_zulip_cli.py      # Existing CLI layer tests
    └── test_zulip_folders.py  # Folder-specific unit/CLI tests
```

**Structure Decision**: Reuse the existing Zulip modules from feature 001. No
new top-level directories are needed. Folder-specific tests may live in a new
`tests/unit/test_zulip_folders.py` file to keep the larger Zulip test files
manageable.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.

## Phase 0: Research

Research confirms Zulip channel folders are exposed by the
`/api/v1/channel_folders` resource family, new in Zulip 11.0 at feature level
389. Folder order is available starting at feature level 414. There is no
hard-delete endpoint; archive and unarchive use the update endpoint. Channel
assignment uses existing stream create/update endpoints with `folder_id`.

See `research.md` for details and API references.

## Phase 1: Design & Contracts

Design artifacts:

- `data-model.md`: Defines `ChannelFolder` and the `Channel.folder_id`
  relationship.
- `contracts/cli-commands.md`: Defines `zulip folder` commands and updated
  channel create/update flags.
- `quickstart.md`: Documents common folder workflows.

## Phase 2: Implementation Planning

Tasks map FRs to implementation phases:

| Phase | Focus | Requirements |
| ----- | ----- | ------------ |
| F1 | API helpers | FR-024 through FR-027 |
| F2 | Feature gates and validation | FR-030, FR-031, FR-033, FR-034 |
| F3 | `zulip folder` Typer commands | FR-023 through FR-027 |
| F4 | Folder resolution helper | FR-032 |
| F5 | Channel `--folder` integration | FR-028, FR-029 |
| F6 | Tests | FR-023 through FR-036 |
| F7 | Spec sync and help text | FR-037 |

## Testing Approach

- Add mock-based API tests for list/create/update/archive/unarchive helpers in
  `tests/unit/test_zulip_folders.py` or `tests/unit/test_zulip_api.py`.
- Add CLI tests with `typer.testing.CliRunner` for folder list table/JSON
  output, mutation output, feature-level errors, validation failures, and
  permission error propagation.
- Add channel create/update tests covering `--folder` by name, `id:N`, numeric
  not-found hint, `none`, and `--folder-id 0` clearing.
- Add feature-level tests for FL 388 rejection, FL 389 success without order,
  and FL 414 order display.
- Run `uv run pytest tests/`, `uv run ruff check .`, `uv run mypy lftools_uv`,
  and `uv run basedpyright` before implementation PRs. For this spec-only PR,
  run pre-commit with the repository's accepted `SKIP=basedpyright` setting.

## Out of Scope

- Implementation code in this PR.
- Per-user folder ordering changes; no API exists as of FL 389.
- Bulk folder reorder.
- Hard-delete of channel folders; Zulip exposes archive only.
- Client-side role pre-flight checks for admin-only folder mutations.
