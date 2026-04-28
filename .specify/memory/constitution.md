<!--
# Sync Impact Report
**Version Change**: 1.0.0 → 1.1.0
**Change Type**: MINOR - New section added (Prohibited Post-Failure Git Operations)

## Modified Principles
- UPDATED: Principle IV (Pre-Commit Integrity) - Added explicit
  `git reset` prohibition after commit failures

## Added Sections
- Development Standards > Prohibited Post-Failure Git Operations
  (NON-NEGOTIABLE)

## Removed Sections
- None

## Templates Review Status
- ✅ `.specify/templates/plan-template.md` - reviewed, no conflicts
- ✅ `.specify/templates/spec-template.md` - reviewed, no conflicts
- ✅ `.specify/templates/tasks-template.md` - reviewed, no conflicts
- ✅ `.specify/templates/constitution-template.md` - reviewed, this
      file replaces placeholder content
- ✅ `.specify/templates/checklist-template.md` - reviewed, no conflicts
- ✅ `.specify/templates/commands/*.md` - not present, no updates needed

## Follow-up TODOs
- None
-->

# LF Tools UV Constitution

## Core Principles

### Principle I: Code Quality & Testing Standards

**Rule**: All code changes MUST meet the following quality standards:

- **Test Coverage**: All new or changed behavior MUST have corresponding
  tests. Tests are run via `uv run pytest tests/` and coverage is
  configured in `pyproject.toml`.
- **Type Safety**: All Python code MUST include type hints and pass both
  mypy and basedpyright validation.
- **Code Style**: All code MUST conform to project linting standards
  (ruff, yamllint, shellcheck, markdownlint, codespell, write-good).
  Enforcement is split between pre-commit hooks and CI workflows;
  see `.pre-commit-config.yaml` and `.github/workflows/` for details.
- **Testability**: Code MUST be designed for testability — avoid tight
  coupling, support dependency injection where appropriate.
- **Python Version**: Code MUST support Python >=3.11 and <3.15 as
  declared in `pyproject.toml`.

**Rationale**: lftools-uv is a collection of CI/CD and release
engineering utilities used across Linux Foundation projects. Defects in
these tools can disrupt CI pipelines, compromise artifact signing, or
cause incorrect deployments across multiple downstream projects. High
quality standards are essential for reliability and trust.

### Principle II: Atomic Commit Discipline (NON-NEGOTIABLE)

**Rule**: All code changes MUST be delivered in small atomic commits
where each commit represents ONE logical change only.

- Each commit MUST pass all relevant lint, type, and test checks.
- Each commit MUST represent a single logical change (one feature, one
  fix, one refactor).
- Each commit MUST have a clear conventional commit message following
  the project's gitlint configuration (types: Fix, Feat, Chore, Docs,
  Style, Refactor, Perf, Test, Revert, CI, Build).
- Large features MUST be broken into multiple atomic commits.
- Mixing unrelated changes in a single commit is PROHIBITED.

**Rationale**: Atomic commits enable:

- Clean git history for debugging and auditing
- Easy reversion of specific changes without affecting unrelated code
- Clear code review process
- Bisect-friendly debugging when issues arise

### Principle III: Licensing & Attribution Standards (NON-NEGOTIABLE)

**Rule**: Each new or modified source file MUST include correct SPDX
license and copyright headers as defined by `REUSE.toml`.

**Header Format** (varies by file — consult `REUSE.toml` for
file-specific rules):

```text
# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation
```

Or for block comment languages:

```text
<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->
```

**Note**: The project is dual-licensed (`EPL-1.0 OR Apache-2.0` per
`pyproject.toml`). Individual files may carry different SPDX identifiers
as declared in `REUSE.toml` annotations (e.g., `.specify/` files use
MIT). Always check `REUSE.toml` before adding headers.

**Enforcement**: The reuse-tool pre-commit hook validates compliance.
Files without proper headers will be rejected.

**Rationale**: The project uses the REUSE specification for license
compliance. Proper attribution protects contributors and users, ensures
clear licensing terms, and maintains compliance with open source best
practices. Check `REUSE.toml` for the authoritative file-to-license
mapping.

