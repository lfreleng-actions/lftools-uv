#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

###############################################################################
# LFTOOLS-UV FUNCTIONAL / INTEGRATION TEST HARNESS (Scaffold)
#
# This script provides a starting point for exercising lftools-uv CLI
# commands against real infrastructure (Jenkins, Nexus, GitHub, etc.).
#
# Current focus:
#   Category 1 (Safe / Read-only) commands only.
#   Categories 2 & 3 are stubs / placeholders (commented out).
#
# Categories (as agreed):
#   1. Harmless (read/query only) - enabled by default
#   2. Reversible (create/change with reliable undo) - listed, disabled
#   3. Destructive / Hard-to-reverse - listed, disabled
#
# HOW TO USE (local workstation):
#   chmod +x scripts/run_functional_tests.sh
#   ./scripts/run_functional_tests.sh
#   ./scripts/run_functional_tests.sh debug    # Show command output to terminal
#
# OPTIONAL FILTERS:
#   TEST_CATEGORY=1                # default; comma-separated ok (e.g. 1,2)
#   TEST_FILTER=jenkins            # substring match on test ID or description
#   STOP_ON_FAILURE=1              # stop after first failure
#   DRY_RUN=1                      # show what would run
#   VERBOSE=1                      # more logging
#   DEBUG=1                        # show command output to terminal (also logs to file)
#   OUTPUT_FORMAT=plain|json       # result summary format
#
# EXIT CODES:
#   0 = Success (no failures; skips allowed)
#   1 = One or more test failures
#   2 = Harness / configuration error (e.g. lftools-uv not found)
#
# EXAMPLES:
#   TEST_FILTER=nexus ./scripts/run_functional_tests.sh
#   TEST_CATEGORY=1,2 DRY_RUN=1 ./scripts/run_functional_tests.sh
#   ./scripts/run_functional_tests.sh debug         # Show command output to terminal
#   DEBUG=1 ./scripts/run_functional_tests.sh       # Enable debug mode via env var
#   TEST_FILTER=openstack DEBUG=1 ./scripts/run_functional_tests.sh  # Debug specific tests
#
# ENVIRONMENT / CREDENTIAL NOTES:
#   Jenkins: JENKINS_URL (defaults to jenkins.onap.org), LFTOOLS_USERNAME, LFTOOLS_PASSWORD (or token via config)
#   Nexus2: NEXUS2_FQDN (defaults to nexus.onap.org, hostname only, no scheme)
#   Nexus3: NEXUS3_FQDN (defaults to nexus3.onap.org)
#   OpenStack: OS_CLOUD (defaults to ecompci)
#   GitHub: GITHUB_ORG (defaults to onap), GITHUB_TOKEN (or config in lftools-uv settings)
#
# DEFAULT VALUES:
#   If environment variables are not set, the script uses ONAP/ECOMPCI project defaults:
#   - JENKINS_URL=https://jenkins.onap.org
#   - NEXUS2_FQDN=nexus.onap.org
#   - NEXUS3_FQDN=nexus3.onap.org
#   - OS_CLOUD=ecompci
#   - GITHUB_ORG=onap
#
# STRATEGY:
#   - We model each test as a record:
#       ID:::CATEGORY:::DESCRIPTION:::COMMAND:::REQ_ENV (comma list or '-')
#   - Category 1 tests are executable immediately if required env vars exist.
#   - Category 2/3: commentary + disabled command lines provided for future work.
#
# EXTENDING:
#   - Add new tests to the TEST_DEFINITIONS block.
#   - Keep ordering logical by subsystem.
#   - For category 2 & 3 add them commented and mark rationale.
#
###############################################################################

set -o pipefail

# Check for 'debug' argument to enable DEBUG mode
if [[ "$1" == "debug" ]]; then
    DEBUG=1
fi

# SCRIPT_NAME="$(basename "$0")"  # Unused, keeping for potential future use
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
START_TIME_EPOCH=$(date +%s)

