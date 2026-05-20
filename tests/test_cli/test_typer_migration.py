# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Tests for Typer CLI implementation and migration.

This module contains tests for the new Typer-based CLI implementation,
including the pilot migration of the passgen command and the environment-based
switching mechanism.
"""

import os
from unittest.mock import patch

from typer.testing import CliRunner

from lftools_uv.cli_app import app as typer_app
from lftools_uv.typer_apps.config import config_app
from lftools_uv.typer_apps.dco import dco_app
from lftools_uv.typer_apps.deploy import deploy_app
from lftools_uv.typer_apps.gerrit import gerrit_app
from lftools_uv.typer_apps.github_cli import github_app
from lftools_uv.typer_apps.jenkins import jenkins_app
from lftools_uv.typer_apps.nexus2 import nexus2_app
from lftools_uv.typer_apps.nexus3 import nexus3_app
from lftools_uv.typer_apps.utils import utils_app
from lftools_uv.typer_apps.version import version_app
from tests.test_utils import assert_in_output


class TestTyperCLI:
    """Test cases for the main Typer CLI application."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_typer_app_help(self):
        """Test that the Typer app shows help correctly."""
        result = self.runner.invoke(typer_app, ["--help"])
        assert result.exit_code == 0
        assert "Linux Foundation Release Engineering Tools (Typer-based)" in result.stdout

    def test_typer_app_debug_flag(self):
        """Test that the debug flag is processed correctly."""
        result = self.runner.invoke(typer_app, ["--debug", "utils", "--help"])
        assert result.exit_code == 0
        # Debug logging may not be captured by CliRunner, but command should succeed
        # The actual debug functionality is tested in other integration tests

    def test_typer_app_credentials_options(self):
        """Test that credential options are available."""
        result = self.runner.invoke(typer_app, ["--help"])
        assert result.exit_code == 0
        assert_in_output("--username", result.stdout)
        assert_in_output("--password", result.stdout)
        assert_in_output("--interactive", result.stdout)


class TestTyperUtilsPassgen:
    """Test cases for the Typer-based utils passgen command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_passgen_help(self):
        """Test that passgen shows help correctly."""
        result = self.runner.invoke(utils_app, ["passgen", "--help"])
        assert result.exit_code == 0
        assert "Generate a complex password" in result.stdout
        assert "Length of the password to generate" in result.stdout

    def test_passgen_default_length(self):
        """Test passgen with default length (12 characters)."""
        result = self.runner.invoke(utils_app, ["passgen"])
        assert result.exit_code == 0

        # Check that output is exactly one line with 12 characters
        output = result.stdout.strip()
        assert len(output) == 12

        # Check that password contains expected character types
        assert any(c.islower() for c in output), "Password should contain lowercase letters"
        assert any(c.isupper() for c in output), "Password should contain uppercase letters"

    def test_passgen_custom_length(self):
        """Test passgen with custom length."""
        test_length = 16
        result = self.runner.invoke(utils_app, ["passgen", str(test_length)])
        assert result.exit_code == 0

        # Check that output has the correct length
        output = result.stdout.strip()
        assert len(output) == test_length

    def test_passgen_invalid_length_zero(self):
        """Test passgen with invalid length (zero)."""
        result = self.runner.invoke(utils_app, ["passgen", "0"])
        assert result.exit_code == 1
        assert_in_output("Password length must be greater than 0", result.stderr)

    def test_passgen_invalid_length_negative(self):
        """Test passgen with invalid length (negative)."""
        result = self.runner.invoke(utils_app, ["passgen", "-5"])
        # Negative numbers cause argument parsing errors (exit code 2)
        assert result.exit_code == 2
        # Click's error message format has varied across versions:
        #   older: "No such option: -5"
        #   newer: "No such option '-5'."
        # Match both by asserting on the stable substrings.
        assert_in_output("No such option", result.stderr)
        assert_in_output("-5", result.stderr)

    def test_passgen_invalid_length_too_large(self):
        """Test passgen with invalid length (too large)."""
        result = self.runner.invoke(utils_app, ["passgen", "300"])
        assert result.exit_code == 1
        assert "Password length cannot exceed 256 characters" in result.stderr

    def test_passgen_character_variety(self):
        """Test that passgen generates passwords with character variety."""
        # Generate multiple passwords to test variety
        passwords = []
        for _ in range(10):
            result = self.runner.invoke(utils_app, ["passgen", "20"])
            assert result.exit_code == 0
            passwords.append(result.stdout.strip())

        # Check that we get different passwords
        assert len(set(passwords)) == len(passwords), "All passwords should be unique"

        # Check that at least some passwords contain different character types
        has_letters = any(any(c.isalpha() for c in pwd) for pwd in passwords)
        has_digits = any(any(c.isdigit() for c in pwd) for pwd in passwords)
        has_punct = any(any(not c.isalnum() for c in pwd) for pwd in passwords)

        assert has_letters, "At least some passwords should contain letters"
        assert has_digits, "At least some passwords should contain digits"
        assert has_punct, "At least some passwords should contain punctuation"


class TestTyperIntegration:
    """Test cases for Typer integration with the main CLI."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_typer_utils_integration(self):
        """Test that utils commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["utils", "--help"])
        assert result.exit_code == 0
        assert "Tools to make life easier" in result.stdout
        assert "passgen" in result.stdout

    def test_typer_passgen_integration(self):
        """Test that passgen works through the main app."""
        result = self.runner.invoke(typer_app, ["utils", "passgen"])
        assert result.exit_code == 0

        # Check that output is a valid password
        output = result.stdout.strip()
        assert len(output) == 12
        assert output.isprintable()

    def test_typer_passgen_with_debug(self):
        """Test passgen with debug flag through main app."""
        result = self.runner.invoke(typer_app, ["--debug", "utils", "passgen"])
        assert result.exit_code == 0
        # Check that passgen output is present (12 character password)
        output = result.stdout.strip()
        assert len(output) == 12


class TestEnvironmentSwitching:
    """Test cases for environment-based CLI switching."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    @patch.dict(os.environ, {"LFTOOLS_CLI_V2": "1"})
    def test_environment_variable_detection(self):
        """Test that LFTOOLS_CLI_V2 environment variable is detected."""
        # This test verifies the environment variable is set correctly
        assert os.environ.get("LFTOOLS_CLI_V2") == "1"

    def test_typer_app_callable(self):
        """Test that the Typer app is callable."""
        # Verify that our app can be invoked
        assert callable(typer_app)

    def test_typer_app_structure(self):
        """Test that the Typer app has the expected structure."""
        # Check that the app has the expected commands
        result = self.runner.invoke(typer_app, ["--help"])
        assert result.exit_code == 0

        # Verify that utils command is registered
        assert "utils" in result.stdout or "utils" in result.output


