# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Unit tests for the Read the Docs Typer CLI layer.

Covers command registration, the ``--json`` contract on both the group
callback and individual commands, branch-to-slug conversion via
``--from-branch``, and the routing of diagnostics to stderr.
"""

from __future__ import annotations

import json
from unittest import mock

import pytest
from typer.testing import CliRunner

from lftools_uv.api.endpoints.readthedocs import (
    ReadTheDocsAPIError,
    ReadTheDocsNotFoundError,
)
from lftools_uv.typer_apps.rtd import get_rtd_app, rtd_app
from tests.test_utils import clean_cli_output

runner = CliRunner()

#: Every command the documentation pipeline calls.
PIPELINE_COMMANDS = [
    "project-details",
    "project-create",
    "project-update",
    "project-version-details",
    "project-version-update",
    "project-build-trigger",
    "project-build-details",
    "subproject-list",
    "subproject-create",
]


def test_rtd_app_registered() -> None:
    """The rtd Typer app exposes help."""
    result = runner.invoke(rtd_app, ["--help"])
    assert result.exit_code == 0
    assert "read the docs" in clean_cli_output(result.stdout).lower()


def test_get_rtd_app_returns_app() -> None:
    """The registration helper returns the module-level app."""
    assert get_rtd_app() is rtd_app


@pytest.mark.parametrize("command", PIPELINE_COMMANDS)
def test_pipeline_commands_present(command: str) -> None:
    """Commands the documentation workflows depend on must exist.

    The previous Typer implementation shipped four of fourteen
    commands, which broke any caller migrating from legacy lftools.
    """
    result = runner.invoke(rtd_app, [command, "--help"])
    assert result.exit_code == 0, f"{command} missing from the rtd app"


@pytest.mark.parametrize(
    "command",
    [
        "project-list",
        "project-details",
        "project-version-list",
        "project-version-details",
        "project-build-list",
        "project-build-details",
        "project-build-trigger",
        "subproject-list",
        "subproject-details",
        "subproject-create",
        "subproject-delete",
        "project-create",
        "project-update",
        "project-version-update",
    ],
)
def test_every_command_offers_json(command: str) -> None:
    """Each command advertises --json for machine-readable output.

    Rich may inject ANSI styling inside the option name, so strip escape
    sequences before matching.
    """
    result = runner.invoke(rtd_app, [command, "--help"])
    assert result.exit_code == 0
    assert "--json" in clean_cli_output(result.stdout)


# ---------------------------------------------------------------------------
# JSON output contract
# ---------------------------------------------------------------------------


def test_project_list_json_is_parsable() -> None:
    """--json emits a payload that parses cleanly."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_list.return_value = ["onap", "onap-cps"]
        result = runner.invoke(rtd_app, ["project-list", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {"projects": ["onap", "onap-cps"]}


def test_json_flag_accepted_on_group() -> None:
    """--json works before the subcommand as well as after."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_list.return_value = ["onap"]
        result = runner.invoke(rtd_app, ["--json", "project-list"])

    assert result.exit_code == 0
    assert json.loads(result.stdout) == {"projects": ["onap"]}


def test_project_list_table_by_default() -> None:
    """Without --json the output renders as a table, not JSON."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_list.return_value = ["onap-cps"]
        result = runner.invoke(rtd_app, ["project-list"])

    assert result.exit_code == 0
    assert "Project Slug" in clean_cli_output(result.stdout)
    with pytest.raises(json.JSONDecodeError):
        json.loads(result.stdout)


def test_build_list_empty_emits_empty_array() -> None:
    """An empty build list stays parsable rather than turning into prose.

    The legacy endpoint returned the sentence 'There are no active
    builds.', which broke callers piping output to jq.
    """
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_build_list.return_value = []
        result = runner.invoke(rtd_app, ["project-build-list", "onap-cps", "--json"])

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["builds"] == []
    assert payload["count"] == 0


# ---------------------------------------------------------------------------
# Branch to slug conversion
# ---------------------------------------------------------------------------


def test_from_branch_slugifies_build_trigger() -> None:
    """--from-branch converts a slashed branch before calling the API."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_build_trigger.return_value = {"build": {"id": 1}}
        result = runner.invoke(
            rtd_app,
            ["project-build-trigger", "onap-cps", "maintenance/3.7.10", "--from-branch", "--json"],
        )

    assert result.exit_code == 0
    api.return_value.project_build_trigger.assert_called_once_with("onap-cps", "maintenance-3.7.10")


def test_without_from_branch_value_passes_through() -> None:
    """A plain slug reaches the API unchanged."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_build_trigger.return_value = {"build": {"id": 1}}
        result = runner.invoke(rtd_app, ["project-build-trigger", "onap-cps", "latest", "--json"])

    assert result.exit_code == 0
    api.return_value.project_build_trigger.assert_called_once_with("onap-cps", "latest")


def test_from_branch_slugifies_version_details() -> None:
    """--from-branch applies to version lookups too."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_version_details.return_value = {"slug": "maintenance-3.7.10"}
        result = runner.invoke(
            rtd_app,
            ["project-version-details", "onap-cps", "maintenance/3.7.10", "--from-branch", "--json"],
        )

    assert result.exit_code == 0
    api.return_value.project_version_details.assert_called_once_with("onap-cps", "maintenance-3.7.10")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_not_found_exits_non_zero_with_stderr_message() -> None:
    """A missing project exits 1 and reports the failure as a diagnostic.

    Click and Typer split stderr on some versions and mix it into stdout
    on others, so combine both streams before matching, matching the
    approach the Zulip CLI tests take.
    """
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_details.side_effect = ReadTheDocsNotFoundError("Project 'nope' not found")
        result = runner.invoke(rtd_app, ["project-details", "nope", "--json"])

    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "not found" in clean_cli_output(combined).lower()


def test_error_keeps_stdout_free_of_diagnostics() -> None:
    """A failure must not write the diagnostic into a JSON stdout stream.

    When the runner separates the streams, stdout stays empty so a
    caller piping it to a parser never receives an error message.
    """
    split_runner = CliRunner()
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_details.side_effect = ReadTheDocsNotFoundError("Project 'nope' not found")
        result = split_runner.invoke(rtd_app, ["project-details", "nope", "--json"])

    assert result.exit_code == 1
    stderr = getattr(result, "stderr", "") or ""
    if stderr:
        # Streams are separated on this Click/Typer version.
        assert "not found" in clean_cli_output(stderr).lower()
        assert "not found" not in clean_cli_output(result.stdout).lower()


def test_api_error_exits_non_zero() -> None:
    """A server error exits non-zero rather than emitting a broken payload."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_details.side_effect = ReadTheDocsAPIError("boom", 500)
        result = runner.invoke(rtd_app, ["project-details", "boom"])

    assert result.exit_code == 1


def test_project_update_rejects_malformed_pairs() -> None:
    """A key=value typo reports an error instead of silently succeeding."""
    result = runner.invoke(rtd_app, ["project-update", "onap-cps", "notapair"])
    assert result.exit_code == 1


def test_project_update_requires_parameters() -> None:
    """Calling update with no pairs is an error."""
    result = runner.invoke(rtd_app, ["project-update", "onap-cps"])
    assert result.exit_code == 1
