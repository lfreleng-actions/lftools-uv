# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``--json`` failures of the folder mutation commands.

Under ``--json`` every failure of ``folder create``, ``update``,
``archive``, ``unarchive`` and ``move`` must print the spec 002
``FolderMutationResult`` error payload on stdout, with nothing on
stderr, and exit 1. Without ``--json`` the failure stays an
``Error: ...`` line on stderr with empty stdout.

The client and every API function are mocks: no test reaches a Zulip
server or the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest import mock

import pytest
from typer.testing import CliRunner, Result

import lftools_uv.typer_apps.zulip as zulip_mod
from lftools_uv.api.endpoints.zulip import ZulipAPIError, ZulipConfigError
from lftools_uv.typer_apps.zulip import zulip_app

FAILING_FUNCTIONS = {
    "create_channel_folder": "create failed",
    "update_channel_folder": "update failed",
    "archive_channel_folder": "archive failed",
    "unarchive_channel_folder": "unarchive failed",
    "reorder_channel_folders": "reorder failed",
}
FOLDERS = [{"id": 10, "name": "Projects", "order": 1}, {"id": 12, "name": "Teams", "order": 2}]
API_FUNCTIONS = ("get_client", "list_channel_folders", *FAILING_FUNCTIONS)
UPDATE_FLAGS = "folder update requires at least one of --name or --description"
MOVE_FLAGS = "Exactly one of --before or --after is required"


@dataclass(frozen=True)
class Case:
    """One failing invocation and the error payload it should produce."""

    args: tuple[str, ...]
    operation: str
    folder_id: int | None
    error: str
    folder_name: str | None = None
    command_json: bool = False

    def argv(self, *, json_output: bool) -> list[str]:
        """Return the arguments, with ``--json`` where the case puts it."""
        if not json_output:
            return list(self.args)
        if self.command_json:
            return [*self.args, "--json"]
        return ["--json", *self.args]


API_CASES = [
    Case(("folder", "create", "--name", "Projects"), "create", None, "create failed", folder_name="Projects"),
    Case(("folder", "update", "--folder-id", "10", "--name", "Eng"), "update", 10, "update failed"),
    Case(("folder", "archive", "--folder-id", "10"), "archive", 10, "archive failed"),
    Case(("folder", "unarchive", "--folder-id", "10"), "unarchive", 10, "unarchive failed"),
    Case(("folder", "move", "--folder-id", "10", "--after", "id:12"), "move", 10, "reorder failed"),
    Case(
        ("folder", "move", "--folder-id", "10", "--before", "id:10"),
        "move",
        10,
        "Cannot move folder relative to itself",
    ),
    Case(("folder", "move", "--folder-id", "99", "--after", "id:10"), "move", 99, "Target folder id 99 not found"),
    Case(("folder", "archive", "--folder-id", "10"), "archive", 10, "archive failed", command_json=True),
]

VALIDATION_CASES = [
    Case(("folder", "update", "--folder-id", "10"), "update", 10, UPDATE_FLAGS),
    Case(("folder", "update", "--folder-id", "10"), "update", 10, UPDATE_FLAGS, command_json=True),
    Case(("folder", "move", "--folder-id", "10"), "move", 10, MOVE_FLAGS),
    Case(
        ("folder", "move", "--folder-id", "10", "--before", "a", "--after", "b"),
        "move",
        10,
        MOVE_FLAGS,
        command_json=True,
    ),
]


def _case_id(case: Case) -> str:
    return " ".join(case.argv(json_output=True))


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> dict[str, mock.MagicMock]:
    """Patch the client and every folder mutation to fail."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    mocks = {
        "get_client": mock.MagicMock(return_value=mock.MagicMock()),
        "list_channel_folders": mock.MagicMock(return_value=[dict(folder) for folder in FOLDERS]),
    }
    for name, message in FAILING_FUNCTIONS.items():
        mocks[name] = mock.MagicMock(side_effect=ZulipAPIError(message))
    for name, value in mocks.items():
        monkeypatch.setattr(zulip_mod, name, value, raising=False)
    return mocks


def _assert_error_payload(result: Result, case: Case) -> None:
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout) == {
        "status": "error",
        "folder_id": case.folder_id,
        "folder_name": case.folder_name,
        "operation": case.operation,
        "error": case.error,
    }
    assert result.stderr == ""


@pytest.mark.parametrize("case", API_CASES, ids=_case_id)
def test_api_failure_emits_json_payload(api: dict[str, mock.MagicMock], case: Case) -> None:
    """An API failure under --json is the error payload on stdout."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    _assert_error_payload(result, case)


def test_config_failure_emits_json_payload(api: dict[str, mock.MagicMock]) -> None:
    """A client configuration failure under --json is the error payload."""
    api["get_client"].side_effect = ZulipConfigError("No zuliprc found")
    case = Case(("folder", "archive", "--folder-id", "10"), "archive", 10, "No zuliprc found")

    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    _assert_error_payload(result, case)


@pytest.mark.parametrize("case", VALIDATION_CASES, ids=_case_id)
def test_validation_failure_emits_json_payload(api: dict[str, mock.MagicMock], case: Case) -> None:
    """A flag validation failure under --json is the error payload."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    _assert_error_payload(result, case)


@pytest.mark.parametrize("case", VALIDATION_CASES, ids=_case_id)
def test_validation_failure_calls_no_api(api: dict[str, mock.MagicMock], case: Case) -> None:
    """A flag validation failure never reaches the client or the API."""
    CliRunner().invoke(zulip_app, case.argv(json_output=True))

    for name in API_FUNCTIONS:
        assert not api[name].called, name


@pytest.mark.parametrize("case", API_CASES + VALIDATION_CASES, ids=_case_id)
def test_failure_without_json_writes_stderr(api: dict[str, mock.MagicMock], case: Case) -> None:
    """Without --json a failure stays an error line on stderr."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=False))

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert result.stderr == f"Error: {case.error}\n"