### Principle IV: Pre-Commit Integrity (NON-NEGOTIABLE)

**Rule**: All pre-commit hooks MUST pass locally prior to any push.
Bypassing hooks is PROHIBITED.

**Failure Recovery Protocol**:

- If pre-commit hooks fail, the commit MUST be redone from scratch.
- Do NOT use `git reset` after a failed commit — this can discard
  staged changes and leave the working tree in an inconsistent state.
- Do NOT amend failing commits — this can mask the true state of
  changes.
- Redo the commit as if it was never made, fixing the issues first.

**Pre-Commit Requirements**:
All commits must pass the following validations (per
`.pre-commit-config.yaml`):

- File integrity checks (no large files, valid AST, proper line endings)
- Conventional commit message format (via gitlint)
- Code formatting and linting (ruff, ruff-format)
- YAML validation (yamllint)
- Type checking (mypy, basedpyright)
- Shell script analysis (shellcheck)
- Markdown linting (markdownlint)
- Spell checking (codespell)
- Prose linting (write-good)
- License compliance (reuse-tool)
- GitHub Actions validation (actionlint, check-github-actions,
  check-github-workflows, gha-workflow-linter)
- Test suite execution (pytest)

**Rationale**: Pre-commit hooks are the first line of defense against
defects, security issues, licensing violations, and technical debt.
Bypassing them creates risk for the entire codebase and can introduce
issues that affect CI/CD pipelines across multiple Linux Foundation
projects that depend on lftools-uv.

### Principle V: Agent Co-Authorship & DCO Requirements (NON-NEGOTIABLE)

**Rule**: All commits authored by AI agents MUST include proper
attribution and sign-off.

**Required Commit Trailers**:
Every agent-authored commit MUST include:

1. **Co-authored-by line**: Identifying the AI agent

   ```text
   Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>
   Co-authored-by: Claude <claude@anthropic.com>
   ```

   (Use appropriate agent name and email address)

2. **DCO Sign-off line**: Added via `git commit -s`

   ```text
   Signed-off-by: Human Author <human@email>
   ```

**Execution**: Use `git commit -s` to automatically add DCO sign-off.
The Co-authored-by trailer goes in the commit message body;
`git commit -s` appends Signed-off-by last.

**Rationale**: Transparency in authorship is critical for:

- Legal compliance (Developer Certificate of Origin)
- Audit trail for code provenance
- Understanding AI contribution patterns
- Maintaining trust in the development process

### Principle VI: CLI Interface Consistency

**Rule**: User-facing CLI commands MUST maintain consistency with
existing lftools-uv conventions and patterns.

- CLI commands MUST use Typer as the CLI framework (per project
  convention).
- Legacy Click-based output format MUST remain available via
  `LEGACY_CLI=1` environment variable for backward compatibility.
- Command output MUST support both human-readable and machine-parseable
  formats where applicable.
- Error messages MUST be clear, actionable, and directed to stderr.
- New subcommands MUST follow the existing naming conventions in
  `lftools_uv/cli/` and `lftools_uv/cli_app.py`.
- Shell scripts in `shell/` MUST pass shellcheck validation.

**Rationale**: lftools-uv is used in automated CI/CD pipelines across
many Linux Foundation projects. Inconsistent CLI behavior or breaking
changes to output formats can silently break downstream pipelines.
Backward compatibility and predictable interfaces are essential.

### Principle VII: Security & Dependency Hygiene

**Rule**: Code changes MUST maintain security standards appropriate for
CI/CD tooling used across critical open source infrastructure.

- **Dependency Pinning**: All dependencies MUST be pinned with version
  constraints in `pyproject.toml`. Transitive security constraints are
  managed via `[tool.uv] constraint-dependencies`.
- **Vulnerability Response**: Known CVEs in dependencies MUST be
  addressed before the next release via version bumps or constraints.
- **XML/Input Handling**: Use `defusedxml` for all XML parsing. Never
  use standard library XML parsers directly.
- **Credential Handling**: NEVER hardcode credentials. Use configuration
  files (`~/.config/lftools/`) or environment variables.