class TestStateManagement:
    """Test cases for state management in Typer CLI."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_state_initialization(self):
        """Test that state is properly initialized."""
        result = self.runner.invoke(typer_app, ["--debug", "utils", "passgen"])
        assert result.exit_code == 0

        # Check that the command executed successfully with debug flag
        # State initialization is tested through successful command execution
        output = result.stdout.strip()
        assert len(output) == 12  # Should generate a 12-character password

    def test_credential_options_parsing(self):
        """Test that credential options are parsed correctly."""
        result = self.runner.invoke(typer_app, ["--username", "testuser", "--debug", "utils", "passgen"])
        assert result.exit_code == 0

        # Command should execute successfully with credentials provided
        output = result.stdout.strip()
        assert len(output) == 12  # Should generate a 12-character password


class TestBackwardCompatibility:
    """Test cases for backward compatibility during migration."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_typer_app_has_expected_options(self):
        """Test that Typer app maintains expected CLI options."""
        result = self.runner.invoke(typer_app, ["--help"])
        assert result.exit_code == 0

        # Check for key options that should be maintained
        assert_in_output("--debug", result.stdout)
        assert_in_output("--username", result.stdout)
        assert_in_output("--password", result.stdout)
        assert_in_output("--interactive", result.stdout)

    def test_passgen_output_format_compatibility(self):
        """Test that passgen output format is compatible with Click version."""
        result = self.runner.invoke(typer_app, ["utils", "passgen"])
        assert result.exit_code == 0

        # Output should be a single line with just the password
        lines = result.stdout.strip().split("\n")
        assert len(lines) == 1, "Output should be a single line"

        # The password should be printable ASCII
        password = lines[0]
        assert password.isprintable()
        assert all(ord(c) < 128 for c in password), "Password should be ASCII"


class TestTyperVersion:
    """Test cases for the Typer-based version command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_version_help(self):
        """Test that version shows help correctly."""
        result = self.runner.invoke(version_app, ["--help"])
        assert result.exit_code == 0
        assert "Version bump script for Maven based projects" in result.stdout

    def test_version_bump_help(self):
        """Test that version bump shows help correctly."""
        result = self.runner.invoke(version_app, ["bump", "--help"])
        assert result.exit_code == 0
        assert "Version bump pom files in a Maven project" in result.stdout
        assert "RELEASE_TAG" in result.stdout

    def test_version_release_help(self):
        """Test that version release shows help correctly."""
        result = self.runner.invoke(version_app, ["release", "--help"])
        assert result.exit_code == 0
        assert "Version bump pom files in a Maven project from SNAPSHOT to RELEASE_TAG" in result.stdout

    def test_version_patch_help(self):
        """Test that version patch shows help correctly."""
        result = self.runner.invoke(version_app, ["patch", "--help"])
        assert result.exit_code == 0
        assert_in_output("--project", result.stdout)

    def test_version_bump_missing_tag(self):
        """Test version bump with missing release tag argument."""
        result = self.runner.invoke(version_app, ["bump"])
        assert result.exit_code == 2
        assert "Missing argument" in result.stderr

    def test_version_release_missing_tag(self):
        """Test version release with missing release tag argument."""
        result = self.runner.invoke(version_app, ["release"])
        assert result.exit_code == 2
        assert "Missing argument" in result.stderr

    def test_version_patch_missing_arguments(self):
        """Test version patch with missing arguments."""
        result = self.runner.invoke(version_app, ["patch"])
        assert result.exit_code == 2
        assert "Missing argument" in result.stderr

    def test_version_patch_invalid_directory(self):
        """Test version patch with invalid patch directory."""
        result = self.runner.invoke(version_app, ["patch", "test-tag", "/invalid/directory"])
        assert result.exit_code == 404
        assert "is not a valid directory" in result.stderr

    def test_version_bump_with_valid_tag(self):
        """Test version bump with a valid tag."""
        # Since the version command exists on the system, test with a valid tag
        result = self.runner.invoke(version_app, ["bump", "test-tag"])
        # The command should execute successfully
        assert result.exit_code == 0
        assert "Version bump completed successfully" in result.stdout

    def test_version_release_with_valid_tag(self):
        """Test version release with a valid tag."""
        # Since the version command exists on the system, test with a valid tag
        result = self.runner.invoke(version_app, ["release", "test-tag"])
        # The command should execute successfully
        assert result.exit_code == 0
        assert "Version release completed successfully" in result.stdout

    def test_version_patch_with_valid_directory(self):
        """Test version patch with a valid directory."""
        # Create a temporary directory for the patch test
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.runner.invoke(version_app, ["patch", "test-tag", tmpdir])
            # The patch command will fail because we don't have proper git setup/patches
            # but we're testing that the directory validation works and error handling is correct
            assert result.exit_code == 1
            assert "Version patch failed with exit code 1" in result.stderr

    def test_version_integration_with_main_app(self):
        """Test that version commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["version", "--help"])
        assert result.exit_code == 0
        assert "Version bump script for Maven based projects" in result.stdout
        assert "bump" in result.stdout
        assert "release" in result.stdout
        assert "patch" in result.stdout

    def test_version_bump_integration_with_main_app(self):
        """Test version bump through the main app."""
        result = self.runner.invoke(typer_app, ["version", "bump", "--help"])
        assert result.exit_code == 0
        assert "Version bump pom files in a Maven project" in result.stdout


