<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Functional Test Harness for lftools-uv

This directory contains the functional/integration test harness for `lftools-uv`.
The harness exercises CLI commands against real infrastructure to detect
regressions, configuration issues, and compatibility problems.

## Quick Start

```bash
# Run all Category 1 (safe/read) tests
./scripts/run_functional_tests.sh

# Run specific test groups
TEST_FILTER=jenkins ./scripts/run_functional_tests.sh
TEST_FILTER=core ./scripts/run_functional_tests.sh

# Verbose output for debugging
VERBOSE=1 ./scripts/run_functional_tests.sh

# JSON output for CI integration
OUTPUT_FORMAT=json ./scripts/run_functional_tests.sh > test_results.json
```

## Configuration Requirements

The harness leverages your lftools configuration from the standard locations.
Based on what commands you want to test, you'll need:

### Jenkins Tests (Working)

- **Configuration**: `~/.config/lftools/jenkins_job.ini`
- **Tests Available**: ONAP production Jenkins instances
- **What's Tested**: Running builds, queue status, node lists, plugin
  inventories

Your configuration should include these Jenkins environments:

- `onap-prod` - ONAP production Jenkins
- `onap-sandbox` - ONAP sandbox Jenkins
- `jenkins` - Default Jenkins server
- And others as needed...

### OpenStack Tests (Available)

- **Configuration**: `~/.config/lftools/clouds.yaml`
- **Tests Available**: Image management, server operations
- **What's Tested**: Cloud connectivity, image listings

### LFID API Tests (Available)

- **Configuration**: `~/.config/lftools/lftools.ini*` files
- **Current Status**: Help commands working; actual API calls need group
  names

### Nexus2/Nexus3 Tests (Need Configuration)

- **Missing**: Configuration sections for Nexus instances
- **Required Format**:

  ```ini
  [nexus.example.org]
  username = your-username
  password = your-token-or-password
  endpoint = https://nexus.example.org/service/local/
  ```

### GitHub Tests (Need Configuration)

- **Missing**: GitHub token configuration
- **Required Format**:

  ```ini
  [github]
  token = your-github-token

  # OR organization-specific:
  [github.onap]
  token = your-github-token
  ```

## Test Categories

## Category 1: Harmless (Enabled)

Safe operations that read data or display help. No state changes.

**Passing (28/30 tests with ONAP/ECOMPCI defaults):**

- ✅ Core functionality (version, help screens)
- ✅ Jenkins integration (ONAP production environment)
  - Build status queries
  - Node inventory
  - Plugin information
- ✅ Nexus2/Nexus3 integration (using nexus.onap.org, nexus3.onap.org)
  - Repository listings
  - Service connectivity
- ✅ OpenStack integration (using ecompci cloud)
  - Server, image, and volume listings
  - Cloud connectivity validation
- ✅ GitHub integration (using onap organization)
  - Repository listings
  - API connectivity
- ✅ All CLI help screens (license, sign, utils, dco, infofile, deploy,
  gerrit, rtd, lfidapi)

**Automatic Defaults:**

The test harness now includes ONAP/ECOMPCI project defaults that remove most
configuration requirements:

- `JENKINS_URL=https://jenkins.onap.org` (if not set)
- `NEXUS2_FQDN=nexus.onap.org` (if not set)
- `NEXUS3_FQDN=nexus3.onap.org` (if not set)
- `OS_CLOUD=ecompci` (if not set)
- `GITHUB_ORG=onap` (if not set)

**May Need Custom Configuration:**

- 🔧 Jenkins credentials (for authenticated operations)
- 🔧 OpenStack credentials (for ecompci cloud access)
- 🔧 GitHub tokens (for API rate limits)

### Category 2: Reversible (Disabled - Future Work)

Operations that change state but can be reliably undone.

**Examples (not yet implemented):**

- Enable/disable Jenkins jobs (with re-enable)
- Create temporary Nexus repositories (with cleanup)
- GitHub repository/team creation (with deletion)

### Category 3: Destructive (Disabled - Staging Required)

High-risk operations that are difficult to reverse.

**Examples (not yet implemented):**

- Release staging repositories
- Delete artifacts or images
- Production infrastructure changes

## Environment Variables