# Default configuration variables (can be overridden via env)
TEST_CATEGORY="${TEST_CATEGORY:-1}"
TEST_FILTER="${TEST_FILTER:-}"
STOP_ON_FAILURE="${STOP_ON_FAILURE:-0}"
DRY_RUN="${DRY_RUN:-0}"
VERBOSE="${VERBOSE:-0}"
DEBUG="${DEBUG:-0}"
OUTPUT_FORMAT="${OUTPUT_FORMAT:-plain}"
LOG_DIR="${LOG_DIR:-${REPO_ROOT}/.functional_logs}"
mkdir -p "${LOG_DIR}"

# Color support (disable if not TTY)
if [[ -t 1 ]]; then
  COLOR_RED='\033[0;31m'
  COLOR_GREEN='\033[0;32m'
  COLOR_YELLOW='\033[0;33m'
  COLOR_BLUE='\033[0;34m'
  COLOR_RESET='\033[0m'
else
  COLOR_RED='' COLOR_GREEN='' COLOR_YELLOW='' COLOR_BLUE='' COLOR_RESET=''
fi

log() {
  local level="$1"; shift
  local msg="$*"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  if [[ "$OUTPUT_FORMAT" == "json" ]]; then
    echo -e "${ts} [${level}] ${msg}" >&2
  else
    echo -e "${ts} [${level}] ${msg}"
  fi
}

vlog() {
  [[ "${VERBOSE}" == "1" ]] && log "DEBUG" "$*"
}

warn() { log "${COLOR_YELLOW}WARN${COLOR_RESET}" "$*"; }
err()  { log "${COLOR_RED}ERROR${COLOR_RESET}" "$*"; }
info() { log "${COLOR_BLUE}INFO${COLOR_RESET}" "$*"; }
success() { log "${COLOR_GREEN}OK${COLOR_RESET}" "$*"; }

###############################################################################
# Load lftools-uv configuration and set defaults
###############################################################################
# Set up lftools-uv configuration directory
LFTOOLS_CONFIG_DIR="${HOME}/.config/lftools"

# Configure OpenStack clouds.yaml location
OPENSTACK_CONFIG="${LFTOOLS_CONFIG_DIR}/clouds.yaml"
if [[ -f "${OPENSTACK_CONFIG}" ]]; then
    export OS_CLIENT_CONFIG_FILE="${OPENSTACK_CONFIG}"
    vlog "Using OpenStack config: ${OPENSTACK_CONFIG}"
else
    vlog "No OpenStack config found at ${OPENSTACK_CONFIG}"
fi

# Configure Jenkins configuration location
JENKINS_CONFIG="${LFTOOLS_CONFIG_DIR}/jenkins_job.ini"
if [[ -f "${JENKINS_CONFIG}" ]]; then
    export JENKINS_JOBS_INI="${JENKINS_CONFIG}"
    vlog "Using Jenkins config: ${JENKINS_CONFIG}"
else
    vlog "No Jenkins config found at ${JENKINS_CONFIG}"
fi

###############################################################################
# Set ONAP/ECOMPCI project defaults for testing (if not already set)
###############################################################################
# Set default Jenkins URL if not provided
if [[ -z "${JENKINS_URL:-}" ]]; then
    export JENKINS_URL="https://jenkins.onap.org"
    vlog "Using default Jenkins URL: ${JENKINS_URL}"
fi

# Set default Nexus2 FQDN if not provided
if [[ -z "${NEXUS2_FQDN:-}" ]]; then
    export NEXUS2_FQDN="nexus.onap.org"
    vlog "Using default Nexus2 FQDN: ${NEXUS2_FQDN}"
fi

# Set default Nexus3 FQDN if not provided
if [[ -z "${NEXUS3_FQDN:-}" ]]; then
    export NEXUS3_FQDN="nexus3.onap.org"
    vlog "Using default Nexus3 FQDN: ${NEXUS3_FQDN}"
fi

