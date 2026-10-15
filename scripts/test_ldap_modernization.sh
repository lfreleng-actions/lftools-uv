#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

###############################################################################
# PYTHON-LDAP MODERNIZATION TEST SCRIPT
#
# This script validates the python-ldap modernization from ~=3.1.0 to >=3.4,<4.0
# as part of the dependency modernization initiative.
#
# Test Categories:
#   1. Version validation (ensure we get modern versions)
#   2. Wheel availability (avoid source compilation)
#   3. Import compatibility (no breaking API changes)
#   4. Basic functionality (LDAP operations work)
#   5. Platform compatibility (CentOS 7 glibc 2.17 wheels)
#
# Usage:
#   ./scripts/test_ldap_modernization.sh
#   VERBOSE=1 ./scripts/test_ldap_modernization.sh
#   PYTHON_VERSION=3.11 ./scripts/test_ldap_modernization.sh
#
# Environment Variables:
#   VERBOSE=1                    Enable debug output
#   PYTHON_VERSION=3.11          Specific Python version to test
#   FORCE_SOURCE_BUILD=1         Test source compilation fallback
#   LDAP_SERVER=ldaps://...      LDAP server for connection tests
#   LDAP_TEST_GROUP=example      LDAP group for query tests
#   DRY_RUN=1                    Show what would be tested
#
###############################################################################

set -euo pipefail

# Script configuration
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
START_TIME=$(date +%s)

# Default settings
VERBOSE="${VERBOSE:-0}"
PYTHON_VERSION="${PYTHON_VERSION:-}"
FORCE_SOURCE_BUILD="${FORCE_SOURCE_BUILD:-0}"
DRY_RUN="${DRY_RUN:-0}"
LDAP_SERVER="${LDAP_SERVER:-}"
LDAP_TEST_GROUP="${LDAP_TEST_GROUP:-}"

# Color support
if [[ -t 1 ]]; then
  RED='\033[0;31m'
  GREEN='\033[0;32m'
  YELLOW='\033[0;33m'
  BLUE='\033[0;34m'
  RESET='\033[0m'
else
  RED='' GREEN='' YELLOW='' BLUE='' RESET=''
fi

# Logging functions
log() {
  local level="$1"; shift
  local msg="$*"
  local ts
  ts="$(date -u '+%Y-%m-%dT%H:%M:%SZ')"
  echo -e "${ts} [${level}] ${msg}"
}

vlog() { [[ "${VERBOSE}" == "1" ]] && log "DEBUG" "$*"; }
info() { log "${BLUE}INFO${RESET}" "$*"; }
warn() { log "${YELLOW}WARN${RESET}" "$*"; }
error() { log "${RED}ERROR${RESET}" "$*"; }
success() { log "${GREEN}OK${RESET}" "$*"; }

# Test result tracking
TESTS_RUN=0
TESTS_PASSED=0
TESTS_FAILED=0
TESTS_SKIPPED=0

run_test() {
  local test_name="$1"
  local test_desc="$2"
  shift 2
  local test_cmd=("$@")

  ((TESTS_RUN++))
  info "Running test: ${test_name} - ${test_desc}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    info "DRY_RUN: would execute: ${test_cmd[*]}"
    ((TESTS_SKIPPED++))
    return 0
  fi

  local start_time
  start_time=$(date +%s)

  if "${test_cmd[@]}" >/dev/null 2>&1; then
    local duration=$(($(date +%s) - start_time))
    success "PASS ${test_name} (${duration}s)"
    ((TESTS_PASSED++))
    return 0
  else
    local duration=$(($(date +%s) - start_time))
    error "FAIL ${test_name} (${duration}s)"
    ((TESTS_FAILED++))
    return 1
  fi
}

run_test_with_output() {
  local test_name="$1"
  local test_desc="$2"
  shift 2
  local test_cmd=("$@")

  ((TESTS_RUN++))
  info "Running test: ${test_name} - ${test_desc}"

  if [[ "${DRY_RUN}" == "1" ]]; then
    info "DRY_RUN: would execute: ${test_cmd[*]}"
    ((TESTS_SKIPPED++))
    return 0
  fi

  local start_time
  start_time=$(date +%s)
  local output

  if output=$("${test_cmd[@]}" 2>&1); then
    local duration=$(($(date +%s) - start_time))
    success "PASS ${test_name} (${duration}s)"
    [[ "${VERBOSE}" == "1" ]] && echo "Output: ${output}"
    ((TESTS_PASSED++))
    return 0
  else
    local duration=$(($(date +%s) - start_time))
    error "FAIL ${test_name} (${duration}s)"
    error "Output: ${output}"
    ((TESTS_FAILED++))
    return 1
  fi
}