| Variable | Default | Purpose |
| -------- | ------- | ------- |
| `TEST_CATEGORY` | `1` | Comma-separated categories to run (1,2,3) |
| `TEST_FILTER` | (none) | Substring to match test IDs/descriptions |
| `STOP_ON_FAILURE` | `0` | Stop after first failure (1=yes, 0=no) |
| `DRY_RUN` | `0` | Show what would run without executing (1=yes, 0=no) |
| `VERBOSE` | `0` | Enable debug logging (1=yes, 0=no) |
| `OUTPUT_FORMAT` | `plain` | Output format (`plain` or `json`) |
| `LOG_DIR` | `.functional_logs` | Directory for test execution logs |

### Infrastructure-Specific Variables

| Variable | Purpose | Example |
| -------- | ------- | ------- |
| `JENKINS_URL` | Jenkins server URL for env tests | `https://jenkins.org/` |
| `NEXUS2_FQDN` | Nexus2 server hostname | `nexus.example.org` |
| `NEXUS3_FQDN` | Nexus3 server hostname | `nexus3.example.org` |
| `GITHUB_ORG` | GitHub organization name | `onap` |

## Usage Examples

### Development & Debugging

```bash
# Test Jenkins functionality with verbose output
VERBOSE=1 TEST_FILTER=jenkins ./scripts/run_functional_tests.sh

# Dry run to see what would execute
DRY_RUN=1 ./scripts/run_functional_tests.sh

# Test specific environment variables
JENKINS_URL=https://jenkins.example.org/ TEST_FILTER=jenkins.env ./scripts/run_functional_tests.sh
```

### CI/CD Integration

```bash
# Generate JSON for build pipeline consumption
OUTPUT_FORMAT=json ./scripts/run_functional_tests.sh > functional_test_results.json

# Fail fast for continuous integration
STOP_ON_FAILURE=1 ./scripts/run_functional_tests.sh
```

### Selective Testing

```bash
# Test help screens (fastest)
TEST_FILTER=help ./scripts/run_functional_tests.sh

# Test all working infrastructure integrations
TEST_FILTER=jenkins ./scripts/run_functional_tests.sh

# Test core functionality
TEST_FILTER=core ./scripts/run_functional_tests.sh
```

## Extending the Test Suite

### Adding a New Test

Add a line to the `TEST_DEFINITIONS` block in `run_functional_tests.sh`:

```text
test.id:::CATEGORY:::Description:::COMMAND:::REQUIRED_ENV_VARS
```

**Format Rules:**

- Use `:::` as the field separator
- Categories: 1 (harmless), 2 (reversible), 3 (destructive)
- Required env vars: comma-separated or `-` for none
- Commands can use `${LFTOOLS_CMD}` variable and environment variables

**Examples:**

```bash
# No environment requirements
core.new.feature:::1:::Test new core feature:::${LFTOOLS_CMD} newfeature --help:::-

# Requires environment variable
jenkins.new.endpoint:::1:::Test new Jenkins endpoint:::${LFTOOLS_CMD} \
  jenkins -s "${JENKINS_URL}" new-command:::JENKINS_URL

# Environment requirements
complex.test:::1:::Complex integration test:::${LFTOOLS_CMD} complex \
  --server "${SERVER}" --org "${ORG}":::SERVER,ORG
```

### Adding Configuration-Based Tests

For services that use configuration sections (like Jenkins, Nexus, GitHub):

```bash
# Uses jenkins_jobs.ini section
jenkins.prod.new:::1:::Test new Jenkins prod feature:::${LFTOOLS_CMD} \
  jenkins -s onap-prod new-feature:::-

# Uses lftools.ini section (requires config setup)
nexus.prod.repos:::1:::List production Nexus repos:::${LFTOOLS_CMD} \
  nexus2 nexus.onap.org repo list:::-
```

## Current Test Results Summary

**Status**: 20/25 tests passing (80% pass rate)

**Passing Infrastructure Integrations:**

- ✅ Jenkins (ONAP production) - 5 tests
- ✅ Jenkins (OpenDaylight production) - 2 tests
- ✅ All CLI help screens - 9 tests
- ✅ Core functionality - 4 tests

**Pending Setup:**

- ⏸️ Nexus2/3 integration (needs credentials)
- ⏸️ GitHub integration (needs token)
- ⏸️ Other Jenkins environments (credentials available)

## Troubleshooting

### Common Issues

1. **"No section: 'server.name'"**
   - Missing configuration section in lftools.ini or jenkins_jobs.ini
   - Add required configuration or skip those tests