# Set default OpenStack cloud if not provided
if [[ -z "${OS_CLOUD:-}" ]]; then
    export OS_CLOUD="ecompci"
    vlog "Using default OpenStack cloud: ${OS_CLOUD}"
fi

# Set default GitHub organization if not provided
if [[ -z "${GITHUB_ORG:-}" ]]; then
    export GITHUB_ORG="onap"
    vlog "Using default GitHub organization: ${GITHUB_ORG}"
fi

# Source additional test credentials if available (for backwards compatibility)
TEST_CREDENTIALS_FILE="${HOME}/.config/lftools/test-setup.txt"

# Auto-setup: copy sample test-setup.txt if it doesn't exist
if [[ ! -f "${TEST_CREDENTIALS_FILE}" ]]; then
    # Get the directory where this script is located
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    SAMPLE_FILE="${SCRIPT_DIR}/test-setup.txt"

    if [[ -f "${SAMPLE_FILE}" ]]; then
        # Create the config directory if it doesn't exist
        CONFIG_DIR="$(dirname "${TEST_CREDENTIALS_FILE}")"
        mkdir -p "${CONFIG_DIR}"

        # Copy the sample file
        cp "${SAMPLE_FILE}" "${TEST_CREDENTIALS_FILE}"
        vlog "Copied sample test-setup.txt to ${TEST_CREDENTIALS_FILE}"
        vlog "Please review and update the configuration file with your credentials"
    else
        vlog "Sample test-setup.txt not found at ${SAMPLE_FILE}"
    fi
fi