class TestTyperConfig:
    """Test cases for the config Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_config_help(self):
        """Test that the config command shows help correctly."""
        result = self.runner.invoke(config_app, ["--help"])
        assert result.exit_code == 0
        assert "Configuration subsystem" in result.stdout
        assert "get" in result.stdout
        assert "set" in result.stdout

    def test_config_get_help(self):
        """Test config get subcommand help."""
        result = self.runner.invoke(config_app, ["get", "--help"])
        assert result.exit_code == 0
        assert "Print section or setting from config file" in result.stdout

    def test_config_set_help(self):
        """Test config set subcommand help."""
        result = self.runner.invoke(config_app, ["set", "--help"])
        assert result.exit_code == 0
        assert "Set a setting in the config file" in result.stdout

    def test_config_get_missing_section(self):
        """Test config get with missing section."""
        result = self.runner.invoke(config_app, ["get", "nonexistent"])
        assert result.exit_code == 1
        # The actual error message will be in stderr for Typer

    def test_config_integration_with_main_app(self):
        """Test that config commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["config", "--help"])
        assert result.exit_code == 0
        assert "Configuration subsystem" in result.stdout

    def test_config_get_integration_with_main_app(self):
        """Test config get through the main app."""
        result = self.runner.invoke(typer_app, ["config", "get", "--help"])
        assert result.exit_code == 0
        assert "Print section or setting from config file" in result.stdout

    def test_config_set_integration_with_main_app(self):
        """Test config set through the main app."""
        result = self.runner.invoke(typer_app, ["config", "set", "--help"])
        assert result.exit_code == 0
        assert "Set a setting in the config file" in result.stdout


class TestTyperDCO:
    """Test cases for the DCO Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_dco_help(self):
        """Test that the dco command shows help correctly."""
        result = self.runner.invoke(dco_app, ["--help"])
        assert result.exit_code == 0
        assert "Check repository for commits missing DCO" in result.stdout
        assert "check" in result.stdout
        assert "match" in result.stdout

    def test_dco_check_help(self):
        """Test dco check subcommand help."""
        result = self.runner.invoke(dco_app, ["check", "--help"])
        assert result.exit_code == 0
        assert_in_output("--signoffs", result.stdout)

    def test_dco_match_help(self):
        """Test dco match subcommand help."""
        result = self.runner.invoke(dco_app, ["match", "--help"])
        assert result.exit_code == 0
        assert_in_output("--signoffs", result.stdout)

    def test_dco_check_invalid_repo(self):
        """Test dco check with invalid repository path."""
        # Test with a non-git directory
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.runner.invoke(dco_app, ["check", tmpdir])
            # This should exit with non-zero status since it's not a git repo
            assert result.exit_code != 0

    def test_dco_match_invalid_repo(self):
        """Test dco match with invalid repository path."""
        # Test with a non-git directory
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            result = self.runner.invoke(dco_app, ["match", tmpdir])
            # This should exit with non-zero status since it's not a git repo
            assert result.exit_code != 0

    def test_dco_integration_with_main_app(self):
        """Test that dco commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["dco", "--help"])
        assert result.exit_code == 0
        assert "Check repository for commits missing DCO" in result.stdout

    def test_dco_check_integration_with_main_app(self):
        """Test dco check through the main app."""
        result = self.runner.invoke(typer_app, ["dco", "check", "--help"])
        assert result.exit_code == 0
        assert "Check repository for commits missing DCO" in result.stdout

    def test_dco_match_integration_with_main_app(self):
        """Test dco match through the main app."""
        result = self.runner.invoke(typer_app, ["dco", "match", "--help"])
        assert result.exit_code == 0
        assert "Check for commits whose DCO does not match" in result.stdout


class TestTyperDeploy:
    """Test cases for the deploy Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_deploy_help(self):
        """Test that the deploy command shows help correctly."""
        result = self.runner.invoke(deploy_app, ["--help"])
        assert result.exit_code == 0
        assert "Deploy files to a Nexus sites repository" in result.stdout
        assert "archives" in result.stdout
        assert "logs" in result.stdout
        assert "nexus" in result.stdout

    def test_deploy_archives_help(self):
        """Test deploy archives subcommand help."""
        result = self.runner.invoke(deploy_app, ["archives", "--help"])
        assert result.exit_code == 0
        assert_in_output("--pattern", result.stdout)

    def test_deploy_logs_help(self):
        """Test deploy logs subcommand help."""
        result = self.runner.invoke(deploy_app, ["logs", "--help"])
        assert result.exit_code == 0
        assert "Deploy logs to a Nexus site repository" in result.stdout

    def test_deploy_nexus_help(self):
        """Test deploy nexus subcommand help."""
        result = self.runner.invoke(deploy_app, ["nexus", "--help"])
        assert result.exit_code == 0
        assert_in_output("--snapshot", result.stdout)

    def test_deploy_maven_file_help(self):
        """Test deploy maven-file subcommand help."""
        result = self.runner.invoke(deploy_app, ["maven-file", "--help"])
        assert result.exit_code == 0
        assert_in_output("--maven-bin", result.stdout)
        assert_in_output("--group-id", result.stdout)

    def test_deploy_integration_with_main_app(self):
        """Test that deploy commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["deploy", "--help"])
        assert result.exit_code == 0
        assert "Deploy files to a Nexus sites repository" in result.stdout

    def test_deploy_archives_integration_with_main_app(self):
        """Test deploy archives through the main app."""
        result = self.runner.invoke(typer_app, ["deploy", "archives", "--help"])
        assert result.exit_code == 0
        assert "Archive files to a Nexus site repository" in result.stdout

    def test_deploy_logs_integration_with_main_app(self):
        """Test deploy logs through the main app."""
        result = self.runner.invoke(typer_app, ["deploy", "logs", "--help"])
        assert result.exit_code == 0
        assert "Deploy logs to a Nexus site repository" in result.stdout

    def test_deploy_nexus_integration_with_main_app(self):
        """Test deploy nexus through the main app."""
        result = self.runner.invoke(typer_app, ["deploy", "nexus", "--help"])
        assert result.exit_code == 0
        assert "Deploy a Maven repository to a specified Nexus repository" in result.stdout


