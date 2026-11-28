# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Typer ``infofile`` command set.

``check-votes``, ``create-info-file``, ``get-committers`` and
``sync-committers`` are full ports of the Click commands; tests that run
them through both front-ends live in test_typer_legacy_ports.py.
"""

from typer.testing import CliRunner

from lftools_uv.typer_apps.infofile import infofile_app

runner = CliRunner()


def test_lists_only_working_commands():
    """Commands that exist in no front-end are not offered."""
    registered = {cmd.name for cmd in infofile_app.registered_commands}
    assert registered == {"check-votes", "create-info-file", "get-committers", "sync-committers"}


def test_no_command_points_at_the_legacy_cli():
    """No command is a placeholder that sends the user to LEGACY_CLI=1."""
    result = runner.invoke(infofile_app, ["create-info-file", "gerrit.example.org", "foo/bar", "--empty"])

    assert result.exit_code == 0, result.output
    assert "LEGACY_CLI" not in result.output