if [[ -f "${TEST_CREDENTIALS_FILE}" ]]; then
    vlog "Loading additional test credentials from ${TEST_CREDENTIALS_FILE}"
    # Source the file, ignoring comments and empty lines
    while IFS= read -r line || [[ -n "$line" ]]; do
        # Skip comments and empty lines
        [[ "$line" =~ ^[[:space:]]*# ]] && continue
        [[ -z "${line// }" ]] && continue
        # Export the variable
        if [[ "$line" =~ ^[[:space:]]*([A-Za-z_][A-Za-z0-9_]*)=(.*)$ ]]; then
            export "${BASH_REMATCH[1]}"="${BASH_REMATCH[2]}"
            vlog "Loaded credential: ${BASH_REMATCH[1]}"
        fi
    done < "${TEST_CREDENTIALS_FILE}"
fi

###############################################################################
# Utility: detect invocation method for lftools-uv
###############################################################################
detect_lftools_cmd() {
  # Preference order: local dev via uv, installed lftools-uv in PATH
  if command -v uv >/dev/null 2>&1 && [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
    echo "uv run lftools-uv"
  elif command -v lftools-uv >/dev/null 2>&1; then
    echo "lftools-uv"
  else
    err "Unable to locate lftools-uv command. Install dependencies first (e.g. 'make install-dev' or 'uv sync')."
    exit 2
  fi
}

LFTOOLS_CMD="$(detect_lftools_cmd)"
vlog "Using lftools-uv command wrapper: ${LFTOOLS_CMD}"

###############################################################################
# Test Definitions
#
# Format per line (DO NOT introduce extra ':::'):
#   ID:::CATEGORY:::DESCRIPTION:::COMMAND:::REQUIRED_ENV_VARS
# Use '-' for no required env vars.
#
# NOTE: Keep lines <= ~180 chars for readability.
###############################################################################
read -r -d '' TEST_DEFINITIONS <<'EOF'
# ---------------------------
# CORE / BASE (Category 1)
core.version:::1:::Show lftools-uv version:::${LFTOOLS_CMD} --version:::-
core.help.root:::1:::Root help screen:::${LFTOOLS_CMD} --help:::-
core.help.version:::1:::Version command help:::${LFTOOLS_CMD} version --help:::-
core.help.schema:::1:::Schema command help:::${LFTOOLS_CMD} schema --help:::-
# ---------------------------
# JENKINS (Category 1) - read-only queries using configuration sections
jenkins.onap.builds.running:::1:::List running Jenkins builds (ONAP):::${LFTOOLS_CMD} jenkins -s onap-prod builds running:::-
jenkins.onap.builds.queued:::1:::List queued Jenkins builds (ONAP):::${LFTOOLS_CMD} jenkins -s onap-prod builds queued:::-
jenkins.onap.nodes.list:::1:::List Jenkins nodes (ONAP):::${LFTOOLS_CMD} jenkins -s onap-prod nodes list:::-
jenkins.onap.plugins.list:::1:::List Jenkins plugins (ONAP):::${LFTOOLS_CMD} jenkins -s onap-prod plugins list:::-
jenkins.onap.plugins.active:::1:::List active Jenkins plugins (ONAP):::${LFTOOLS_CMD} jenkins -s onap-prod plugins active:::-

# Alternative tests using environment variables (require JENKINS_URL)
jenkins.env.builds.running:::1:::List running Jenkins builds (env URL):::${LFTOOLS_CMD} jenkins -s "${JENKINS_URL}" builds running:::JENKINS_URL
jenkins.env.builds.queued:::1:::List queued Jenkins builds (env URL):::${LFTOOLS_CMD} jenkins -s "${JENKINS_URL}" builds queued:::JENKINS_URL
# ---------------------------
# LFIDAPI (Category 1) - Using existing configuration from lftools.ini
lfidapi.help:::1:::LFIDAPI help information:::${LFTOOLS_CMD} lfidapi --help:::-
# Note: Actual member searches require valid group names and may fail without proper access
# lfidapi.search.example:::1:::List members of example group:::${LFTOOLS_CMD} lfidapi search-members "example-group":::-
# ---------------------------
# LOCAL TOOLS (Category 1) - File system and local operations
license.help:::1:::License command help:::${LFTOOLS_CMD} license --help:::-
sign.help:::1:::Sign command help:::${LFTOOLS_CMD} sign --help:::-
utils.help:::1:::Utils command help:::${LFTOOLS_CMD} utils --help:::-
dco.help:::1:::DCO command help:::${LFTOOLS_CMD} dco --help:::-
infofile.help:::1:::Infofile command help:::${LFTOOLS_CMD} infofile --help:::-
deploy.help:::1:::Deploy command help:::${LFTOOLS_CMD} deploy --help:::-
gerrit.help:::1:::Gerrit command help:::${LFTOOLS_CMD} gerrit --help:::-
rtd.help:::1:::RTD command help:::${LFTOOLS_CMD} rtd --help:::-
# ---------------------------
# NEXUS2 (Category 1) - list repositories (read) - requires config section
# NOTE: Auth works and API response format compatibility has been fixed
nexus2.repo.list:::1:::List Nexus2 repositories:::${LFTOOLS_CMD} nexus2 "${NEXUS2_FQDN}" repo list:::NEXUS2_FQDN
# ---------------------------
# NEXUS3 (Category 1) - list repositories (read) - requires config section
nexus3.repository.list:::1:::List Nexus3 repositories:::${LFTOOLS_CMD} nexus3 "${NEXUS3_FQDN}" repository list:::NEXUS3_FQDN
# ---------------------------
# OPENSTACK (Category 1) - read-only queries using test-specific config
openstack.server.list:::1:::List OpenStack servers:::${LFTOOLS_CMD} openstack --os-cloud "${OS_CLOUD}" server list:::OS_CLOUD
openstack.image.list:::1:::List OpenStack images:::${LFTOOLS_CMD} openstack --os-cloud "${OS_CLOUD}" image list:::OS_CLOUD
openstack.volume.list:::1:::List OpenStack volumes:::${LFTOOLS_CMD} openstack --os-cloud "${OS_CLOUD}" volume list:::OS_CLOUD
# ---------------------------
# GITHUB (Category 1) - Org listing (read) - requires config section
github.org.list:::1:::List GitHub organization repos (requires token config):::${LFTOOLS_CMD} github list "${GITHUB_ORG}" --repos:::GITHUB_ORG
github.lfreleng.list:::1:::List lfreleng-actions organization repos:::${LFTOOLS_CMD} github list "lfreleng-actions" --repos:::-
# ---------------------------
# PYTHON-LDAP MODERNIZATION (Category 1) - Test modernized python-ldap dependency
ldap.import.test:::1:::Test python-ldap import (modernization validation):::uv run --extra ldap python3 -c "import ldap; print(f'python-ldap version: {ldap.__version__}')":::-
ldap.version.check:::1:::Verify python-ldap version meets modernization requirements:::uv run --extra ldap python3 -c "import ldap; from packaging import version; v=ldap.__version__; assert version.parse(v) >= version.parse('3.4.0'), f'Expected >=3.4.0, got {v}'; print(f'✓ python-ldap {v} meets modernization requirements')":::-
ldap.api.compatibility:::1:::Test LDAP API compatibility with existing code:::uv run --extra ldap python3 -c "import ldap; ldap_obj = ldap.initialize('ldap://example.com'); assert hasattr(ldap_obj, 'simple_bind_s'); print('✓ LDAP API compatibility verified')":::-
# Note: Actual LDAP server operations require credentials and would be Category 2
# ldap.server.connect:::2:::Test LDAP server connection (requires LDAP_SERVER, credentials):::uv run --extra ldap python3 -c "import ldap; conn=ldap.initialize('${LDAP_SERVER}'); conn.simple_bind_s('','')":::LDAP_SERVER
# ---------------------------
# PLACEHOLDER Category 2 (Reversible) - disabled
# Example: enabling/disabling Jenkins jobs (reversible) - disabled until harness ready
# jenkins.jobs.disable:::2:::Disable Jenkins jobs by regex (REQUIRES CAUTION):::${LFTOOLS_CMD} jenkins --url "${JENKINS_URL}" jobs disable 'test-regex':::JENKINS_URL
# jenkins.jobs.enable:::2:::Enable Jenkins jobs by regex:::${LFTOOLS_CMD} jenkins --url "${JENKINS_URL}" jobs enable 'test-regex':::JENKINS_URL
# nexus2.repo.create:::2:::Create temporary Nexus2 repo (requires cleanup):::-:::NEXUS2_FQDN
# nexus2.repo.delete:::2:::Delete temporary Nexus2 repo:::-:::NEXUS2_FQDN
# ---------------------------
# PLACEHOLDER Category 3 (Destructive / Hard to reverse) - disabled
# nexus.repo.release:::3:::Release staging repositories in Nexus (production impact):::${LFTOOLS_CMD} nexus release repo1 repo2:::NEXUS_URL
# nexus.docker.delete:::3:::Delete docker images in Nexus (irreversible):::${LFTOOLS_CMD} nexus docker delete myrepo '*':::NEXUS_URL
# github.createrepo:::3:::Create new GitHub repo (requires manual cleanup):::${LFTOOLS_CMD} github create-repo "${GITHUB_ORG}" temp-repo 'Temporary':::GITHUB_ORG
EOF

###############################################################################
# Parse test definitions into an array (ignore commented or blank lines)
###############################################################################
mapfile -t ALL_TEST_LINES < <(echo "${TEST_DEFINITIONS}" | grep -Ev '^\s*(#|$)')

# User-selected categories (normalize to comma list)
SELECTED_CATEGORIES="${TEST_CATEGORY// /}"
IFS=',' read -r -a CATEGORY_FILTER <<<"${SELECTED_CATEGORIES}"

contains_element() {
  local e match="$1"; shift
  for e; do [[ "$e" == "$match" ]] && return 0; done
  return 1
}

###############################################################################
# Harness Functions
###############################################################################
json_escape() {
  # Minimal JSON escaping for strings
  local s="$1"
  s="${s//\\/\\\\}"
  s="${s//\"/\\\"}"
  s="${s//$'\n'/\\n}"
  s="${s//$'\r'/\\r}"
  echo "$s"
}

check_required_env() {
  local req="$1"
  [[ "$req" == "-" || -z "$req" ]] && return 0
  IFS=',' read -r -a vars <<<"$req"
  local missing=()
  for v in "${vars[@]}"; do
    # Skip empty variable names that might come from parsing issues
    [[ -z "$v" ]] && continue
    if [[ -z "${!v:-}" ]]; then
      missing+=("$v")
    fi
  done
  if ((${#missing[@]})); then
    echo "${missing[*]}"
    return 1
  fi
  return 0
}

# Arrays to hold results
TEST_IDS=()
TEST_CATEGORIES=()
TEST_STATUSES=()     # PASSED | FAILED | SKIPPED
TEST_MESSAGES=()
TEST_DURATIONS_MS=()

record_result() {
  TEST_IDS+=("$1")
  TEST_CATEGORIES+=("$2")
  TEST_STATUSES+=("$3")
  TEST_MESSAGES+=("$4")
  TEST_DURATIONS_MS+=("$5")
}

run_test() {
  local id="$1" category="$2" desc="$3" cmd="$4" req_env="$5"

  # Category filter
  if ! contains_element "$category" "${CATEGORY_FILTER[@]}"; then
    vlog "Skipping ${id} (category ${category} not in selection)"
    record_result "$id" "$category" "SKIPPED" "CategoryFiltered" "0"
    return
  fi

  # TEST_FILTER substring
  if [[ -n "$TEST_FILTER" ]]; then
    if [[ "$id" != *"$TEST_FILTER"* && "$desc" != *"$TEST_FILTER"* ]]; then
      vlog "Skipping ${id} (filter mismatch)"
      record_result "$id" "$category" "SKIPPED" "FilterMismatch" "0"
      return
    fi
  fi

  # Env checks
  local missing_env
  if ! missing_env=$(check_required_env "$req_env"); then
    warn "Skipping ${id} - missing env: ${missing_env}"
    record_result "$id" "$category" "SKIPPED" "MissingEnv:${missing_env}" "0"
    return
  fi

  # DRY RUN
  if [[ "$DRY_RUN" == "1" ]]; then
    info "[DRY-RUN] ${id}: ${cmd}"
    record_result "$id" "$category" "SKIPPED" "DryRun" "0"
    return
  fi

  info "Running (${category}) ${id} - ${desc}"
  vlog "Command: $cmd"

  local start_ms end_ms dur_ms
  # Use seconds for timing on macOS (date +%s%3N not supported)
  start_ms=$(( $(date +%s) * 1000 ))

  local log_file="${LOG_DIR}/${id//[^A-Za-z0-9._-]/_}.log"
  local exit_code

  # shellcheck disable=SC2086
  if [[ "$DEBUG" == "1" ]]; then
    # Debug mode: show output to terminal AND log to file
    info "=== Command Output for ${id} ==="
    if eval "$cmd" 2>&1 | tee "$log_file"; then
      exit_code=0
    else
      exit_code=1
    fi
    info "=== End Output for ${id} ==="
  else
    # Normal mode: only log to file
    if eval "$cmd" &> "$log_file"; then
      exit_code=0
    else
      exit_code=1
    fi
  fi

  if [[ $exit_code -eq 0 ]]; then
    end_ms=$(( $(date +%s) * 1000 ))
    dur_ms=$(( end_ms - start_ms ))
    success "PASS ${id} (${dur_ms} ms)"
    record_result "$id" "$category" "PASSED" "OK (log: $log_file)" "$dur_ms"
  else
    end_ms=$(( $(date +%s) * 1000 ))
    dur_ms=$(( end_ms - start_ms ))
    err "FAIL ${id} (${dur_ms} ms) - see $log_file"
    record_result "$id" "$category" "FAILED" "SeeLog:${log_file}" "$dur_ms"
    if [[ "$STOP_ON_FAILURE" == "1" ]]; then
      warn "Stopping on first failure due to STOP_ON_FAILURE=1"
      return 1
    fi
  fi
}

###############################################################################
# Main Execution Loop
###############################################################################
info "Selected categories: ${SELECTED_CATEGORIES}"
[[ -n "$TEST_FILTER" ]] && info "Filter substring: ${TEST_FILTER}"
[[ "$DRY_RUN" == "1" ]] && info "DRY RUN mode active (no commands executed)"
[[ "$DEBUG" == "1" ]] && info "DEBUG mode active (displaying command output)"
[[ "$STOP_ON_FAILURE" == "1" ]] && info "Will stop on first failure"

for line in "${ALL_TEST_LINES[@]}"; do
  # Parse using parameter expansion instead of IFS read for triple colon delimiter
  tid="${line%%:::*}"
  rest="${line#*:::}"
  tcat="${rest%%:::*}"
  rest="${rest#*:::}"
  tdesc="${rest%%:::*}"
  rest="${rest#*:::}"
  tcmd="${rest%%:::*}"
  treq="${rest#*:::}"

  run_test "$tid" "$tcat" "$tdesc" "$tcmd" "$treq" || break
done

###############################################################################
# Summary
###############################################################################
TOTAL=${#TEST_IDS[@]}
PASSED=0 FAILED=0 SKIPPED=0
for st in "${TEST_STATUSES[@]}"; do
  case "$st" in
    PASSED) ((PASSED++));;
    FAILED) ((FAILED++));;
    SKIPPED) ((SKIPPED++));;
  esac
done

END_TIME_EPOCH=$(date +%s)
ELAPSED=$(( END_TIME_EPOCH - START_TIME_EPOCH ))

if [[ "$OUTPUT_FORMAT" == "json" ]]; then
  # Build JSON (send to stdout only)
  {
    printf '{'
    printf '"summary":{"total":%d,"passed":%d,"failed":%d,"skipped":%d,"elapsed_sec":%d},' "$TOTAL" "$PASSED" "$FAILED" "$SKIPPED" "$ELAPSED"
    printf '"tests":['
    for i in "${!TEST_IDS[@]}"; do
      [[ $i -gt 0 ]] && printf ','
      id="${TEST_IDS[$i]}"
      catg="${TEST_CATEGORIES[$i]}"
      st="${TEST_STATUSES[$i]}"
      msg="${TEST_MESSAGES[$i]}"
      dur="${TEST_DURATIONS_MS[$i]}"
      printf '{"id":"%s","category":"%s","status":"%s","duration_ms":%s,"message":"%s"}' \
        "$(json_escape "$id")" \
        "$(json_escape "$catg")" \
        "$(json_escape "$st")" \
        "$dur" \
        "$(json_escape "$msg")"
    done
    printf ']}\n'
  }
else
  {
    echo
    info "================ Functional Test Summary ================"
    info " Total:   ${TOTAL}"
    info " Passed:  ${PASSED}"
    info " Failed:  ${FAILED}"
    info " Skipped: ${SKIPPED}"
    info " Elapsed: ${ELAPSED}s"
    echo
    printf "%-28s %-8s %-8s %s\n" "TEST ID" "CAT" "STATUS" "DETAIL"
    printf "%-28s %-8s %-8s %s\n" "----------------------------" "----" "--------" "------------------------------"
    for i in "${!TEST_IDS[@]}"; do
      printf "%-28s %-8s %-8s %s\n" "${TEST_IDS[$i]}" "${TEST_CATEGORIES[$i]}" "${TEST_STATUSES[$i]}" "${TEST_MESSAGES[$i]}"
    done
    echo
    info "Logs directory: ${LOG_DIR}"
  } >&2
fi

EXIT_CODE=0
((FAILED>0)) && EXIT_CODE=1
exit "${EXIT_CODE}"
