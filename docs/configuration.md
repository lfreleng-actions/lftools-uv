<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# lftools-uv Configuration

This document describes how to configure lftools-uv for use with Jenkins,
OpenStack, and other services.

## Configuration Directory

lftools-uv uses the standard XDG configuration directory structure. The
directory keeps the `lftools` name so that lftools-uv and legacy lftools
share one configuration:

```bash
~/.config/lftools/
├── jenkins_job.ini     # Jenkins server configurations
├── clouds.yaml         # OpenStack cloud configurations
└── lftools.ini         # General settings (optional)
```

## Jenkins Configuration

### Jenkins Location

Jenkins server configurations go in `~/.config/lftools/jenkins_job.ini`.

### Jenkins Format

The configuration file uses INI format with sections for each Jenkins
server:

```ini
[job_builder]
ignore_cache=True
keep_descriptions=False
include_path=.
recursive=False
exclude_path=
allow_duplicates=False
update=jobs

# Default Jenkins server
[jenkins]
user=your-username
password=your-api-token
url=https://jenkins.example.com/

# ONAP Production Jenkins
[onap-prod]
user=your-onap-username
password=your-onap-api-token
url=https://jenkins.onap.org/

# ONAP Sandbox Jenkins
[onap-sandbox]
user=your-onap-username
password=your-onap-api-token
url=https://jenkins.onap.org/sandbox/
```

### Required Stanzas

Each Jenkins server section must include:

- `user` - Jenkins username
- `password` - Jenkins API token (recommended) or password
- `url` - Full Jenkins server URL

### Common Server Sections

Based on typical lftools-uv usage, you may need these sections:

- `onap-prod` - ONAP production Jenkins
- `onap-sandbox` - ONAP sandbox Jenkins
- `odl` - OpenDaylight Jenkins (if applicable)
- `jenkins` - Default/fallback Jenkins server
- `local` - Local development Jenkins

### API Token Generation

For security, use API tokens instead of passwords:

1. Log into Jenkins
2. Go to User Settings → Configure
3. Click "Add new Token" in the API Token section
4. Copy the generated token to your configuration file

### Usage

Reference Jenkins servers by section name:

```bash
# Use specific server
lftools-uv jenkins -s onap-prod builds running

# Use with config file override
lftools-uv jenkins -c /path/to/jenkins_job.ini -s onap-prod nodes list
```

## OpenStack Configuration

### OpenStack Location

OpenStack cloud configurations go in `~/.config/lftools/clouds.yaml`.

### OpenStack Format

The configuration file uses YAML format following the standard OpenStack
clouds.yaml specification:

```yaml
clouds:
  production:
    auth:
      auth_url: https://keystone.production.example.com:5000/v3
      username: your-username
      password: your-password
      project_name: your-project
      project_domain_name: Default
      user_domain_name: Default
    region_name: RegionOne
    interface: public
    identity_api_version: 3

  # Application credentials (recommended for automation)
  prod-app-creds:
    auth:
      auth_url: https://keystone.production.example.com:5000/v3
      application_credential_id: your-app-credential-id
      application_credential_secret: your-app-credential-secret
    region_name: RegionOne
    interface: public
    identity_api_version: 3
```

### Required Fields

Each cloud must include:

- `auth.auth_url` - Keystone authentication URL
- `auth` section with credentials (username/password or application credentials)
- `region_name` - OpenStack region
- `interface` - API interface type (typically 'public')
- `identity_api_version` - Keystone API version (typically 3)

### OpenStack Usage

Reference clouds by name:

```bash
# Use specific cloud
lftools-uv openstack --os-cloud production image list

# Set via environment variable
export OS_CLOUD=production
lftools-uv openstack image cleanup --days 30
```

## Configuration Precedence

lftools-uv searches for configuration files in this order:

### Jenkins Config Search Order

1. Path specified by `JENKINS_JOBS_INI` environment variable
2. `~/.config/lftools/jenkins_job.ini` (standard location)
3. `~/.config/jenkins_jobs/jenkins_jobs.ini` (legacy)
4. `/etc/jenkins_jobs/jenkins_jobs.ini` (system-wide)
5. `./jenkins_jobs.ini` (current directory)

### OpenStack Config Search Order

1. Path specified by `OS_CLIENT_CONFIG_FILE` environment variable
2. `~/.config/lftools/clouds.yaml` (standard location)
3. Standard OpenStack client locations

