# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the Typer ``infofile`` command set and its one placeholder.

``check-votes``, ``get-committers`` and ``sync-committers`` are full ports;
tests for them live in test_typer_legacy_ports.py. ``create-info-file`` is
still a placeholder that points the user at the Click implementation. Its
hint must name a command the user can run: ``lftools``, the legacy
executable, is not installed by lftools-uv.

The placeholder does no work, so it exits 1 with its guidance on stderr.
"""

import re

from typer.testing import CliRunner

from lftools_uv.typer_apps.infofile import infofile_app

runner = CliRunner()

PLACEHOLDER_ARGS = ["create-info-file", "gerrit.example.org", "foo/bar"]


def test_lists_only_working_commands():
    """Commands that exist in no front-end are not offered."""
    registered = {cmd.name for cmd in infofile_app.registered_commands}
    assert registered == {"check-votes", "create-info-file", "get-committers", "sync-committers"}


def test_placeholder_hint_names_a_runnable_command():
    """The hint matches what the Click front-end actually provides."""
    result = runner.invoke(infofile_app, PLACEHOLDER_ARGS)

    assert re.search(r"\blftools(?!-uv)\b", result.output) is None
    assert "LEGACY_CLI=1 lftools-uv infofile create-info-file" in result.output


def test_placeholder_exits_non_zero_with_note_on_stderr():
    """A placeholder does no work, so it must not report success."""
    result = runner.invoke(infofile_app, PLACEHOLDER_ARGS)

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Note: This command is" in result.stderr
    assert "Traceback" not in result.output
