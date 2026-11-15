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
from collections.abc import Iterator
from unittest import mock

import pytest
import responses
from typer.testing import CliRunner

from lftools_uv.api.endpoints.readthedocs import (
    ReadTheDocs,
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
# Branch to slug conversion over HTTP
#
# Read the Docs gives the branch ``release-`` the slug ``release-``. These
# tests register both ``release`` and ``release-`` so that addressing the
# wrong one shows up as a request to the wrong path, not as a failure.
# ---------------------------------------------------------------------------

_RTD_API = "https://readthedocs.org/api/v3/"
_VERSIONS = f"{_RTD_API}projects/fixture/versions/"
_SLUG_PENDING = pytest.mark.xfail(strict=True, reason="slug differs from Read the Docs")


@pytest.fixture
def rtd_http() -> Iterator[responses.RequestsMock]:
    """Route the CLI through a real client against mocked HTTP only."""
    api = ReadTheDocs(creds={"authtype": "token", "endpoint": _RTD_API, "token": "xyz"})
    with (
        mock.patch("lftools_uv.typer_apps.rtd._client", return_value=api),
        responses.RequestsMock(assert_all_requests_are_fired=False) as mocked,
    ):
        yield mocked


def _requested(mocked: responses.RequestsMock) -> list[tuple[str | None, str | None]]:
    return [(call.request.method, call.request.url) for call in mocked.calls]


@_SLUG_PENDING
def test_from_branch_version_details_keeps_trailing_hyphen(rtd_http: responses.RequestsMock) -> None:
    """Lookup of ``release-`` reads ``release-``, never ``release``."""
    rtd_http.get(f"{_VERSIONS}release/", json={"slug": "release"})
    rtd_http.get(f"{_VERSIONS}release-/", json={"slug": "release-"})

    result = runner.invoke(rtd_app, ["project-version-details", "fixture", "release-", "--from-branch", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["slug"] == "release-"
    assert _requested(rtd_http) == [("GET", f"{_VERSIONS}release-/")]


@_SLUG_PENDING
def test_from_branch_build_trigger_keeps_trailing_hyphen(rtd_http: responses.RequestsMock) -> None:
    """A build of ``release-`` is triggered on ``release-``."""
    rtd_http.post(f"{_VERSIONS}release/builds/", json={"build": {"id": 1}}, status=202)
    rtd_http.post(f"{_VERSIONS}release-/builds/", json={"build": {"id": 2}}, status=202)

    result = runner.invoke(rtd_app, ["project-build-trigger", "fixture", "release-", "--from-branch", "--json"])

    assert result.exit_code == 0
    assert json.loads(result.stdout)["build"]["id"] == 2
    assert _requested(rtd_http) == [("POST", f"{_VERSIONS}release-/builds/")]


@_SLUG_PENDING
@pytest.mark.parametrize(("active", "expected"), [("true", True), ("false", False)])
def test_from_branch_version_update_keeps_trailing_hyphen(
    rtd_http: responses.RequestsMock, active: str, expected: bool
) -> None:
    """Activation of ``release-`` patches ``release-`` with the same payload."""
    rtd_http.patch(f"{_VERSIONS}release/", status=204)
    rtd_http.patch(f"{_VERSIONS}release-/", status=204)

    result = runner.invoke(
        rtd_app,
        ["project-version-update", "fixture", "release-", active, "--from-branch", "--json"],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout)["version"] == "release-"
    assert _requested(rtd_http) == [("PATCH", f"{_VERSIONS}release-/")]
    body = rtd_http.calls[0].request.body
    assert isinstance(body, (str, bytes))
    assert json.loads(body) == {"active": expected}


@_SLUG_PENDING
def test_from_branch_missing_version_does_not_fall_back(rtd_http: responses.RequestsMock) -> None:
    """A missing ``release-`` exits 3 even when ``release`` exists."""
    rtd_http.get(f"{_VERSIONS}release/", json={"slug": "release"})
    rtd_http.get(f"{_VERSIONS}release-/", json={"detail": "Not found."}, status=404)

    result = runner.invoke(rtd_app, ["project-version-details", "fixture", "release-", "--from-branch", "--json"])

    assert result.exit_code == 3
    assert _requested(rtd_http) == [("GET", f"{_VERSIONS}release-/")]


@pytest.mark.parametrize("version", ["release-", "Feature/Foo+Bar", "_release"])
def test_literal_version_is_not_slugified(rtd_http: responses.RequestsMock, version: str) -> None:
    """Without ``--from-branch`` the version reaches the request as given."""
    rtd_http.get(f"{_VERSIONS}{version}/", json={"slug": version})

    result = runner.invoke(rtd_app, ["project-version-details", "fixture", version, "--json"])

    assert result.exit_code == 0
    assert _requested(rtd_http) == [("GET", f"{_VERSIONS}{version}/")]


@pytest.mark.parametrize(
    ("command", "extra"),
    [
        ("project-version-details", []),
        ("project-build-trigger", []),
        ("project-version-update", ["true"]),
    ],
)
@pytest.mark.parametrize("branch", ["", "   ", "///", pytest.param("...", marks=_SLUG_PENDING)])
def test_from_branch_rejects_unusable_without_request(
    rtd_http: responses.RequestsMock, command: str, extra: list[str], branch: str
) -> None:
    """Unusable branch names fail before any request is made."""
    result = runner.invoke(rtd_app, [command, "fixture", branch, *extra, "--from-branch", "--json"])

    assert result.exit_code == 1
    assert _requested(rtd_http) == []


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------


def test_not_found_exits_non_zero_with_stderr_message() -> None:
    """A missing project exits 3 and reports the failure as a diagnostic.

    Click and Typer split stderr on some versions and mix it into stdout
    on others, so combine both streams before matching, matching the
    approach the Zulip CLI tests take.
    """
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_details.side_effect = ReadTheDocsNotFoundError("Project 'nope' not found")
        result = runner.invoke(rtd_app, ["project-details", "nope", "--json"])

    assert result.exit_code == 3
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

    assert result.exit_code == 3
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


#: Read commands, the client method each calls, and its arguments.
READ_COMMANDS = [
    ("project-details", "project_details", ["nope"]),
    ("project-version-list", "project_version_list", ["nope"]),
    ("project-version-details", "project_version_details", ["nope", "latest"]),
    ("project-build-list", "project_build_list", ["nope"]),
    ("project-build-details", "project_build_details", ["nope", "1"]),
    ("subproject-list", "subproject_list", ["nope"]),
    ("subproject-details", "subproject_details", ["nope", "child"]),
]


@pytest.mark.parametrize(("command", "method", "args"), READ_COMMANDS)
def test_read_command_not_found_exits_3(command: str, method: str, args: list[str]) -> None:
    """A read command exits 3 on HTTP 404, keeping the message unchanged.

    Shell callers test the status instead of matching the message, so
    it must differ from 1 (other API errors) and 2 (usage).
    """
    message = "Project 'nope' not found"
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        getattr(api.return_value, method).side_effect = ReadTheDocsNotFoundError(message)
        result = runner.invoke(rtd_app, [command, *args])

    assert result.exit_code == 3
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert f"Error: {message}" in clean_cli_output(combined)


@pytest.mark.parametrize(("command", "method", "args"), READ_COMMANDS)
def test_read_command_other_api_error_exits_1(command: str, method: str, args: list[str]) -> None:
    """Any API error other than 404 still exits 1 on a read command."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        getattr(api.return_value, method).side_effect = ReadTheDocsAPIError("denied", 403)
        result = runner.invoke(rtd_app, [command, *args])

    assert result.exit_code == 1


def test_write_command_not_found_still_exits_1() -> None:
    """Write commands keep exit 1 on HTTP 404; the contract covers reads."""
    with mock.patch("lftools_uv.typer_apps.rtd.ReadTheDocs") as api:
        api.return_value.project_version_update.side_effect = ReadTheDocsNotFoundError("Version 'x' not found")
        result = runner.invoke(rtd_app, ["project-version-update", "nope", "x", "true"])

    assert result.exit_code == 1


def test_project_update_rejects_malformed_pairs() -> None:
    """A key=value typo reports an error instead of silently succeeding."""
    result = runner.invoke(rtd_app, ["project-update", "onap-cps", "notapair"])
    assert result.exit_code == 1


def test_project_update_requires_parameters() -> None:
    """Calling update with no pairs is an error."""
    result = runner.invoke(rtd_app, ["project-update", "onap-cps"])
    assert result.exit_code == 1