- **Security Scanning**: The project uses CodeQL and OpenSSF Scorecard
  for security analysis. Changes MUST NOT introduce new security
  findings.

**Rationale**: lftools-uv handles artifact signing, deployment
credentials, Jenkins API access, OpenStack cloud operations, and Nexus
repository management. A security compromise in this tool could cascade
to every Linux Foundation project that uses it for CI/CD operations.

## Development Standards

### Git Workflow Requirements

- **Branch Protection**: Direct commits to `main`, `dev`, `master`,
  `rc`, and `production` are PROHIBITED (enforced via pre-commit hook).
- **Conventional Commits**: REQUIRED for all commits (enforced via
  gitlint).
- **Signed Commits**: DCO sign-off REQUIRED via `git commit -s`.
- **Pull Requests**: All changes MUST go through PR review before
  merging to main.

### Testing Requirements

- **Coverage**: Code coverage is configured via `pyproject.toml`
  (`[tool.pytest.ini_options]` and `[tool.coverage.*]`).
- **Test Types**: Unit tests for all business logic; functional tests
  available via `scripts/run_functional_tests.sh` for integration
  validation.
- **Test Execution**: Tests MUST pass before commit (verified via
  pre-commit pytest hook and manually via `uv run pytest tests/`).
- **Make Targets**: Use `make test` for quick test runs, `make check`
  for lint + test combined.

### Code Review Standards

- Reviewers MUST verify constitutional compliance.
- Reviewers MUST check for atomic commit structure.
- Reviewers MUST verify pre-commit hooks passed.
- Reviewers MUST verify proper licensing headers.
- Reviewers MUST check for agent co-authorship when applicable.

### Prohibited Post-Failure Git Operations (NON-NEGOTIABLE)

**Rule**: After a failed `git commit` (e.g., pre-commit hook failure),
AI agents MUST NOT use `git reset` to recover.

The following operations are PROHIBITED after a commit failure:

- `git reset` (all forms: `--soft`, `--mixed`, `--hard`) — can discard
  staged changes and leave the working tree in an inconsistent state.
- `git commit --amend` — rewrites history and masks the true state
  of changes.

**Recovery procedure**: Fix the issues identified by the hooks, stage
the fixes with `git add`, and create a new commit attempt.

**Rationale**: After a pre-commit failure, the working tree may contain
auto-fixes from hooks (e.g., ruff format, markdownlint). Using
`git reset` can silently discard these fixes. A clean re-stage and
fresh commit attempt is always the safe recovery path.

## Governance

### Constitutional Authority

This constitution supersedes all other development practices and
guidelines. When conflicts arise, constitutional principles take
precedence.

### Amendment Process

**Version Format**: MAJOR.MINOR.PATCH

- **MAJOR**: Backward-incompatible changes, principle removal or
  redefinition, or fundamental governance changes.
- **MINOR**: New principles added, sections expanded, new mandatory
  requirements.
- **PATCH**: Clarifications, wording improvements, typo fixes without
  semantic changes.

**Amendment Requirements**:

1. Proposed changes MUST be documented with rationale.
2. Impact assessment MUST identify affected templates and workflows.
3. All `.specify/templates/*.md` files MUST be updated for consistency.
4. Version increment MUST follow semantic versioning rules above.
5. Amendment history MUST be preserved in Sync Impact Report comments.

### Compliance Review

**Mandatory Review Points**:

- Every PR merge (verify constitutional compliance in review)
- Every sprint/milestone retrospective (check for systematic
  violations)
- Every quarter (constitution effectiveness review)

**Violation Response**:

- **Pre-commit violations**: Commit rejected, redo required
- **PR violations**: PR rejected until corrected
- **Post-merge violations**: Immediate corrective commit required

### Development Guidance Integration

For runtime agent guidance, refer to
`.specify/templates/agent-file-template.md` and related command
templates in `.specify/templates/commands/*.md` (when present).

All development tooling and agent instructions MUST align with
constitutional principles.

---

**Version**: 1.1.0 | **Ratified**: 2026-04-28 | **Last Amended**: 2026-04-28