## Environment Variable Overrides

You can override configuration locations using environment variables:

```bash
# Jenkins configuration
export JENKINS_JOBS_INI=/custom/path/jenkins_job.ini

# OpenStack configuration
export OS_CLIENT_CONFIG_FILE=/custom/path/clouds.yaml

# OpenStack cloud selection
export OS_CLOUD=production
```

## ONAP/ECOMPCI Project Defaults

The functional test harness includes built-in defaults for ONAP/ECOMPCI project
infrastructure.

### Default Values

When environment variables are not explicitly set, the system uses these defaults:

- `JENKINS_URL=https://jenkins.onap.org`
- `NEXUS2_FQDN=nexus.onap.org`
- `NEXUS3_FQDN=nexus3.onap.org`
- `OS_CLOUD=ecompci`
- `GITHUB_ORG=onap`

### Benefits

- **Immediate Testing**: Run functional tests without extensive configuration
- **ONAP Integration**: Tests work out-of-the-box with ONAP infrastructure
- **Reduced Setup**: Fewer skipped tests due to missing environment variables

### Overriding Defaults

You can override any default by setting the corresponding environment variable:

```bash
# Use different Jenkins server
export JENKINS_URL=https://jenkins.example.com

# Use different OpenStack cloud
export OS_CLOUD=production

# Use different GitHub organization
export GITHUB_ORG=myorg

# Run tests with overrides
./scripts/run_functional_tests.sh
```

### Example: Using Custom Infrastructure

```bash
# Override all defaults for custom infrastructure
export JENKINS_URL=https://jenkins.mycompany.com
export NEXUS2_FQDN=nexus.mycompany.com
export NEXUS3_FQDN=nexus3.mycompany.com
export OS_CLOUD=mycloud
export GITHUB_ORG=myorg

# Run tests
./scripts/run_functional_tests.sh
```

## Example Setup

### 1. Create Configuration Directory

```bash
mkdir -p ~/.config/lftools
```

### 2. Copy Example Files

```bash
# Copy example configurations
cp etc/lftools/jenkins_job.ini.example ~/.config/lftools/jenkins_job.ini
cp etc/lftools/clouds.yaml.example ~/.config/lftools/clouds.yaml
```

### 3. Customize Configurations

Edit the files to include your actual credentials and server details.

### 4. Test Configuration

```bash
# Test Jenkins connectivity
lftools-uv jenkins -s onap-prod plugins list

# Test OpenStack connectivity
lftools-uv openstack --os-cloud production image list
```

## Security Best Practices

1. **Use API tokens** instead of passwords for Jenkins
2. **Use application credentials** instead of user credentials for OpenStack automation
3. **Set restrictive permissions** on configuration files:

   ```bash
   chmod 600 ~/.config/lftools/jenkins_job.ini
   chmod 600 ~/.config/lftools/clouds.yaml
   ```

4. **Never commit** configuration files with real credentials to version control
5. **Rotate** API tokens and application credentials periodically

## Troubleshooting

### Jenkins Connection Issues

1. Verify the server URL is correct and accessible
2. Check that the username exists in Jenkins
3. Ensure the API token is valid and has necessary permissions
4. Test connectivity with curl:

   ```bash
   curl -u username:token https://jenkins.example.com/api/json
   ```

### OpenStack Connection Issues

1. Verify the auth_url is correct and accessible
2. Check that credentials are valid
3. Ensure the project/domain names are correct
4. Test with OpenStack CLI:

   ```bash
   openstack --os-cloud production server list
   ```

### Configuration Not Found

1. Check file paths and permissions
2. Verify environment variables if using custom locations
3. Enable debug logging:

   ```bash
   lftools-uv --debug jenkins -s onap-prod builds running
   ```

## Functional Testing

The `scripts/run_functional_tests.sh` script automatically uses configurations from:

- `~/.config/lftools/jenkins_job.ini` for Jenkins tests
- `~/.config/lftools/clouds.yaml` for OpenStack tests

Run functional tests to verify your configuration:

```bash
# Run all safe tests
./scripts/run_functional_tests.sh

# Run Jenkins tests
TEST_FILTER=jenkins ./scripts/run_functional_tests.sh

# Run with verbose output
VERBOSE=1 ./scripts/run_functional_tests.sh
```