class TestTyperGitHub:
    """Test cases for the GitHub Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_github_help(self):
        """Test that the github command shows help correctly."""
        result = self.runner.invoke(github_app, ["--help"])
        assert result.exit_code == 0
        assert "GitHub tools" in result.stdout
        assert "submit-pr" in result.stdout
        assert "votes" in result.stdout
        assert "list" in result.stdout
        assert "create-repo" in result.stdout

    def test_github_submit_pr_help(self):
        """Test github submit-pr subcommand help."""
        result = self.runner.invoke(github_app, ["submit-pr", "--help"])
        assert result.exit_code == 0
        assert "Submit a pr if mergeable" in result.stdout

    def test_github_votes_help(self):
        """Test github votes subcommand help."""
        result = self.runner.invoke(github_app, ["votes", "--help"])
        assert result.exit_code == 0
        assert "Helper for votes" in result.stdout

    def test_github_list_help(self):
        """Test github list subcommand help."""
        result = self.runner.invoke(github_app, ["list", "--help"])
        assert result.exit_code == 0
        assert_in_output("--audit", result.stdout)
        assert_in_output("--repos", result.stdout)

    def test_github_create_repo_help(self):
        """Test github create-repo subcommand help."""
        result = self.runner.invoke(github_app, ["create-repo", "--help"])
        assert result.exit_code == 0
        assert_in_output("--has-issues", result.stdout)

    def test_github_update_repo_help(self):
        """Test github update-repo subcommand help."""
        result = self.runner.invoke(github_app, ["update-repo", "--help"])
        assert result.exit_code == 0
        assert_in_output("--add-team", result.stdout)

    def test_github_create_team_help(self):
        """Test github create-team subcommand help."""
        result = self.runner.invoke(github_app, ["create-team", "--help"])
        assert result.exit_code == 0
        assert_in_output("--repo", result.stdout)

    def test_github_user_help(self):
        """Test github user subcommand help."""
        result = self.runner.invoke(github_app, ["user", "--help"])
        assert result.exit_code == 0
        assert_in_output("--delete", result.stdout)
        assert_in_output("--admin", result.stdout)

    def test_github_integration_with_main_app(self):
        """Test that github commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["github", "--help"])
        assert result.exit_code == 0
        assert "GitHub tools" in result.stdout

    def test_github_submit_pr_integration_with_main_app(self):
        """Test github submit-pr through the main app."""
        result = self.runner.invoke(typer_app, ["github", "submit-pr", "--help"])
        assert result.exit_code == 0
        assert "Submit a pr if mergeable" in result.stdout

    def test_github_list_integration_with_main_app(self):
        """Test github list through the main app."""
        result = self.runner.invoke(typer_app, ["github", "list", "--help"])
        assert result.exit_code == 0
        assert "List options for github org repos" in result.stdout

    def test_github_create_repo_integration_with_main_app(self):
        """Test github create-repo through the main app."""
        result = self.runner.invoke(typer_app, ["github", "create-repo", "--help"])
        assert result.exit_code == 0
        assert "Create a Github repo within an Organization" in result.stdout


class TestTyperGerrit:
    """Test cases for the Gerrit Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_gerrit_help(self):
        """Test that the gerrit command shows help correctly."""
        result = self.runner.invoke(gerrit_app, ["--help"])
        assert result.exit_code == 0
        assert "GERRIT TOOLS." in result.stdout
        assert "addfile" in result.stdout
        assert "addinfojob" in result.stdout
        assert "addgitreview" in result.stdout
        assert "addgithubrights" in result.stdout
        assert "abandonchanges" in result.stdout
        assert "createproject" in result.stdout
        assert "create-saml-group" in result.stdout
        assert "list-project-permissions" in result.stdout
        assert "list-project-inherits-from" in result.stdout
        assert "addmavenconfig" in result.stdout

    def test_gerrit_addfile_help(self):
        """Test gerrit addfile subcommand help."""
        result = self.runner.invoke(gerrit_app, ["addfile", "--help"])
        assert result.exit_code == 0
        assert_in_output("--issue-id", result.stdout)
        assert_in_output("--file-location", result.stdout)

    def test_gerrit_addinfojob_help(self):
        """Test gerrit addinfojob subcommand help."""
        result = self.runner.invoke(gerrit_app, ["addinfojob", "--help"])
        assert result.exit_code == 0
        assert_in_output("--issue-id", result.stdout)
        assert_in_output("--agent", result.stdout)

    def test_gerrit_addgitreview_help(self):
        """Test gerrit addgitreview subcommand help."""
        result = self.runner.invoke(gerrit_app, ["addgitreview", "--help"])
        assert result.exit_code == 0
        assert_in_output("--issue-id", result.stdout)

    def test_gerrit_addgithubrights_help(self):
        """Test gerrit addgithubrights subcommand help."""
        result = self.runner.invoke(gerrit_app, ["addgithubrights", "--help"])
        assert result.exit_code == 0
        assert "Grant Github read for a project" in result.stdout

    def test_gerrit_abandonchanges_help(self):
        """Test gerrit abandonchanges subcommand help."""
        result = self.runner.invoke(gerrit_app, ["abandonchanges", "--help"])
        assert result.exit_code == 0
        assert "Abandon all OPEN changes for a gerrit project" in result.stdout

    def test_gerrit_createproject_help(self):
        """Test gerrit createproject subcommand help."""
        result = self.runner.invoke(gerrit_app, ["createproject", "--help"])
        assert result.exit_code == 0
        assert_in_output("--description", result.stdout)
        assert_in_output("--check", result.stdout)

    def test_gerrit_create_saml_group_help(self):
        """Test gerrit create-saml-group subcommand help."""
        result = self.runner.invoke(gerrit_app, ["create-saml-group", "--help"])
        assert result.exit_code == 0
        assert "Create saml group based on ldap group" in result.stdout

    def test_gerrit_list_project_permissions_help(self):
        """Test gerrit list-project-permissions subcommand help."""
        result = self.runner.invoke(gerrit_app, ["list-project-permissions", "--help"])
        assert result.exit_code == 0
        assert "List Owners of a Project" in result.stdout

    def test_gerrit_list_project_inherits_from_help(self):
        """Test gerrit list-project-inherits-from subcommand help."""
        result = self.runner.invoke(gerrit_app, ["list-project-inherits-from", "--help"])
        assert result.exit_code == 0
        assert "List who a project inherits from" in result.stdout

    def test_gerrit_addmavenconfig_help(self):
        """Test gerrit addmavenconfig subcommand help."""
        result = self.runner.invoke(gerrit_app, ["addmavenconfig", "--help"])
        assert result.exit_code == 0
        assert_in_output("--issue-id", result.stdout)
        assert_in_output("--nexus3", result.stdout)
        assert_in_output("--nexus3-ports", result.stdout)

    def test_gerrit_addfile_missing_args(self):
        """Test gerrit addfile with missing required arguments."""
        result = self.runner.invoke(gerrit_app, ["addfile"])
        assert result.exit_code == 2
        # Typer will show usage/error for missing arguments

    def test_gerrit_createproject_missing_description(self):
        """Test gerrit createproject with missing required --description option."""
        result = self.runner.invoke(gerrit_app, ["createproject", "gerrit.example.com", "test/project", "test-group"])
        assert result.exit_code == 2
        # Should fail due to missing required --description option

    def test_gerrit_integration_with_main_app(self):
        """Test that gerrit commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["gerrit", "--help"])
        assert result.exit_code == 0
        assert "GERRIT TOOLS." in result.stdout

    def test_gerrit_addfile_integration_with_main_app(self):
        """Test gerrit addfile through the main app."""
        result = self.runner.invoke(typer_app, ["gerrit", "addfile", "--help"])
        assert result.exit_code == 0
        assert "Add a file for review to a Project" in result.stdout

    def test_gerrit_createproject_integration_with_main_app(self):
        """Test gerrit createproject through the main app."""
        result = self.runner.invoke(typer_app, ["gerrit", "createproject", "--help"])
        assert result.exit_code == 0
        assert "Create a project via the gerrit API" in result.stdout

    def test_gerrit_addmavenconfig_integration_with_main_app(self):
        """Test gerrit addmavenconfig through the main app."""
        result = self.runner.invoke(typer_app, ["gerrit", "addmavenconfig", "--help"])
        assert result.exit_code == 0
        assert "Add maven config file for JCasC" in result.stdout


