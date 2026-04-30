<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2026 The Linux Foundation
-->

# Research: Zulip Channel Management

## Decision 1: Zulip Python Client Library

**Decision**: Use the official `zulip` PyPI package as the Zulip API client.

**Rationale**: FR-013 mandates use of an official supported Zulip client
library.
The `zulip` package is the only official Python client maintained by the Zulip
team. It handles HTTP connection management, retries, and rate limiting
internally. The library provides `zulip.Client` for authentication and
`call_endpoint()` for accessing any REST API endpoint.

**Alternatives Considered**:

- Raw `requests` calls: Rejected — would require reimplementing authentication,
  rate limiting, and error handling already provided by the official client.
- `python-zulip-api` (meta-package): Same underlying library; `zulip` is the
  correct direct dependency name on PyPI.

## Decision 2: Zulip API Feature Levels for Runtime Detection

**Decision**: Feature levels are hardcoded constants in the CLI,
determined during implementation from the Zulip changelog. At runtime,
the CLI checks the server's reported feature level (via
`GET /api/v1/server_settings` → `zulip_feature_level`) against the
required threshold and errors if insufficient.

| Feature                        | Required Feature Level |
|--------------------------------|------------------------|
| Web-public streams / spectator | Hardcoded at impl      |
| Group-based access control     | Hardcoded at impl      |
| Topic policy                   | Hardcoded at impl      |
| Stream reactivation (unarchive)| Hardcoded at impl      |
| can_remove_subscribers_group   | Hardcoded at impl      |