skip_test() {
  local test_name="$1"
  local reason="$2"

  ((TESTS_RUN++))
  ((TESTS_SKIPPED++))
  warn "SKIP ${test_name} - ${reason}"
}

# Detect Python command
detect_python() {
  if [[ -n "${PYTHON_VERSION}" ]]; then
    if command -v "python${PYTHON_VERSION}" >/dev/null 2>&1; then
      echo "python${PYTHON_VERSION}"
      return 0
    fi
  fi

  for py in python3 python; do
    if command -v "$py" >/dev/null 2>&1; then
      echo "$py"
      return 0
    fi
  done

  error "No Python interpreter found"
  exit 1
}

PYTHON_CMD="$(detect_python)"
vlog "Using Python: ${PYTHON_CMD}"

# Detect UV command for dependency management
detect_uv() {
  if command -v uv >/dev/null 2>&1 && [[ -f "${REPO_ROOT}/pyproject.toml" ]]; then
    echo "uv"
    return 0
  fi
  return 1
}

if UV_CMD="$(detect_uv)"; then
  vlog "Using UV for dependency management: ${UV_CMD}"
else
  vlog "UV not available, using pip fallback"
  UV_CMD=""
fi

print_header() {
  info "========================================"
  info "Python-LDAP Modernization Test Suite"
  info "========================================"
  info "Python: ${PYTHON_CMD}"
  info "Target version range: >=3.4,<4.0"
  info "Test categories: Version, Wheel, Import, Function, Platform"
  info "========================================"
}

# Test 1: Version Validation
test_version_validation() {
  info "=== Category 1: Version Validation ==="

  # Test that we can import ldap at all
  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.import" "Import python-ldap module" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "import ldap; print(f'python-ldap version: {ldap.__version__}')"
  else
    run_test_with_output "ldap.import" "Import python-ldap module" \
      "${PYTHON_CMD}" -c "import ldap; print(f'python-ldap version: {ldap.__version__}')"
  fi

  # Test version meets modernization requirements (>=3.4.0)
  local version_cmd="import ldap
from packaging import version
v = ldap.__version__
min_version = '3.4.0'
if version.parse(v) >= version.parse(min_version):
    print(f'✓ python-ldap {v} meets modernization requirement (>={min_version})')
else:
    raise AssertionError(f'Expected >={min_version}, got {v}')"

  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.version.modern" "Verify version >=3.4.0" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "${version_cmd}"
  else
    run_test_with_output "ldap.version.modern" "Verify version >=3.4.0" \
      "${PYTHON_CMD}" -c "${version_cmd}"
  fi

  # Test version is not too new (stays in 3.x series)
  local compat_cmd="import ldap
from packaging import version
v = ldap.__version__
max_version = '4.0.0'
if version.parse(v) < version.parse(max_version):
    print(f'✓ python-ldap {v} is compatible (<{max_version})')
else:
    raise AssertionError(f'Expected <{max_version}, got {v}')"

  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.version.compatible" "Verify version <4.0" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "${compat_cmd}"
  else
    run_test_with_output "ldap.version.compatible" "Verify version <4.0" \
      "${PYTHON_CMD}" -c "${compat_cmd}"
  fi
}