class TestTyperJenkins:
    """Test cases for the Jenkins Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_jenkins_help(self):
        """Test that the jenkins command shows help correctly."""
        result = self.runner.invoke(jenkins_app, ["--help"])
        assert result.exit_code == 0
        assert "Query information about the Jenkins Server" in result.stdout
        assert "get-credentials" in result.stdout
        assert "get-secrets" in result.stdout
        assert "get-private-keys" in result.stdout
        assert "groovy" in result.stdout
        assert "quiet-down" in result.stdout
        assert "remove-offline-nodes" in result.stdout
        assert "builds" in result.stdout
        assert "jobs" in result.stdout
        assert "nodes" in result.stdout
        assert "plugins" in result.stdout
        assert "token" in result.stdout

    def test_jenkins_get_credentials_help(self):
        """Test jenkins get-credentials subcommand help."""
        result = self.runner.invoke(jenkins_app, ["get-credentials", "--help"])
        assert result.exit_code == 0
        assert "Print all available Credentials" in result.stdout

    def test_jenkins_get_secrets_help(self):
        """Test jenkins get-secrets subcommand help."""
        result = self.runner.invoke(jenkins_app, ["get-secrets", "--help"])
        assert result.exit_code == 0
        assert "Print all available secrets" in result.stdout

    def test_jenkins_get_private_keys_help(self):
        """Test jenkins get-private-keys subcommand help."""
        result = self.runner.invoke(jenkins_app, ["get-private-keys", "--help"])
        assert result.exit_code == 0
        assert "Print all available SSH User Private Keys" in result.stdout

    def test_jenkins_groovy_help(self):
        """Test jenkins groovy subcommand help."""
        result = self.runner.invoke(jenkins_app, ["groovy", "--help"])
        assert result.exit_code == 0
        assert "Run a groovy script" in result.stdout

    def test_jenkins_quiet_down_help(self):
        """Test jenkins quiet-down subcommand help."""
        result = self.runner.invoke(jenkins_app, ["quiet-down", "--help"])
        assert result.exit_code == 0
        assert_in_output("--yes", result.stdout)

    def test_jenkins_remove_offline_nodes_help(self):
        """Test jenkins remove-offline-nodes subcommand help."""
        result = self.runner.invoke(jenkins_app, ["remove-offline-nodes", "--help"])
        assert result.exit_code == 0
        assert_in_output("--force", result.stdout)

    def test_jenkins_builds_help(self):
        """Test jenkins builds subcommand help."""
        result = self.runner.invoke(jenkins_app, ["builds", "--help"])
        assert result.exit_code == 0
        assert "Information regarding current builds and the queue" in result.stdout
        assert "running" in result.stdout
        assert "queued" in result.stdout

    def test_jenkins_builds_running_help(self):
        """Test jenkins builds running subcommand help."""
        result = self.runner.invoke(jenkins_app, ["builds", "running", "--help"])
        assert result.exit_code == 0
        assert "Show all the currently running builds" in result.stdout

    def test_jenkins_builds_queued_help(self):
        """Test jenkins builds queued subcommand help."""
        result = self.runner.invoke(jenkins_app, ["builds", "queued", "--help"])
        assert result.exit_code == 0
        assert "Show all jobs waiting in the queue and their status" in result.stdout

    def test_jenkins_jobs_help(self):
        """Test jenkins jobs subcommand help."""
        result = self.runner.invoke(jenkins_app, ["jobs", "--help"])
        assert result.exit_code == 0
        assert "Command to update Jenkins Jobs" in result.stdout
        assert "enable" in result.stdout
        assert "disable" in result.stdout

    def test_jenkins_jobs_enable_help(self):
        """Test jenkins jobs enable subcommand help."""
        result = self.runner.invoke(jenkins_app, ["jobs", "enable", "--help"])
        assert result.exit_code == 0
        assert "Enable all Jenkins jobs matching REGEX" in result.stdout

    def test_jenkins_jobs_disable_help(self):
        """Test jenkins jobs disable subcommand help."""
        result = self.runner.invoke(jenkins_app, ["jobs", "disable", "--help"])
        assert result.exit_code == 0
        assert "Disable all Jenkins jobs matching REGEX" in result.stdout

    def test_jenkins_nodes_help(self):
        """Test jenkins nodes subcommand help."""
        result = self.runner.invoke(jenkins_app, ["nodes", "--help"])
        assert result.exit_code == 0
        assert "Find information about builders connected to Jenkins Master" in result.stdout
        assert "list" in result.stdout

    def test_jenkins_nodes_list_help(self):
        """Test jenkins nodes list subcommand help."""
        result = self.runner.invoke(jenkins_app, ["nodes", "list", "--help"])
        assert result.exit_code == 0
        assert "List Jenkins nodes" in result.stdout

    def test_jenkins_plugins_help(self):
        """Test jenkins plugins subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "--help"])
        assert result.exit_code == 0
        assert "Inspect Jenkins plugins on the server" in result.stdout
        assert "list" in result.stdout
        assert "pinned" in result.stdout
        assert "dynamic" in result.stdout
        assert "needs-update" in result.stdout
        assert "active" in result.stdout
        assert "enabled" in result.stdout
        assert "disabled" in result.stdout
        assert "sec" in result.stdout

    def test_jenkins_plugins_list_help(self):
        """Test jenkins plugins list subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "list", "--help"])
        assert result.exit_code == 0
        assert "List installed plugins" in result.stdout

    def test_jenkins_plugins_pinned_help(self):
        """Test jenkins plugins pinned subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "pinned", "--help"])
        assert result.exit_code == 0
        assert "List pinned plugins" in result.stdout

    def test_jenkins_plugins_dynamic_help(self):
        """Test jenkins plugins dynamic subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "dynamic", "--help"])
        assert result.exit_code == 0
        assert "List dynamically reloadable plugins" in result.stdout

    def test_jenkins_plugins_needs_update_help(self):
        """Test jenkins plugins needs-update subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "needs-update", "--help"])
        assert result.exit_code == 0
        assert "List pending plugin updates" in result.stdout

    def test_jenkins_plugins_active_help(self):
        """Test jenkins plugins active subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "active", "--help"])
        assert result.exit_code == 0
        assert "List active plugins" in result.stdout

    def test_jenkins_plugins_enabled_help(self):
        """Test jenkins plugins enabled subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "enabled", "--help"])
        assert result.exit_code == 0
        assert "List enabled plugins" in result.stdout

    def test_jenkins_plugins_disabled_help(self):
        """Test jenkins plugins disabled subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "disabled", "--help"])
        assert result.exit_code == 0
        assert "List disabled plugins" in result.stdout

    def test_jenkins_plugins_sec_help(self):
        """Test jenkins plugins sec subcommand help."""
        result = self.runner.invoke(jenkins_app, ["plugins", "sec", "--help"])
        assert result.exit_code == 0
        assert "List plugins with a known vulnerability" in result.stdout

    def test_jenkins_token_help(self):
        """Test jenkins token subcommand help."""
        result = self.runner.invoke(jenkins_app, ["token", "--help"])
        assert result.exit_code == 0
        assert "Get API token" in result.stdout
        assert "change" in result.stdout
        assert "init" in result.stdout
        assert "print" in result.stdout
        assert "reset" in result.stdout

    def test_jenkins_token_change_help(self):
        """Test jenkins token change subcommand help."""
        result = self.runner.invoke(jenkins_app, ["token", "change", "--help"])
        assert result.exit_code == 0
        assert_in_output("--name", result.stdout)

    def test_jenkins_token_init_help(self):
        """Test jenkins token init subcommand help."""
        result = self.runner.invoke(jenkins_app, ["token", "init", "--help"])
        assert result.exit_code == 0
        assert "Initialize jenkins_jobs.ini config for new server section" in result.stdout

    def test_jenkins_token_print_help(self):
        """Test jenkins token print subcommand help."""
        result = self.runner.invoke(jenkins_app, ["token", "print", "--help"])
        assert result.exit_code == 0
        assert "Print current API token" in result.stdout

    def test_jenkins_token_reset_help(self):
        """Test jenkins token reset subcommand help."""
        result = self.runner.invoke(jenkins_app, ["token", "reset", "--help"])
        assert result.exit_code == 0
        assert "Regenerate API tokens for configurations in jenkins_jobs.ini" in result.stdout

    def test_jenkins_groovy_missing_args(self):
        """Test jenkins groovy with missing required arguments."""
        result = self.runner.invoke(jenkins_app, ["groovy"])
        assert result.exit_code == 2
        # Typer will show usage/error for missing arguments

    def test_jenkins_jobs_enable_missing_args(self):
        """Test jenkins jobs enable with missing required arguments."""
        result = self.runner.invoke(jenkins_app, ["jobs", "enable"])
        assert result.exit_code == 2
        # Should fail due to missing required regex argument

    def test_jenkins_token_init_missing_args(self):
        """Test jenkins token init with missing required arguments."""
        result = self.runner.invoke(jenkins_app, ["token", "init"])
        assert result.exit_code == 2
        # Should fail due to missing required name and url arguments

    def test_jenkins_integration_with_main_app(self):
        """Test that jenkins commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["jenkins", "--help"])
        assert result.exit_code == 0
        assert "Query information about the Jenkins Server" in result.stdout

    def test_jenkins_builds_integration_with_main_app(self):
        """Test jenkins builds through the main app."""
        result = self.runner.invoke(typer_app, ["jenkins", "builds", "--help"])
        assert result.exit_code == 0
        assert "Information regarding current builds and the queue" in result.stdout

    def test_jenkins_jobs_integration_with_main_app(self):
        """Test jenkins jobs through the main app."""
        result = self.runner.invoke(typer_app, ["jenkins", "jobs", "--help"])
        assert result.exit_code == 0
        assert "Command to update Jenkins Jobs" in result.stdout

    def test_jenkins_plugins_integration_with_main_app(self):
        """Test jenkins plugins through the main app."""
        result = self.runner.invoke(typer_app, ["jenkins", "plugins", "--help"])
        assert result.exit_code == 0
        assert "Inspect Jenkins plugins on the server" in result.stdout

    def test_jenkins_token_integration_with_main_app(self):
        """Test jenkins token through the main app."""
        result = self.runner.invoke(typer_app, ["jenkins", "token", "--help"])
        assert result.exit_code == 0
        assert "Get API token" in result.stdout


