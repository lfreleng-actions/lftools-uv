#!/usr/bin/env bash
# SPDX-License-Identifier: Apache-2.0
# SPDX-FileCopyrightText: 2025 The Linux Foundation

###############################################################################
# LFTOOLS-UV CONFIGURATION SETUP HELPER
#
# This script helps set up lftools-uv configuration files in the standard
# locations with proper permissions and example content.
#
# Usage:
#   ./scripts/setup-config.sh [--force] [--help]
#
# Options:
#   --force    Overwrite existing configuration files
#   --help     Show this help message
#
# The script will:
# 1. Create ~/.config/lftools/ directory if it doesn't exist
# 2. Copy example configuration files (if they don't exist or --force is used)
# 3. Set appropriate file permissions (600 for security)
# 4. Provide guidance on customizing the configurations
#
###############################################################################

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
LFTOOLS_CONFIG_DIR="${HOME}/.config/lftools"

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

# Logging functions
info() { echo -e "${COLOR_BLUE}INFO${COLOR_RESET} $*"; }
warn() { echo -e "${COLOR_YELLOW}WARN${COLOR_RESET} $*"; }
error() { echo -e "${COLOR_RED}ERROR${COLOR_RESET} $*"; }
success() { echo -e "${COLOR_GREEN}SUCCESS${COLOR_RESET} $*"; }

# Show help
show_help() {
    cat << EOF
lftools-uv Configuration Setup Helper

This script helps set up lftools-uv configuration files in the standard
~/.config/lftools/ directory.

USAGE:
    ./scripts/setup-config.sh [OPTIONS]

OPTIONS:
    --force     Overwrite existing configuration files
    --help      Show this help message

CONFIGURATION FILES:
    jenkins_job.ini     Jenkins server configurations
    clouds.yaml         OpenStack cloud configurations

The script will create example files that you need to customize with
your actual credentials and server details.

EXAMPLES:
    # Initial setup
    ./scripts/setup-config.sh

    # Force overwrite existing files
    ./scripts/setup-config.sh --force

NEXT STEPS:
    1. Edit ~/.config/lftools/jenkins_job.ini with your Jenkins credentials
    2. Edit ~/.config/lftools/clouds.yaml with your OpenStack credentials
    3. Test your configuration with: ./scripts/run_functional_tests.sh

For more information, see: docs/configuration.md
EOF
}

# Parse command line arguments
FORCE=false
while [[ $# -gt 0 ]]; do
    case $1 in
        --force)
            FORCE=true
            shift
            ;;
        --help|-h)
            show_help
            exit 0
            ;;
        *)
            error "Unknown option: $1"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# Configuration file definitions
declare -A CONFIG_FILES=(
    ["jenkins_job.ini"]="Jenkins server configurations"
    ["clouds.yaml"]="OpenStack cloud configurations"
)

# Check if repo example files exist
check_example_files() {
    local missing_files=()

    for config_file in "${!CONFIG_FILES[@]}"; do
        local example_file="${REPO_ROOT}/etc/lftools/${config_file}.example"
        if [[ ! -f "$example_file" ]]; then
            missing_files+=("$example_file")
        fi
    done

    if [[ ${#missing_files[@]} -gt 0 ]]; then
        error "Missing example configuration files:"
        for file in "${missing_files[@]}"; do
            echo "  - $file"
        done
        error "Please ensure you're running this script from the lftools-uv repository root"
        exit 1
    fi
}

# Create configuration directory
create_config_dir() {
    if [[ ! -d "$LFTOOLS_CONFIG_DIR" ]]; then
        info "Creating configuration directory: $LFTOOLS_CONFIG_DIR"
        mkdir -p "$LFTOOLS_CONFIG_DIR"
        success "Created configuration directory"
    else
        info "Configuration directory already exists: $LFTOOLS_CONFIG_DIR"
    fi
}

# Copy configuration file
copy_config_file() {
    local config_file="$1"
    local description="$2"
    local example_file="${REPO_ROOT}/etc/lftools/${config_file}.example"
    local target_file="${LFTOOLS_CONFIG_DIR}/${config_file}"

    if [[ -f "$target_file" && "$FORCE" != "true" ]]; then
        warn "Configuration file already exists: $target_file"
        warn "Use --force to overwrite"
        return 0
    fi

    info "Copying $description: $config_file"
    cp "$example_file" "$target_file"

    # Set secure permissions
    chmod 600 "$target_file"

    success "Created $target_file"
}

# Show next steps
show_next_steps() {
    cat << EOF

${COLOR_GREEN}Configuration Setup Complete!${COLOR_RESET}

NEXT STEPS:

1. ${COLOR_YELLOW}Customize Jenkins Configuration:${COLOR_RESET}
   Edit: ${LFTOOLS_CONFIG_DIR}/jenkins_job.ini
   - Replace 'your-*-username' with actual Jenkins usernames
   - Replace 'your-*-api-token' with actual Jenkins API tokens
   - Update server URLs as needed
   - Remove unused server sections

2. ${COLOR_YELLOW}Customize OpenStack Configuration:${COLOR_RESET}
   Edit: ${LFTOOLS_CONFIG_DIR}/clouds.yaml
   - Replace 'your-*' placeholders with actual credentials
   - Update auth_url, project names, and regions
   - Consider using application credentials for automation
   - Remove unused cloud sections

3. ${COLOR_YELLOW}Test Your Configuration:${COLOR_RESET}
   # Test Jenkins connectivity
   lftools-uv jenkins -s onap-prod plugins list

   # Test OpenStack connectivity
   lftools-uv openstack --os-cloud production image list

   # Run functional tests
   ./scripts/run_functional_tests.sh

4. ${COLOR_YELLOW}Security Best Practices:${COLOR_RESET}
   - Use API tokens instead of passwords for Jenkins
   - Use application credentials for OpenStack automation
   - Never commit real credentials to version control
   - Regularly rotate credentials

${COLOR_BLUE}For detailed configuration instructions, see: docs/configuration.md${COLOR_RESET}

${COLOR_YELLOW}Current Configuration Files:${COLOR_RESET}
EOF

    # List created files with permissions
    for config_file in "${!CONFIG_FILES[@]}"; do
        local target_file="${LFTOOLS_CONFIG_DIR}/${config_file}"
        if [[ -f "$target_file" ]]; then
            local perms
            perms=$(stat -f '%p' "$target_file" 2>/dev/null || stat -c '%a' "$target_file" 2>/dev/null || echo "unknown")
            echo "  $target_file ($perms)"
        fi
    done
}

# Main execution
main() {
    info "Starting lftools-uv configuration setup..."

    # Verify example files exist
    check_example_files

    # Create configuration directory
    create_config_dir

    # Copy configuration files
    local files_created=0
    for config_file in "${!CONFIG_FILES[@]}"; do
        if copy_config_file "$config_file" "${CONFIG_FILES[$config_file]}"; then
            ((files_created++))
        fi
    done

    if [[ $files_created -eq 0 && "$FORCE" != "true" ]]; then
        info "All configuration files already exist"
        info "Use --force to overwrite existing files"
        echo ""
        info "Current configuration directory: $LFTOOLS_CONFIG_DIR"
        ls -la "$LFTOOLS_CONFIG_DIR"
    else
        show_next_steps
    fi
}

# Execute main function
main "$@"