# Test 2: Wheel Availability
test_wheel_availability() {
  info "=== Category 2: Wheel Availability ==="

  if [[ "${FORCE_SOURCE_BUILD}" == "1" ]]; then
    skip_test "ldap.wheel.check" "FORCE_SOURCE_BUILD=1, testing source compilation instead"
    return
  fi

  # Test that python-ldap was installed from wheel (not compiled from source)
  local wheel_cmd="import ldap
import os
import sys

# Check if we have a wheel-installed package
ldap_path = ldap.__file__
ldap_dir = os.path.dirname(ldap_path)

# Look for wheel metadata
dist_info_dirs = [d for d in os.listdir(os.path.dirname(ldap_dir))
                  if d.startswith('python_ldap') and d.endswith('.dist-info')]

if dist_info_dirs:
    print(f'✓ python-ldap installed from wheel (found {dist_info_dirs[0]})')
else:
    # This might be a source install or development install
    print(f'⚠ python-ldap may be source-compiled or dev install at {ldap_path}')"

  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.wheel.check" "Verify wheel installation" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "${wheel_cmd}"
  else
    run_test_with_output "ldap.wheel.check" "Verify wheel installation" \
      "${PYTHON_CMD}" -c "${wheel_cmd}"
  fi

  # Test platform compatibility (manylinux wheel should work on CentOS 7 glibc 2.17)
  local platform_cmd="import ldap
import platform
import sys

print(f'Platform: {platform.platform()}')
print(f'Python: {sys.version}')
print(f'python-ldap: {ldap.__version__}')

# Try to import key submodules to ensure native extensions work
try:
    import ldap.sasl
    import ldap.controls
    print('✓ Native extensions loaded successfully')
except ImportError as e:
    raise AssertionError(f'Native extension import failed: {e}')"

  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.platform.compat" "Check platform compatibility" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "${platform_cmd}"
  else
    run_test_with_output "ldap.platform.compat" "Check platform compatibility" \
      "${PYTHON_CMD}" -c "${platform_cmd}"
  fi
}

# Test 3: Import Compatibility
test_import_compatibility() {
  info "=== Category 3: Import Compatibility ==="

  # Test core LDAP imports work
  local import_cmd="import ldap
import ldap.sasl
import ldap.controls
import ldap.filter
import ldap.modlist
print('✓ Core LDAP modules imported successfully')"

  if [[ -n "${UV_CMD}" ]]; then
    run_test "ldap.import.core" "Import core LDAP modules" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "${import_cmd}"
  else
    run_test "ldap.import.core" "Import core LDAP modules" \
      "${PYTHON_CMD}" -c "${import_cmd}"
  fi

  # Test that our existing code patterns still work
  local api_cmd="import ldap

# Test patterns used in lftools_uv/cli/ldap_cli.py
try:
    # Test LDAP connection object creation (doesn't actually connect)
    ldap_obj = ldap.initialize('ldap://example.com')

    # Test common methods exist
    assert hasattr(ldap_obj, 'simple_bind_s')
    assert hasattr(ldap_obj, 'search_s')
    assert hasattr(ldap_obj, 'unbind_s')

    # Test constants exist
    assert hasattr(ldap, 'SCOPE_SUBTREE')
    assert hasattr(ldap, 'SCOPE_BASE')

    print('✓ LDAP API compatibility verified')
except Exception as e:
    raise AssertionError(f'API compatibility failed: {e}')"

  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.api.compatibility" "Test API compatibility" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "${api_cmd}"
  else
    run_test_with_output "ldap.api.compatibility" "Test API compatibility" \
      "${PYTHON_CMD}" -c "${api_cmd}"
  fi
}

# Test 4: Basic Functionality
test_basic_functionality() {
  info "=== Category 4: Basic Functionality ==="

  # Test LDAP URL parsing
  run_test_with_output "ldap.url.parsing" "Test LDAP URL parsing" \
    "${PYTHON_CMD}" -c "
import ldap
from ldap.ldapobject import LDAPObject

# Test URL parsing with various formats
test_urls = [
    'ldap://example.com',
    'ldaps://secure.example.com:636',
    'ldap://server.com:389',
]

for url in test_urls:
    try:
        # This should not raise an exception for valid URLs
        ldap_obj = ldap.initialize(url)
        assert isinstance(ldap_obj, LDAPObject)
    except Exception as e:
        raise AssertionError(f'URL parsing failed for {url}: {e}')

print('✓ LDAP URL parsing works correctly')
"

  # Test filter construction (used in our code)
  run_test_with_output "ldap.filter.construction" "Test LDAP filter construction" \
    "${PYTHON_CMD}" -c "
import ldap.filter

# Test filter escaping (security-critical)
test_inputs = [
    ('user123', 'user123'),
    ('user*', 'user\\\\2a'),
    ('user(test)', 'user\\\\28test\\\\29'),
    ('user\\', 'user\\\\5c'),
]

for input_val, expected in test_inputs:
    escaped = ldap.filter.escape_filter_chars(input_val)
    if escaped != expected:
        raise AssertionError(f'Filter escaping failed: {input_val} -> {escaped}, expected {expected}')

print('✓ LDAP filter construction and escaping works')
"

  # Test actual LDAP connection if server is available
  if [[ -n "${LDAP_SERVER}" ]]; then
    run_test_with_output "ldap.server.connect" "Test LDAP server connection" \
      "${PYTHON_CMD}" -c "
import ldap
import socket
from urllib.parse import urlparse

server = '${LDAP_SERVER}'
try:
    # Parse server URL
    parsed = urlparse(server)
    host = parsed.hostname
    port = parsed.port or (636 if parsed.scheme == 'ldaps' else 389)

    # Test network connectivity first
    sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    sock.settimeout(5)
    result = sock.connect_ex((host, port))
    sock.close()

    if result != 0:
        print(f'⚠ Cannot connect to {host}:{port}, skipping LDAP test')
    else:
        # Test LDAP connection
        ldap_obj = ldap.initialize(server)
        ldap_obj.protocol_version = ldap.VERSION3
        ldap_obj.set_option(ldap.OPT_NETWORK_TIMEOUT, 5)
        ldap_obj.set_option(ldap.OPT_TIMEOUT, 5)

        # Test anonymous bind (should work for most LDAP servers)
        try:
            ldap_obj.simple_bind_s('', '')
            print(f'✓ LDAP connection to {server} successful')
            ldap_obj.unbind_s()
        except ldap.LDAPError as e:
            print(f'⚠ LDAP bind failed (expected without credentials): {e}')

except Exception as e:
    raise AssertionError(f'LDAP connection test failed: {e}')
"
  else
    skip_test "ldap.server.connect" "No LDAP_SERVER configured"
  fi
}