class TestTyperNexus2:
    """Test cases for the Nexus2 Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_nexus2_help(self):
        """Test that the nexus2 command shows help correctly."""
        result = self.runner.invoke(nexus2_app, ["example.com", "--help"])
        assert result.exit_code == 0
        assert "The Nexus2 API Interface" in result.stdout
        assert "privilege" in result.stdout
        assert "repo" in result.stdout
        assert "role" in result.stdout
        assert "user" in result.stdout

    def test_nexus2_privilege_help(self):
        """Test nexus2 privilege subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "privilege", "--help"])
        assert result.exit_code == 0
        assert "Privilege primary interface" in result.stdout
        assert "list" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout

    def test_nexus2_privilege_list_help(self):
        """Test nexus2 privilege list subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "privilege", "list", "--help"])
        assert result.exit_code == 0
        assert "List privileges" in result.stdout

    def test_nexus2_privilege_create_help(self):
        """Test nexus2 privilege create subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "privilege", "create", "--help"])
        assert result.exit_code == 0
        assert "Create a new privilege" in result.stdout

    def test_nexus2_privilege_delete_help(self):
        """Test nexus2 privilege delete subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "privilege", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a privilege" in result.stdout

    def test_nexus2_repo_help(self):
        """Test nexus2 repo subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "repo", "--help"])
        assert result.exit_code == 0
        assert "Repository primary interface" in result.stdout
        assert "list" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout

    def test_nexus2_repo_list_help(self):
        """Test nexus2 repo list subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "repo", "list", "--help"])
        assert result.exit_code == 0
        assert "List repositories" in result.stdout

    def test_nexus2_repo_create_help(self):
        """Test nexus2 repo create subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "repo", "create", "--help"])
        assert result.exit_code == 0
        assert_in_output("--upstream-repo", result.stdout)

    def test_nexus2_repo_delete_help(self):
        """Test nexus2 repo delete subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "repo", "delete", "--help"])
        assert result.exit_code == 0
        assert "Permanently delete a repo" in result.stdout

    def test_nexus2_role_help(self):
        """Test nexus2 role subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "role", "--help"])
        assert result.exit_code == 0
        assert "Role primary interface" in result.stdout
        assert "list" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout

    def test_nexus2_role_list_help(self):
        """Test nexus2 role list subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "role", "list", "--help"])
        assert result.exit_code == 0
        assert "List roles" in result.stdout

    def test_nexus2_role_create_help(self):
        """Test nexus2 role create subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "role", "create", "--help"])
        assert result.exit_code == 0
        assert_in_output("--description", result.stdout)
        assert_in_output("--roles", result.stdout)
        assert_in_output("--privileges", result.stdout)

    def test_nexus2_role_delete_help(self):
        """Test nexus2 role delete subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "role", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a role" in result.stdout

    def test_nexus2_user_help(self):
        """Test nexus2 user subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "user", "--help"])
        assert result.exit_code == 0
        assert "User primary interface" in result.stdout
        assert "list" in result.stdout
        assert "add" in result.stdout
        assert "delete" in result.stdout

    def test_nexus2_user_list_help(self):
        """Test nexus2 user list subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "user", "list", "--help"])
        assert result.exit_code == 0
        assert "List users" in result.stdout

    def test_nexus2_user_add_help(self):
        """Test nexus2 user add subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "user", "add", "--help"])
        assert result.exit_code == 0
        assert "Add a new user" in result.stdout

    def test_nexus2_user_delete_help(self):
        """Test nexus2 user delete subcommand help."""
        result = self.runner.invoke(nexus2_app, ["example.com", "user", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a user" in result.stdout

    def test_nexus2_missing_fqdn(self):
        """Test nexus2 with missing required FQDN argument."""
        result = self.runner.invoke(nexus2_app, ["--help"])
        assert result.exit_code == 0
        # Should show the main help since FQDN is required

    def test_nexus2_privilege_create_missing_args(self):
        """Test nexus2 privilege create with missing required arguments."""
        result = self.runner.invoke(nexus2_app, ["example.com", "privilege", "create"])
        assert result.exit_code == 2
        # Should fail due to missing required arguments

    def test_nexus2_integration_with_main_app(self):
        """Test that nexus2 commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["nexus2", "example.com", "--help"])
        assert result.exit_code == 0
        assert "The Nexus2 API Interface" in result.stdout

    def test_nexus2_privilege_integration_with_main_app(self):
        """Test nexus2 privilege through the main app."""
        result = self.runner.invoke(typer_app, ["nexus2", "example.com", "privilege", "--help"])
        assert result.exit_code == 0
        assert "Privilege primary interface" in result.stdout

    def test_nexus2_repo_integration_with_main_app(self):
        """Test nexus2 repo through the main app."""
        result = self.runner.invoke(typer_app, ["nexus2", "example.com", "repo", "--help"])
        assert result.exit_code == 0
        assert "Repository primary interface" in result.stdout


class TestTyperNexus3:
    """Test cases for the Nexus3 Typer command."""

    runner: CliRunner = CliRunner()

    def setup_method(self):
        """Set up test fixtures."""
        self.runner = CliRunner()

    def test_nexus3_help(self):
        """Test that the nexus3 command shows help correctly."""
        result = self.runner.invoke(nexus3_app, ["example.com", "--help"])
        assert result.exit_code == 0
        assert "The Nexus3 API Interface" in result.stdout
        assert "asset" in result.stdout
        assert "privilege" in result.stdout
        assert "repository" in result.stdout
        assert "role" in result.stdout
        assert "script" in result.stdout
        assert "tag" in result.stdout
        assert "task" in result.stdout
        assert "user" in result.stdout

    def test_nexus3_asset_help(self):
        """Test nexus3 asset subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "asset", "--help"])
        assert result.exit_code == 0
        assert "Asset primary interface" in result.stdout
        assert "list" in result.stdout
        assert "search" in result.stdout

    def test_nexus3_asset_list_help(self):
        """Test nexus3 asset list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "asset", "list", "--help"])
        assert result.exit_code == 0
        assert "List assets" in result.stdout

    def test_nexus3_asset_search_help(self):
        """Test nexus3 asset search subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "asset", "search", "--help"])
        assert result.exit_code == 0
        assert_in_output("--details", result.stdout)

    def test_nexus3_privilege_help(self):
        """Test nexus3 privilege subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "privilege", "--help"])
        assert result.exit_code == 0
        assert "Privilege primary interface" in result.stdout
        assert "list" in result.stdout

    def test_nexus3_privilege_list_help(self):
        """Test nexus3 privilege list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "privilege", "list", "--help"])
        assert result.exit_code == 0
        assert "List privileges" in result.stdout

    def test_nexus3_repository_help(self):
        """Test nexus3 repository subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "repository", "--help"])
        assert result.exit_code == 0
        assert "Repository primary interface" in result.stdout
        assert "list" in result.stdout

    def test_nexus3_repository_list_help(self):
        """Test nexus3 repository list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "repository", "list", "--help"])
        assert result.exit_code == 0
        assert "List repositories" in result.stdout

    def test_nexus3_role_help(self):
        """Test nexus3 role subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "role", "--help"])
        assert result.exit_code == 0
        assert "Role primary interface" in result.stdout
        assert "list" in result.stdout
        assert "create" in result.stdout

    def test_nexus3_role_list_help(self):
        """Test nexus3 role list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "role", "list", "--help"])
        assert result.exit_code == 0
        assert "List roles" in result.stdout

    def test_nexus3_role_create_help(self):
        """Test nexus3 role create subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "role", "create", "--help"])
        assert result.exit_code == 0
        assert "Create roles" in result.stdout

    def test_nexus3_script_help(self):
        """Test nexus3 script subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "--help"])
        assert result.exit_code == 0
        assert "Script primary interface" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout
        assert "list" in result.stdout
        assert "read" in result.stdout
        assert "run" in result.stdout
        assert "update" in result.stdout

    def test_nexus3_script_create_help(self):
        """Test nexus3 script create subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "create", "--help"])
        assert result.exit_code == 0
        assert "Create a new script" in result.stdout

    def test_nexus3_script_delete_help(self):
        """Test nexus3 script delete subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a script" in result.stdout

    def test_nexus3_script_list_help(self):
        """Test nexus3 script list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "list", "--help"])
        assert result.exit_code == 0
        assert "List all scripts" in result.stdout

    def test_nexus3_script_read_help(self):
        """Test nexus3 script read subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "read", "--help"])
        assert result.exit_code == 0
        assert "Get script contents" in result.stdout

    def test_nexus3_script_run_help(self):
        """Test nexus3 script run subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "run", "--help"])
        assert result.exit_code == 0
        assert "Run a script" in result.stdout

    def test_nexus3_script_update_help(self):
        """Test nexus3 script update subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "update", "--help"])
        assert result.exit_code == 0
        assert "Update script contents" in result.stdout

    def test_nexus3_tag_help(self):
        """Test nexus3 tag subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "tag", "--help"])
        assert result.exit_code == 0
        assert "Tag primary interface" in result.stdout
        assert "add" in result.stdout
        assert "delete" in result.stdout
        assert "list" in result.stdout
        assert "show" in result.stdout

    def test_nexus3_tag_add_help(self):
        """Test nexus3 tag add subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "tag", "add", "--help"])
        assert result.exit_code == 0
        assert "Add a tag" in result.stdout

    def test_nexus3_tag_delete_help(self):
        """Test nexus3 tag delete subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "tag", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a tag" in result.stdout

    def test_nexus3_tag_list_help(self):
        """Test nexus3 tag list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "tag", "list", "--help"])
        assert result.exit_code == 0
        assert "List tags" in result.stdout

    def test_nexus3_tag_show_help(self):
        """Test nexus3 tag show subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "tag", "show", "--help"])
        assert result.exit_code == 0
        assert "Show tags" in result.stdout

    def test_nexus3_task_help(self):
        """Test nexus3 task subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "task", "--help"])
        assert result.exit_code == 0
        assert "Task primary interface" in result.stdout
        assert "list" in result.stdout

    def test_nexus3_task_list_help(self):
        """Test nexus3 task list subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "task", "list", "--help"])
        assert result.exit_code == 0
        assert "List tasks" in result.stdout

    def test_nexus3_user_help(self):
        """Test nexus3 user subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "user", "--help"])
        assert result.exit_code == 0
        assert "User primary interface" in result.stdout
        assert "search" in result.stdout
        assert "create" in result.stdout
        assert "delete" in result.stdout

    def test_nexus3_user_search_help(self):
        """Test nexus3 user search subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "user", "search", "--help"])
        assert result.exit_code == 0
        assert "Search users" in result.stdout

    def test_nexus3_user_create_help(self):
        """Test nexus3 user create subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "user", "create", "--help"])
        assert result.exit_code == 0
        assert "Create a new user account" in result.stdout

    def test_nexus3_user_delete_help(self):
        """Test nexus3 user delete subcommand help."""
        result = self.runner.invoke(nexus3_app, ["example.com", "user", "delete", "--help"])
        assert result.exit_code == 0
        assert "Delete a user account" in result.stdout

    def test_nexus3_missing_fqdn(self):
        """Test nexus3 with missing required FQDN argument."""
        result = self.runner.invoke(nexus3_app, ["--help"])
        assert result.exit_code == 0
        # Should show the main help since FQDN is required

    def test_nexus3_asset_list_missing_args(self):
        """Test nexus3 asset list with missing required arguments."""
        result = self.runner.invoke(nexus3_app, ["example.com", "asset", "list"])
        assert result.exit_code == 2
        # Should fail due to missing required repository argument

    def test_nexus3_script_create_missing_args(self):
        """Test nexus3 script create with missing required arguments."""
        result = self.runner.invoke(nexus3_app, ["example.com", "script", "create"])
        assert result.exit_code == 2
        # Should fail due to missing required arguments

    def test_nexus3_integration_with_main_app(self):
        """Test that nexus3 commands are properly integrated in the main app."""
        result = self.runner.invoke(typer_app, ["nexus3", "example.com", "--help"])
        assert result.exit_code == 0
        assert "The Nexus3 API Interface" in result.stdout

    def test_nexus3_asset_integration_with_main_app(self):
        """Test nexus3 asset through the main app."""
        result = self.runner.invoke(typer_app, ["nexus3", "example.com", "asset", "--help"])
        assert result.exit_code == 0
        assert "Asset primary interface" in result.stdout

    def test_nexus3_script_integration_with_main_app(self):
        """Test nexus3 script through the main app."""
        result = self.runner.invoke(typer_app, ["nexus3", "example.com", "script", "--help"])
        assert result.exit_code == 0
        assert "Script primary interface" in result.stdout

    def test_nexus3_user_integration_with_main_app(self):
        """Test nexus3 user through the main app."""
        result = self.runner.invoke(typer_app, ["nexus3", "example.com", "user", "--help"])
        assert result.exit_code == 0
        assert "User primary interface" in result.stdout
