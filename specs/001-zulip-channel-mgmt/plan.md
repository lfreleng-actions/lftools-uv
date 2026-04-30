<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Implementation Plan: Zulip Channel Management

**Branch**: `001-zulip-channel-mgmt` | **Date**: 2026-04-29 |
**Spec**: `specs/001-zulip-channel-mgmt/spec.md`
**Input**: Feature specification from `/specs/001-zulip-channel-mgmt/spec.md`

## Summary

Add Zulip channel (stream) management commands to lftools-uv, providing CLI
commands for listing, creating, updating, archiving/unarchiving channels, and
managing user subscriptions on a single Zulip server. The implementation uses
the official `zulip` Python client library with a separated API layer
(`lftools_uv/api/endpoints/zulip.py`) and CLI presentation layer
(`lftools_uv/typer_apps/zulip.py`), following existing project conventions.
Runtime feature-level detection ensures graceful degradation on older Zulip
servers. Group-based permissions use two distinct flags: `--allow-group`
(who can join — maps to `can_access_group`) and
`--can-remove-subscribers-group` (who can remove subscribers — maps to
`can_remove_subscribers_group`), both accepting comma-separated inline
group identification with `id:` prefix disambiguation.

## Technical Context

**Language/Version**: Python >=3.11, <3.15
**Primary Dependencies**: `zulip` (official client), `typer` (CLI), `tabulate`
(output formatting)
**Storage**: N/A (stateless CLI — all data from Zulip API)
**Testing**: pytest with `responses` for HTTP mocking, `typer.testing.CliRunner`
for CLI tests
**Target Platform**: Linux (POSIX)
**Project Type**: CLI tool (extending existing multi-command CLI)
**Performance Goals**: List operations <5s for 500 channels or 5,000 users
(SC-001, SC-008)
**Constraints**: Bulk subscribe/unsubscribe up to 50 users per invocation
(SC-003)
**Scale/Scope**: Single Zulip server per invocation; servers up to 500
channels, 5,000 users

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle            | Status | Notes                       |
| -------------------- | ------ | --------------------------- |
| I: Quality & Testing | PASS   | pytest; type hints; ruff    |
| II: Atomic Commits   | PASS   | Stories → atomic commits    |
| III: Licensing       | PASS   | EPL-1.0 per REUSE.toml      |
| IV: Pre-Commit       | PASS   | Hooks pass before commit    |
| V: Co-Author & DCO   | PASS   | Co-authored-by + `-s`       |
| VI: CLI Consistency  | PASS   | Typer; typer_apps/ patterns |
| VII: Security & Deps | PASS   | Pinned zulip; config creds  |

**Post-Design Re-Check**: ✅ All principles satisfied. No violations requiring
justification.

## Project Structure

### Documentation (this feature)

```text
specs/001-zulip-channel-mgmt/
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
│       └── zulip.py           # Reusable API layer (FR-009)
├── typer_apps/
│   └── zulip.py               # CLI presentation layer (Typer app)
├── cli_app.py                 # Updated to register zulip app

tests/
└── unit/
    ├── test_zulip_api.py      # API layer unit tests
    ├── test_zulip_cli.py      # CLI layer unit tests
    └── test_zulip_config.py   # Config resolution unit tests
```

**Structure Decision**: Follows existing project pattern — API logic in
`lftools_uv/api/endpoints/`, CLI in `lftools_uv/typer_apps/`, tests in
`tests/unit/`. No new top-level directories needed.

## Complexity Tracking

> No constitution violations. No complexity justifications needed.