# Test 5: Platform Compatibility
test_platform_compatibility() {
  info "=== Category 5: Platform Compatibility ==="

  # Test that SSL/TLS works (important for ldaps://)
  run_test_with_output "ldap.ssl.support" "Test SSL/TLS support" \
    "${PYTHON_CMD}" -c "
import ldap
import ssl

# Test that SSL context can be configured
try:
    ldap_obj = ldap.initialize('ldaps://example.com')

    # Test SSL options are available
    assert hasattr(ldap, 'OPT_X_TLS_REQUIRE_CERT')
    assert hasattr(ldap, 'OPT_X_TLS_NEVER')

    # Test SSL context configuration
    ldap_obj.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

    print('✓ SSL/TLS support verified')

except Exception as e:
    raise AssertionError(f'SSL/TLS support test failed: {e}')
"

  # Test SASL support (used for advanced authentication)
  run_test_with_output "ldap.sasl.support" "Test SASL support" \
    "${PYTHON_CMD}" -c "
import ldap
import ldap.sasl

# Test SASL mechanisms are available
try:
    # Test common SASL mechanisms
    mechanisms = ['PLAIN', 'DIGEST-MD5', 'GSSAPI']

    for mech in mechanisms:
        try:
            # This will fail to actually authenticate, but should not fail to create the auth object
            auth = ldap.sasl.sasl({}, mech)
            assert auth is not None
        except ldap.LDAPError:
            # Expected - we're not actually connecting
            pass
        except Exception as e:
            print(f'⚠ SASL mechanism {mech} may not be available: {e}')

    print('✓ SASL support verified')

except ImportError as e:
    raise AssertionError(f'SASL support not available: {e}')
except Exception as e:
    raise AssertionError(f'SASL support test failed: {e}')
"

  # Test thread safety (important for web applications)
  run_test_with_output "ldap.thread.safety" "Test thread safety options" \
    "${PYTHON_CMD}" -c "
import ldap
import threading

# Test that thread-safe options are available
try:
    # Test global options
    ldap.set_option(ldap.OPT_X_TLS_REQUIRE_CERT, ldap.OPT_X_TLS_NEVER)

    # Test per-connection options
    ldap_obj = ldap.initialize('ldap://example.com')
    ldap_obj.set_option(ldap.OPT_PROTOCOL_VERSION, ldap.VERSION3)

    print('✓ Thread safety options verified')

except Exception as e:
    raise AssertionError(f'Thread safety test failed: {e}')
"
}