2. **"MissingEnv: VARIABLE_NAME"**
   - Set required environment variable
   - Or change test to use configuration sections instead

3. **Authentication failures**
   - Check credentials in configuration files
   - Verify network access to target infrastructure

### Debugging Failed Tests

1. **Check test logs**:

   ```bash
   ls .functional_logs/
   cat .functional_logs/failed-test-name.log
   ```

2. **Run single test with verbose output**:

   ```bash
   VERBOSE=1 TEST_FILTER=specific-test ./scripts/run_functional_tests.sh
   ```

3. **Test command manually**:

   ```bash
   uv run lftools-uv jenkins -s onap-prod builds running
   ```

## Future Enhancements

### Planned Improvements

- [ ] Category 2 test harness with cleanup mechanisms
- [ ] JUnit XML output format for better CI integration
- [ ] Test dependency management (setup/teardown)
- [ ] Configuration validation helper
- [ ] Parallel test execution for performance
- [ ] Test data generators for isolated testing

### Configuration Expansion

- [ ] Add Nexus test instance configurations
- [ ] Set up GitHub token for organization testing
- [ ] Add LDAP test configurations (when available)
- [ ] Expand OpenStack testing (when infrastructure available)

## CentOS 7 UV Installation

This directory also contains scripts and documentation for installing UV on
CentOS 7 systems, which presents unique challenges due to the end-of-life
status of CentOS 7.

### Quick Installation

For CentOS 7 systems, use the dedicated installation script:

```bash
# Download and run the installation script
curl -LsSf \
  https://raw.githubusercontent.com/lfreleng-actions/lftools-uv/main/scripts/\
install_uv_centos7.sh | sudo bash

# Or download, inspect, then run
wget https://raw.githubusercontent.com/lfreleng-actions/lftools-uv/main/scripts/install_uv_centos7.sh
sudo bash install_uv_centos7.sh
```

### Available CentOS 7 Scripts

- **`install_uv_centos7.sh`** - Automated UV installation for CentOS 7
  - Fixes EOL repository configuration to use vault.centos.org
  - Installs dependencies and UV system-wide
  - Handles glibc compatibility issues automatically

- **`validate_uv_centos7.sh`** - Comprehensive validation of UV installation
  - Tests all UV functionality on CentOS 7
  - Provides detailed compatibility reports
  - Suitable for production validation

- **`test_centos7_docker.sh`** - Docker-based testing demonstration
  - Demonstrates complete installation process
  - Uses Docker containers for isolated testing
  - Validates both manual and automated installation

### Documentation

See `CENTOS7_UV_INSTALLATION.md` for comprehensive documentation including:

- Manual installation steps
- Troubleshooting common issues
- Security considerations for EOL systems
- Production deployment strategies
- Migration planning from CentOS 7

### CentOS 7 Challenges Addressed

1. **Repository mirrors unavailable** - Automatically redirects to vault.centos.org
2. **Outdated glibc (2.17)** - UV installer detects and uses musl-static version
3. **System-wide installation** - Configures UV for all users with proper PATH setup
4. **Production deployment** - Provides scripts suitable for automation and
   configuration management

### Testing the Installation

```bash
# Test installation on existing CentOS 7 system
sudo ./scripts/validate_uv_centos7.sh

# Test installation process using Docker
./scripts/test_centos7_docker.sh
```

We tested and verified this approach on CentOS 7.9 systems and it provides
a reliable path for deploying UV on legacy infrastructure while planning
migration to supported distributions.

## Security Notes

- Configuration files may contain sensitive tokens/passwords
- Test logs exist locally and may contain auth traces
- Category 2/3 tests will require security review
- Never commit actual credentials to version control
- **CentOS 7 EOL Security**: CentOS 7 no longer receives security updates -
  reduce network exposure and plan migration to supported distributions

## Integration with CI/CD

The JSON output format supports CI pipeline consumption:

```json
{
  "summary": {
    "total": 25,
    "passed": 20,
    "failed": 0,
    "skipped": 5,
    "elapsed_sec": 21
  },
  "tests": [
    {
      "id": "test.name",
      "category": "1",
      "status": "PASSED",
      "duration_ms": 1000,
      "message": "OK (log: path/to/log)"
    }
  ]
}
```

Build systems can parse this to generate test reports, track regression
trends, and fail builds when critical infrastructure integration fails.
