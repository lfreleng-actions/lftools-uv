<!--
SPDX-License-Identifier: Apache-2.0
SPDX-FileCopyrightText: 2025 The Linux Foundation
-->

# Installing UV on CentOS 7 Systems

This document provides comprehensive guidance for installing the UV Python
package manager on CentOS 7 systems, which presents unique challenges due to
the end-of-life status of CentOS 7.

## Overview

CentOS 7 reached end-of-life in June 2024, which creates notable challenges
for installing modern tools like UV:

1. **Repository mirrors are unavailable** - Standard CentOS mirrors no longer
   serve CentOS 7 packages
2. **Outdated system libraries** - CentOS 7 ships with glibc 2.17, which is
   too old for most modern binaries
3. **Security concerns** - No more security updates are available

Despite these challenges, you can install and use UV on CentOS 7 systems.

## Quick Installation

For a fully automated installation, use the provided script:

```bash
# Download and run the installation script
curl -LsSf \
  https://raw.githubusercontent.com/lfreleng-actions/lftools-uv/main/scripts/\
install_uv_centos7.sh | sudo bash

# Or download first, inspect, then run
wget https://raw.githubusercontent.com/lfreleng-actions/lftools-uv/main/scripts/\
install_uv_centos7.sh
sudo bash install_uv_centos7.sh
```

## Manual Installation Steps

If you prefer to install manually or need to understand the process:

### 1. Fix CentOS 7 Repositories

Since CentOS 7 mirrors are no longer available, redirect to the vault:

```bash
# Backup original repo configuration
sudo cp -r /etc/yum.repos.d /etc/yum.repos.d.backup

# Update repository URLs
sudo sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-*.repo
sudo sed -i \
  's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' \
  /etc/yum.repos.d/CentOS-*.repo

# Rebuild package cache
sudo yum clean all
sudo yum makecache
```

### 2. Install Dependencies

```bash
sudo yum install -y curl wget which
```

### 3. Install UV

The UV installer automatically detects the old glibc and uses the musl-static version:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 4. System-wide Installation

To make UV available to all users:

```bash
sudo cp ~/.local/bin/uv /usr/local/bin/
sudo cp ~/.local/bin/uvx /usr/local/bin/
sudo chmod +x /usr/local/bin/uv /usr/local/bin/uvx
```

### 5. Configure System PATH

Create a profile script so UV is available in all shell sessions:

```bash
sudo tee /etc/profile.d/uv.sh << 'EOF'
# UV Python package manager
export PATH="/usr/local/bin:$PATH"
EOF

sudo chmod +x /etc/profile.d/uv.sh
```

## Verification

Test the installation:

```bash
# Check version
uv --version

# Test basic functionality
uv --help

# Create and test a sample project
mkdir /tmp/uv-test
cd /tmp/uv-test
uv init test-project
cd test-project
uv add requests
uv run main.py
```

## Docker Testing

We validated this approach using Docker. You can reproduce our testing:

```bash
# Start CentOS 7 container
docker run -d --name centos7-test centos:7 tail -f /dev/null

# Fix repositories
docker exec centos7-test bash -c "
sed -i 's/mirrorlist/#mirrorlist/g' /etc/yum.repos.d/CentOS-*.repo &&
sed -i 's|#baseurl=http://mirror.centos.org|baseurl=http://vault.centos.org|g' /etc/yum.repos.d/CentOS-*.repo
"

# Install dependencies and UV
docker exec centos7-test bash -c "
yum clean all && yum makecache &&
yum install -y curl wget which &&
curl -LsSf https://astral.sh/uv/install.sh | sh
"

# Test UV
docker exec centos7-test bash -c "
export PATH=\$HOME/.local/bin:\$PATH &&
uv --version &&
cd /tmp &&
uv init test &&
cd test &&
uv add requests &&
uv run main.py
"

# Cleanup
docker stop centos7-test && docker rm centos7-test
```

## How It Works

### UV's Automatic Fallback

The UV installer handles old systems intelligently:

1. **Glibc Detection**: It checks the system glibc version
2. **Automatic Fallback**: When it detects glibc < 2.18, it downloads the
   musl-static version
3. **Statically Linked**: The musl-static version has no external dependencies
   and works on any Linux system

### Repository Vault

CentOS provides vault.centos.org for accessing packages from EOL releases:

- **vault.centos.org**: Archive of all CentOS packages
- **Same package structure**: Mirrors the original repository layout
- **No security updates**: Packages freeze at EOL state

## Troubleshooting

### Common Issues

