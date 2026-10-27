# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the guidance printed by the Typer ``infofile`` placeholders.

The Typer ``infofile`` commands are placeholders that point the user at the
Click implementation. The hints named ``lftools``, the legacy executable that
lftools-uv does not install, and three of them name commands that exist in no
front-end. A hint must name a command the user can run, or say plainly that
none exists.

Whether the placeholders should exit non-zero is tracked separately in #857.
"""

import re

import pytest
from typer.testing import CliRunner

from lftools_uv.cli.infofile import infofile as click_infofile
from lftools_uv.typer_apps.infofile import infofile_app

runner = CliRunner()

PLACEHOLDER_ARGS = {
    "create-info-file": ["gerrit.example.org", "foo/bar"],
    "get-committers": ["gerrit.example.org", "foo/bar", "grp", "INFO.yaml"],
    "validate-info-file": ["INFO.yaml"],
    "check-committers": ["INFO.yaml"],
    "match-ldap": ["INFO.yaml"],
}


@pytest.mark.parametrize("command", PLACEHOLDER_ARGS)
def test_placeholder_hint_names_a_runnable_command(command):
    """The hint matches what the Click front-end actually provides."""
    result = runner.invoke(infofile_app, [command, *PLACEHOLDER_ARGS[command]])
    output = result.output

    assert re.search(r"\blftools(?!-uv)\b", output) is None
    if command in click_infofile.commands:
        assert f"LEGACY_CLI=1 lftools-uv infofile {command}" in output
    else:
        assert "lftools-uv infofile" not in output
        assert "not implemented" in output


def test_placeholders_cover_every_typer_command():
    """Guard the parametrisation: a new placeholder must be checked too."""
    registered = {cmd.name for cmd in infofile_app.registered_commands}
    assert registered == set(PLACEHOLDER_ARGS)


@pytest.mark.xfail(strict=True, reason="#857: placeholders print to stdout and exit 0")
@pytest.mark.parametrize("command", PLACEHOLDER_ARGS)
def test_placeholder_exits_non_zero_with_note_on_stderr(command):
    """A placeholder does no work, so it must not report success."""
    result = runner.invoke(infofile_app, [command, *PLACEHOLDER_ARGS[command]])

    assert result.exit_code == 1
    assert result.stdout == ""
    assert "Note: This command is" in result.stderr
    assert "Traceback" not in result.output
