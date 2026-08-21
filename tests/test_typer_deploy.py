# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Typer deploy commands that delegate to the deploy subsystem.

`copy-archives` and `maven-file` previously echoed a placeholder and exited
successfully. These tests pin the behaviour they gained: argument forwarding,
the translation from this command's option names to the flags the deploy shell
script understands, and exit-code propagation.
"""

from unittest.mock import patch

from typer.testing import CliRunner

from lftools_uv.typer_apps.deploy import deploy_app

runner = CliRunner()


class TestCopyArchives:
    """`deploy copy-archives` forwards to deploy_sys.copy_archives."""

    @patch("lftools_uv.typer_apps.deploy.deploy_sys.copy_archives")
    def test_forwards_workspace_with_no_patterns(self, mock_copy):
        """With no patterns, None is forwarded rather than an empty list."""
        result = runner.invoke(deploy_app, ["copy-archives", "/w/space"])

        assert result.exit_code == 0
        mock_copy.assert_called_once_with("/w/space", None)

    @patch("lftools_uv.typer_apps.deploy.deploy_sys.copy_archives")
    def test_forwards_positional_patterns(self, mock_copy):
        """Positional patterns reach the implementation in order."""
        result = runner.invoke(deploy_app, ["copy-archives", "/w/space", "*.log", "**/*.xml"])

        assert result.exit_code == 0
        mock_copy.assert_called_once_with("/w/space", ["*.log", "**/*.xml"])

    @patch("lftools_uv.typer_apps.deploy.deploy_sys.copy_archives")
    def test_reads_workspace_from_environment(self, mock_copy):
        """WORKSPACE supplies the argument, as it does under Jenkins."""
        result = runner.invoke(deploy_app, ["copy-archives"], env={"WORKSPACE": "/env/space"})

        assert result.exit_code == 0
        mock_copy.assert_called_once_with("/env/space", None)

    @patch("lftools_uv.typer_apps.deploy.deploy_sys.copy_archives")
    def test_failure_is_not_reported_as_success(self, mock_copy):
        """A failing copy must not exit 0, which is what the stub used to do."""
        mock_copy.side_effect = OSError("disk full")

        result = runner.invoke(deploy_app, ["copy-archives", "/w/space"])

        assert result.exit_code != 0


class TestMavenFile:
    """`deploy maven-file` builds the deploy script invocation."""

    ARGS = ["maven-file", "https://nexus.example.org", "repo-id", "artifact.tar.xz"]

    @patch("lftools_uv.typer_apps.deploy.subprocess.call", return_value=0)
    def test_required_arguments_come_last(self, mock_call):
        """getopts consumes flags first, so positionals must trail them."""
        result = runner.invoke(deploy_app, self.ARGS)

        assert result.exit_code == 0
        assert mock_call.call_args[0][0] == [
            "deploy",
            "maven-file",
            "https://nexus.example.org",
            "repo-id",
            "artifact.tar.xz",
        ]

    @patch("lftools_uv.typer_apps.deploy.subprocess.call", return_value=0)
    def test_options_translate_to_shell_script_flags(self, mock_call):
        """This command's option names differ from the script's flags.

        The mapping is not identity: --global-settings is forwarded as -l,
        and --pom-file as -f.
        """
        result = runner.invoke(
            deploy_app,
            [
                *self.ARGS,
                "-b",
                "/usr/bin/mvn",
                "-gs",
                "/etc/global.xml",
                "-s",
                "/home/settings.xml",
                "-p",
                "-DskipTests",
                "-a",
                "my-artifact",
                "-c",
                "sources",
                "-f",
                "pom.xml",
                "-g",
                "org.example",
                "-v",
                "1.2.3",
            ],
        )

        assert result.exit_code == 0
        params = mock_call.call_args[0][0]
        pairs = dict(zip(params[2:-3:2], params[3:-3:2], strict=True))
        assert pairs == {
            "-b": "/usr/bin/mvn",
            "-l": "/etc/global.xml",
            "-s": "/home/settings.xml",
            "-p": "-DskipTests",
            "-a": "my-artifact",
            "-c": "sources",
            "-g": "org.example",
            "-f": "pom.xml",
            "-v": "1.2.3",
        }

    @patch("lftools_uv.typer_apps.deploy.subprocess.call", return_value=3)
    def test_propagates_script_exit_status(self, mock_call):
        """A failing deploy script must fail the command."""
        result = runner.invoke(deploy_app, self.ARGS)

        assert result.exit_code == 3

    @patch("lftools_uv.typer_apps.deploy.subprocess.call", side_effect=FileNotFoundError)
    def test_missing_deploy_binary_exits_127(self, mock_call):
        """127 is the conventional shell status for a missing command."""
        result = runner.invoke(deploy_app, self.ARGS)

        assert result.exit_code == 127