### "Could not resolve host: mirrorlist.centos.org"

- Solution: Run the repository fix steps above

### "No such file or directory" for UV

- Solution: Ensure `/usr/local/bin` is in your PATH
- Run: `source /etc/profile.d/uv.sh` or start a new shell

### Permission denied

- Solution: Ensure UV binaries are executable
- Run: `sudo chmod +x /usr/local/bin/uv /usr/local/bin/uvx`

### Verification Commands

```bash
# Check if repositories are working
sudo yum repolist

# Check if UV is in PATH
which uv

# Check UV functionality
uv pip --help
uv python list
```

## Security Considerations

### CentOS 7 EOL Risks

- **No security updates**: CentOS 7 no longer receives security patches
- **Vulnerable packages**: System packages may have known vulnerabilities
- **Network exposure**: Reduce network-facing services

### Mitigation Strategies

1. **Containerization**: Use CentOS 7 in containers with minimal exposure
2. **Network isolation**: Place CentOS 7 systems behind firewalls
3. **Limit services**: Reduce network-facing services
4. **Migration planning**: Develop timeline to migrate to supported
   distributions
5. **Monitoring**: Deploy security monitoring for these systems

### UV Security

- **Static binary**: The musl-static version has minimal attack surface
- **No system dependencies**: Doesn't rely on potentially vulnerable system libraries
- **Isolated environments**: UV creates isolated Python environments

## Production Deployment

### Deployment Script

The provided `install_uv_centos7.sh` script supports production use:

- **Idempotent**: Safe to run again
- **Logged output**: Clear feedback on all operations
- **Error handling**: Fails fast with clear error messages
- **Backup creation**: Preserves original configuration

### Ansible Playbook Example

```yaml
---
- name: Install UV on CentOS 7
  hosts: centos7_servers
  become: yes
  tasks:
    - name: Download UV installation script
      get_url:
        url: https://raw.githubusercontent.com/lfreleng-actions/lftools-uv/main/scripts/install_uv_centos7.sh
        dest: /tmp/install_uv_centos7.sh
        mode: '0755'

    - name: Run UV installation
      command: /tmp/install_uv_centos7.sh
      register: uv_install

    - name: Verify UV installation
      command: uv --version
      register: uv_version

    - name: Display UV version
      debug:
        msg: "UV installed: {{ uv_version.stdout }}"
```

### Configuration Management

For large deployments, consider:

1. **Package repository**: Host the UV binary in your internal repository
2. **Configuration templates**: Standardize UV configuration across systems
3. **Monitoring**: Track UV installations and versions
4. **Updates**: Plan for UV updates (manual process on CentOS 7)

## Migration Planning

### Long-term Strategy

CentOS 7 systems require migration to supported distributions:

1. **Assessment**: Inventory all CentOS 7 systems
2. **Prioritization**: Identify critical vs. non-critical systems
3. **Testing**: Test applications on target distributions
4. **Migration schedule**: Plan phased migration approach

### Target Distributions

Consider these alternatives:

- **RHEL 8/9**: Direct upgrade path with Red Hat support
- **AlmaLinux 8/9**: Community-supported RHEL rebuild
- **Rocky Linux 8/9**: Another RHEL rebuild option
- **Ubuntu 20.04/22.04 LTS**: Popular alternative with long support

### UV on Modern Systems

On supported distributions, UV installation is straightforward:

```bash
# Standard installation (works on modern systems)
curl -LsSf https://astral.sh/uv/install.sh | sh
```

## Alternatives to UV on CentOS 7

If UV installation fails, consider these alternatives:

### pip-tools

```bash
sudo yum install python3-pip
pip3 install --user pip-tools
```

### pipenv

```bash
sudo yum install python3-pip
pip3 install --user pipenv
```

### poetry (may require newer Python)

```bash
# May need Python 3.8+ from EPEL or SCL
sudo yum install epel-release
sudo yum install python38
python3.8 -m pip install --user poetry
```

## Support and Resources

### Getting Help

1. **UV Documentation**: <https://docs.astral.sh/uv/>
2. **CentOS Vault**: <https://vault.centos.org/>
3. **Migration guides**: Research RHEL/AlmaLinux/Rocky migration paths

### Internal Support

- Maintain documentation of your specific use cases
- Create testing procedures for your applications
- Document any custom configurations or workarounds
- Plan regular reviews of CentOS 7 systems

---

*This documentation reflects testing performed in October 2024. The
installation approach should remain valid as long as vault.centos.org continues
to serve CentOS 7 packages and UV maintains musl-static builds.*