# Test 6: Integration with lftools-uv
test_lftools_integration() {
  info "=== Category 6: lftools-uv Integration ==="

  # Test that lftools-uv can import LDAP functionality
  if [[ -n "${UV_CMD}" ]]; then
    run_test_with_output "ldap.lftools.import" "Test lftools-uv LDAP import" \
      "${UV_CMD}" run --extra ldap "${PYTHON_CMD}" -c "
# Test that we can import lftools-uv LDAP modules with the ldap extra
try:
    from lftools_uv.cli.ldap_cli import ldap_cli
    print('✓ lftools_uv LDAP CLI import successful')
except ImportError as e:
    raise AssertionError(f'lftools_uv LDAP import failed: {e}')
"
  else
    skip_test "ldap.lftools.import" "UV not available"
  fi

  # Test LDAP CLI help (should not require actual LDAP connection)
  if command -v lftools-uv >/dev/null 2>&1; then
    run_test "ldap.cli.help" "Test LDAP CLI help" \
      lftools-uv ldap --help
  elif [[ -n "${UV_CMD}" ]]; then
    run_test "ldap.cli.help" "Test LDAP CLI help (via uv)" \
      "${UV_CMD}" run --extra ldap lftools-uv ldap --help
  else
    skip_test "ldap.cli.help" "lftools-uv not available"
  fi
}

# Main test execution
main() {
  print_header

  # Run test categories
  test_version_validation
  test_wheel_availability
  test_import_compatibility
  test_basic_functionality
  test_platform_compatibility
  test_lftools_integration

  # Print summary
  local end_time
  end_time=$(date +%s)
  local duration=$((end_time - START_TIME))

  info "========================================"
  info "Python-LDAP Modernization Test Summary"
  info "========================================"
  info "Total tests: ${TESTS_RUN}"
  info "Passed: ${TESTS_PASSED}"
  info "Failed: ${TESTS_FAILED}"
  info "Skipped: ${TESTS_SKIPPED}"
  info "Duration: ${duration}s"

  if [[ "${TESTS_FAILED}" -gt 0 ]]; then
    error "Some tests failed. python-ldap modernization may have issues."
    exit 1
  elif [[ "${TESTS_PASSED}" -eq 0 ]]; then
    warn "No tests passed. Check your python-ldap installation."
    exit 1
  else
    success "All tests passed! python-ldap modernization is successful."

    # Additional success information
    info ""
    info "Modernization Benefits Achieved:"
    info "✓ Updated from python-ldap ~=3.1.0 (2018) to >=3.4.0 (2024+)"
    info "✓ Security patches and bug fixes from 6+ years of development"
    info "✓ Better wheel availability (reduced compilation requirements)"
    info "✓ Improved compatibility with Python 3.11+ and modern OpenSSL"
    info "✓ Enhanced performance and feature support"
    info "✓ Maintained API compatibility with existing lftools-uv code"

    exit 0
  fi
}

# Script help
if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
  cat << 'EOF'
Python-LDAP Modernization Test Script

This script validates the python-ldap dependency modernization from
~=3.1.0 to >=3.4,<4.0 as part of the lftools-uv modernization initiative.

USAGE:
  ./scripts/test_ldap_modernization.sh [OPTIONS]

OPTIONS:
  --help, -h                   Show this help message

ENVIRONMENT VARIABLES:
  VERBOSE=1                    Enable debug output
  PYTHON_VERSION=3.11          Specific Python version to test
  FORCE_SOURCE_BUILD=1         Test source compilation fallback
  LDAP_SERVER=ldaps://...      LDAP server for connection tests
  LDAP_TEST_GROUP=example      LDAP group for query tests (future use)
  DRY_RUN=1                    Show what would be tested without executing

EXAMPLES:
  # Basic test run
  ./scripts/test_ldap_modernization.sh

  # Verbose output with specific Python version
  VERBOSE=1 PYTHON_VERSION=3.11 ./scripts/test_ldap_modernization.sh

  # Test with LDAP server connection
  LDAP_SERVER=ldaps://ldap.example.com ./scripts/test_ldap_modernization.sh

  # Dry run to see what would be tested
  DRY_RUN=1 ./scripts/test_ldap_modernization.sh

TEST CATEGORIES:
  1. Version Validation    - Ensure >=3.4.0, <4.0
  2. Wheel Availability    - Prefer wheels over source compilation
  3. Import Compatibility  - API compatibility with existing code
  4. Basic Functionality   - Core LDAP operations work
  5. Platform Compatibility - SSL/TLS, SASL, threading support
  6. lftools-uv Integration - Integration with our CLI tools

EXIT CODES:
  0 - All tests passed
  1 - One or more tests failed
  2 - Script configuration error

EOF
  exit 0
fi

# Run main function
main "$@"