**Rationale**: FR-019 requires runtime feature detection rather than a minimum
server version. The `server_settings` endpoint is unauthenticated and always
available. Caching the feature level per client session avoids repeated
API calls. Exact feature level thresholds are hardcoded constants
determined during implementation by consulting the Zulip changelog. The
spec defines BEHAVIOR (check server's reported level against the
threshold and return the canonical error: "This operation requires Zulip
feature level X (server has Y)") rather than specific numbers.

**Alternatives Considered**:

- Minimum server version enforcement: Rejected per spec — graceful degradation
  with clear error messages is required.
- Try-and-catch approach (attempt the call, handle 400): Rejected — less
  user-friendly and harder to produce the exact error message format required.

## Decision 3: Architecture — API Layer Separation

**Decision**: Create `lftools_uv/api/endpoints/zulip.py` as the reusable API
layer and `lftools_uv/typer_apps/zulip.py` as the CLI presentation layer.

**Rationale**: FR-009 mandates separation between API logic and CLI
presentation. This follows the existing project pattern where
`lftools_uv/api/endpoints/` contains API modules and
`lftools_uv/typer_apps/` contains Typer CLI apps. The API layer raises
domain exceptions; the CLI layer catches them and formats output.

**Alternatives Considered**:

- Single module: Rejected — violates FR-009 and project conventions.
- Separate package (e.g., `lftools_uv/zulip/`): Rejected — existing pattern
  uses `api/endpoints/` and `typer_apps/`.

## Decision 4: Configuration Resolution

**Decision**: Implement a `ZulipConfig` resolver that checks sources in order:

1. `--zuliprc PATH` flag
2. `./zuliprc` (current working directory)
3. `[zulip]` section in `lftools.ini`
4. `~/.zuliprc`

The resolver returns a path to a zuliprc-format file or synthesizes one from
lftools.ini fields (email, key, site) into a temporary in-memory config for
the `zulip.Client`.

**Rationale**: FR-011 and FR-012 define the exact precedence and compatibility
requirements. The `zulip.Client` accepts either a `config_file` path or
individual `email`/`api_key`/`site` parameters, making both resolution paths
straightforward.

**Alternatives Considered**:

- Environment variable support: Not specified in FR-011; out of scope for v1.
- Only zuliprc support (no lftools.ini): Rejected — FR-012 requires lftools.ini
  integration.

## Decision 5: CLI Command Structure

**Decision**: Register commands under the `zulip` subcommand group:

```text
lftools-uv zulip channel list
lftools-uv zulip channel create <name>
lftools-uv zulip channel update [channel]
lftools-uv zulip channel archive [channel]
lftools-uv zulip channel unarchive [channel]
lftools-uv zulip channel subscribe [channel] USER [USER...]
lftools-uv zulip channel unsubscribe [channel] USER [USER...]
lftools-uv zulip channel subscribers [channel]
lftools-uv zulip channel topic-policy [channel]
lftools-uv zulip user list
lftools-uv zulip group list
```

**Rationale**: Follows existing lftools-uv Typer app patterns where domain
commands are grouped under a top-level subcommand. The spec explicitly defines
these command paths. The `channel` sub-group keeps channel operations organized.

**Alternatives Considered**:

- Flat namespace (`lftools-uv zulip-channel-list`): Rejected — inconsistent
  with existing CLI patterns and harder to discover.
- Separate `stream` alias: Rejected — spec uses "channel" terminology
  consistently.

## Decision 6: Output Formatting

**Decision**: Use `tabulate` for human-readable table output (already a project
dependency) and `json.dumps` with `indent=2` for `--json` output.

**Rationale**: The project already depends on `tabulate` and uses it in other
commands. JSON output follows FR-008's schema requirements. Using `typer.echo()`
for stdout output and `typer.echo(..., err=True)` for errors follows Principle
VI.

**Alternatives Considered**:

- Rich tables: Rejected — adds a new dependency; `tabulate` is sufficient and
  already available.
- Custom formatting: Rejected — `tabulate` provides consistent formatting with
  minimal code.

## Decision 7: Error Handling Pattern

**Decision**: Define domain exceptions in `lftools_uv/api/exceptions.py` (or a
new `lftools_uv/api/endpoints/zulip_exceptions.py`):

- `ZulipConfigError` — configuration resolution failures
- `ZulipConnectionError` — network/connectivity issues
- `ZulipPermissionError` — insufficient permissions
- `ZulipNotFoundError` — channel/user/group not found
- `ZulipFeatureLevelError` — server lacks required feature level
- `ZulipAmbiguityError` — ambiguous name match (multiple users/groups)
- `ZulipValidationError` — client-side validation failures (e.g., private
  channel without subscribers)

The CLI layer catches these and formats appropriate error messages to stderr
with non-zero exit codes.

**Rationale**: FR-010 requires the CLI to catch API exceptions and produce
meaningful errors. Typed exceptions allow the CLI to format different error
types differently (e.g., feature level errors include the specific levels).

**Alternatives Considered**:

- Generic exception with error codes: Rejected — typed exceptions are more
  Pythonic and easier to handle in the CLI layer.
- Return-code pattern (no exceptions): Rejected — exceptions provide better
  separation between happy path and error handling.

## Decision 8: Testing Strategy

**Decision**: Use `pytest` with `responses` library (already in test
dependencies) to mock HTTP calls to the Zulip API. Structure tests as:

- `tests/unit/test_zulip_api.py` — API layer unit tests
- `tests/unit/test_zulip_cli.py` — CLI layer unit tests (invoke via Typer
  test client)
- `tests/unit/test_zulip_config.py` — Configuration resolution tests

**Rationale**: The project already uses pytest with responses for HTTP mocking.
The `zulip.Client` makes standard HTTP requests that can be intercepted by the
`responses` library. Typer provides `typer.testing.CliRunner` for CLI testing.

**Alternatives Considered**:

- Mocking `zulip.Client` directly: Could be used in addition but testing
  against actual HTTP calls provides better confidence in API integration.
- Integration tests against live Zulip: Useful for functional tests but not
  suitable for unit test suite (requires server access).

## Decision 9: Permission Group Flags and Inline Identification

**Decision**: Use two distinct flags for group-based channel permissions:

- `--allow-group` — defines who is allowed to join the channel. Maps to
  Zulip API field `can_access_group`. Valid on ALL channel types (server
  enforces on private; accepts but does not enforce on public/web-public).
- `--can-remove-subscribers-group` — defines who can remove subscribers.
  Maps to Zulip API field `can_remove_subscribers_group`. Valid on ALL
  channel types. Requires feature-level detection per FR-019.

Both flags accept a comma-separated, quoted string value with inline
group identification:

- Default interpretation: group name (case-insensitive)
- `id:NUM` prefix: force ID lookup

**API Translation (Group-Setting Values)**: After resolving group
names/IDs to numeric IDs, the CLI translates to the Zulip API
"group-setting value" format:

- Single group → simple integer (e.g., `42`)
- Multiple groups → complex form:
  `{"direct_members": [], "direct_subgroups": [id1, id2, ...]}`

**Create vs Update Format Difference**: The Zulip API uses different
payload shapes for permission fields depending on the endpoint. Create
(POST) accepts a raw group-setting value. Update (PATCH) requires a
group-setting-update wrapper: `{"new": <group-setting-value>}` with
`old` omitted (CLI syncs desired state, not incremental edits). The
CLI wraps automatically — user syntax is identical for both commands.

This translation is transparent to the user — they always use the
comma-separated name/ID syntax regardless of how many groups are
specified.

Examples:

- `--allow-group 'foo, bar, id:123'`
- `--can-remove-subscribers-group 'baz, admin'`

This eliminates `--group-name`/`--group-id` as separate flags in
permission flag contexts. Those flags remain only for
`lftools-uv zulip group list` filtering.

**Rationale**: The spec clarifies that `--allow-group` has ONE consistent
meaning ("who can join") on ALL channel types, not two different meanings
depending on channel type. A separate `--can-remove-subscribers-group`
flag avoids overloading `--allow-group` with administrative permissions.
The comma-separated inline syntax is more ergonomic than requiring
separate `--group-name`/`--group-id` modifier flags for each permission
flag, especially when both `--allow-group` and
`--can-remove-subscribers-group` appear in the same command.

**Alternatives Considered**:

- Single `--allow-group` with multiple meanings per channel type: Rejected
  — confusing semantics, violates principle of least surprise.
- Separate `--group-name`/`--group-id` modifier flags for permission
  contexts: Rejected — awkward when two permission flags coexist in one
  command; which modifier applies to which flag is ambiguous.
- Repeated `--allow-group` flags instead of comma-separated: Rejected —
  spec mandates comma-separated inline syntax with prefix disambiguation.
