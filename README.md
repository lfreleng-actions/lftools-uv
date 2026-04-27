<!--
SPDX-License-Identifier: EPL-1.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# LF Tools UV

[![Source Code](https://img.shields.io/badge/GitHub-100000?logo=github&logoColor=white&color=blue)](https://github.com/lfreleng-actions/lftools-uv)
[![OpenSSF Scorecard](https://api.securityscorecards.dev/projects/github.com/lfreleng-actions/lftools-uv/badge)](https://scorecard.dev/viewer/?uri=github.com/lfreleng-actions/lftools-uv)
[![License: EPL-1.0](https://img.shields.io/badge/License-EPL--1.0-blue.svg)](https://www.eclipse.org/legal/epl-v10.html)
[![PyPI](https://img.shields.io/pypi/v/lftools-uv.svg?label=PyPi)](https://pypi.org/project/lftools-uv/)
[![TestPyPI](https://img.shields.io/pypi/v/lftools-uv.svg?label=TestPyPi&pypiBaseUrl=https://test.pypi.org)](https://test.pypi.org/project/lftools-uv/)
[![CodeQL](https://github.com/lfreleng-actions/lftools-uv/actions/workflows/codeql.yml/badge.svg)](https://github.com/lfreleng-actions/lftools-uv/actions/workflows/codeql.yml)

This project's documentation is available on ReadTheDocs (RTD) and GitHub Pages:

- **Official Documentation**: <https://lftools-uv.readthedocs.io>
- **GitHub Pages**: <https://lfreleng-actions.github.io/lftools-uv/>

LF Tools UV is a collection of scripts and utilities that are useful to Linux
Foundation projects' CI and Releng related activities. We try to create
these tools to be as generic as possible such that they are reusable in other
CI environments.

## CLI Interface

**lftools-uv** uses Typer as the CLI library. For CI/CD environments that
require the previous Click-based output format, use `LEGACY_CLI=1`.

## Installation

### Using uv (Recommended)

This project uses [uv](https://docs.astral.sh/uv/) for fast Python package management.

1. Install uv:

   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. Install lftools-uv:

   ```bash
   uv pip install lftools-uv
   ```

3. Or install with all extras for development:

   ```bash
   uv pip install "lftools-uv[all]"
   ```

### Using pip

```bash
pip install lftools-uv
```

## Configuration

lftools uses configuration files in the standard `~/.config/lftools/`
directory for Jenkins, OpenStack, and other service credentials.

### Quick Setup

Use the setup helper to create example configuration files:

```bash
# Clone the repository first (if not already done)
git clone https://github.com/lfreleng-actions/lftools-uv.git
cd lftools-uv

# Run the configuration setup helper
./scripts/setup-config.sh
```

This creates:

- `~/.config/lftools/jenkins_job.ini` - Jenkins server configurations
- `~/.config/lftools/clouds.yaml` - OpenStack cloud configurations

### Manual Configuration

Create the configuration directory:

```bash
mkdir -p ~/.config/lftools
```

Copy and customize the example files:

```bash
# Jenkins configuration
cp etc/lftools/jenkins_job.ini.example ~/.config/lftools/jenkins_job.ini
# Edit with your Jenkins credentials

# OpenStack configuration
cp etc/lftools/clouds.yaml.example ~/.config/lftools/clouds.yaml
# Edit with your OpenStack credentials
```

### Testing Configuration

Test your configuration with basic commands:

```bash
# Test Jenkins connectivity
lftools jenkins -s onap-prod plugins list

# Test OpenStack connectivity
lftools openstack --os-cloud production image list

# Run comprehensive functional tests (see Functional Testing section below)
./scripts/run_functional_tests.sh
```

For detailed configuration instructions, see: [docs/configuration.md](docs/configuration.md)

## Functional Testing

The repository includes a comprehensive functional test harness that validates
lftools-uv commands against real infrastructure (Jenkins, OpenStack, Nexus,
GitHub, etc.).

### Basic Usage

```bash
# Run all Category 1 (safe/read-access) tests
./scripts/run_functional_tests.sh

# Run with debug output (shows command output to terminal)
./scripts/run_functional_tests.sh debug

# Filter tests by substring
TEST_FILTER=jenkins ./scripts/run_functional_tests.sh

# Run specific category with debug output
TEST_CATEGORY=1 DEBUG=1 ./scripts/run_functional_tests.sh
```

### Configuration Requirements

The functional tests work with standard lftools configuration files:

#### Jenkins Tests

- **File**: `~/.config/lftools/jenkins_job.ini`
- **Environment**: `JENKINS_URL`, `LFTOOLS_USERNAME`, `LFTOOLS_PASSWORD`
- **Default**: Uses `jenkins.onap.org` (read-access operations)

#### OpenStack Tests

- **File**: `~/.config/lftools/clouds.yaml`
- **Environment**: `OS_CLOUD` (default: `ecompci`)
- **Required**: Valid OpenStack credentials for cloud operations

#### Nexus Tests

- **Environment**: `NEXUS2_FQDN` (default: `nexus.onap.org`),
  `NEXUS3_FQDN` (default: `nexus3.onap.org`)
- **Operations**: Read-access repository queries

#### GitHub Tests

- **Environment**: `GITHUB_ORG` (default: `onap`), `GITHUB_TOKEN`
- **File**: Can use lftools config for token storage

### Test Categories

- **Category 1**: Safe, read-access operations (default)
- **Category 2**: Reversible operations (disabled by default)
- **Category 3**: Destructive operations (disabled by default)

### Advanced Options

```bash
# Environment variables
TEST_CATEGORY=1,2          # Run two categories
TEST_FILTER=openstack      # Filter by substring
STOP_ON_FAILURE=1          # Stop after first failure
DRY_RUN=1                  # Show what would run
DEBUG=1                    # Show command output
VERBOSE=1                  # More logging
OUTPUT_FORMAT=json         # JSON output format

# Examples
TEST_FILTER=nexus DEBUG=1 ./scripts/run_functional_tests.sh
STOP_ON_FAILURE=1 ./scripts/run_functional_tests.sh debug
```

### Debug Mode

Debug mode displays actual command output to the terminal while tests run:

```bash
# Enable debug mode
./scripts/run_functional_tests.sh debug
DEBUG=1 ./scripts/run_functional_tests.sh

# Debug specific tests
TEST_FILTER=openstack ./scripts/run_functional_tests.sh debug
```text

**Debug Output Example:**

```text
2025-09-20T09:12:32Z [INFO] DEBUG mode active (displaying command output)
2025-09-20T09:12:32Z [INFO] Running (1) core.version - Show lftools-uv version
2025-09-20T09:12:32Z [INFO] === Command Output for core.version ===
lftools-uv 0.1.5.dev2
2025-09-20T09:12:32Z [INFO] === End Output for core.version ===
2025-09-20T09:12:32Z [OK] PASS core.version (0 ms)
```

### Log Files

Test output is always logged to files regardless of debug mode:

- **Location**: `.functional_logs/` directory
- **Format**: `{test_id}.log` files
- **Content**: Complete command output for analysis

### Quick Setup for Testing

```bash
# 1. Set up configuration files
./scripts/setup-config.sh

# 2. Run some basic tests
TEST_FILTER=core ./scripts/run_functional_tests.sh debug

# 3. Test specific functionality
TEST_FILTER=jenkins ./scripts/run_functional_tests.sh debug
TEST_FILTER=openstack ./scripts/run_functional_tests.sh debug

# 4. Run all safe tests
./scripts/run_functional_tests.sh
```

Most tests pass with default ONAP/ECOMPCI configurations, making it easy to
verify your lftools-uv installation and basic connectivity.

### Using uvx for CI/CD (Recommended)

[uvx](https://docs.astral.sh/uv/guides/tools/) is ideal for CI/CD environments
and one-off executions where you want to run lftools-uv without affecting the
existing Python environment. It creates an isolated virtual environment for
each execution, preventing dependency conflicts with other tools in your pipeline.

#### uvx Basic Usage

Run lftools-uv commands directly without installation:

```bash
# Basic command execution
uvx lftools-uv version

# Run with help
uvx lftools-uv --help
```

#### Using Optional Dependencies

When using features that require optional dependencies (like LDAP or
OpenStack), you need to specify the extras:

```bash
# For LDAP functionality - note the quotes to prevent shell expansion
uvx "lftools-uv[ldap]" ldap --help

# For OpenStack functionality
uvx "lftools-uv[openstack]" openstack --help

# Combined extras
uvx "lftools-uv[ldap,openstack]" --help

# All extras for full functionality
uvx "lftools-uv[all]" --help
```

#### Alternative uvx Syntax

You can also use the `--from` flag for clarity:

```bash
# Same as the above
uvx --from "lftools-uv[ldap]" lftools-uv ldap csv mygroup
uvx --from "lftools-uv[openstack]" lftools-uv openstack --help
```

#### CI/CD Pipeline Examples

**GitHub Actions:**

```yaml
- name: Deploy artifacts with lftools-uv
  run: |
    uvx lftools-uv deploy nexus-zip \
      --nexus-url ${{ secrets.NEXUS_URL }} \
      --nexus-repo releases \
      ./artifacts/*.zip
```

**GitLab CI:**

```yaml
deploy:
  script:
    - uvx "lftools-uv[all]" deploy logs --help
    - uvx lftools-uv sign sigul ./artifacts/
```

**Jenkins Pipeline:**

```groovy
pipeline {
    agent any
    stages {
        stage('Deploy') {
            steps {
                sh 'uvx lftools-uv version'
                sh 'uvx "lftools-uv[ldap]" ldap csv project-committers'
            }
        }
    }
}
```

#### Benefits of uvx in CI/CD

- **Isolation**: No interference with existing Python packages in the CI environment
- **Speed**: Automatic caching of environments between runs
- **Consistency**: Same tool version across different pipeline stages
- **No Setup**: No need to manage virtual environments or installations
- **Clean**: Environments are automatically cleaned up after execution

## Development Setup

### Prerequisites

- Python 3.8+
- uv (recommended) or pip

### Quick Start with uv

1. Clone the repository:

   ```bash
   git clone https://github.com/lfreleng-actions/lftools-uv.git
   cd lftools-uv
   ```

2. Install development dependencies:

   ```bash
   make install-dev
   # or manually:
   uv sync --extra dev --extra test --extra docs --extra ldap --extra openstack
   ```

3. Run tests:

   ```bash
   make test
   # or manually:
   uv run pytest
   ```

4. Format and lint code:

   ```bash
   make format
   make lint
   ```

### Available Make Targets

- `make help` - Show all available targets
- `make install` - Install project dependencies
- `make install-dev` - Install with all development dependencies
- `make test` - Run tests
- `make lint` - Run linting
- `make format` - Format code
- `make build` - Build package
- `make docs` - Build documentation
- `make clean` - Clean build artifacts
- `make all` - Run full development pipeline

### Ubuntu Dependencies

For development on Ubuntu, you may need:

- build-essential
- python3-dev
- libldap2-dev
- libsasl2-dev
- libssl-dev

## Repository Information

The canonical repository for this project is:

- **Repository**: `https://github.com/lfreleng-actions/lftools-uv.git`

### Local Git Setup

Configure your local git remote:

```bash
git remote -v
# origin  https://github.com/lfreleng-actions/lftools-uv.git (fetch)
# origin  https://github.com/lfreleng-actions/lftools-uv.git (push)
```
