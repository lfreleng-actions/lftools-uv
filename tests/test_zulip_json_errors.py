# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``--json`` failures of the channel mutation commands.

Under ``--json`` every failure of ``channel archive``, ``unarchive``,
``update`` and ``topic-policy`` must print the FR-008 error payload on
stdout, with nothing on stderr, and exit 1. Without ``--json`` the
failure stays an ``Error: ...`` line on stderr with empty stdout.

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
from lftools_uv.api.endpoints.zulip import ZulipConfigError, ZulipNotFoundError
from lftools_uv.typer_apps.zulip import zulip_app

API_FUNCTIONS = ("archive_channel", "unarchive_channel", "update_channel", "set_topic_policy", "get_topic_policy")
NOT_FOUND = "Channel 'missing' not found"
XFAIL = pytest.mark.xfail(strict=True, reason="#900: --json failures write only to stderr")


@dataclass(frozen=True)
class Case:
    """One failing invocation and the error payload it should produce."""

    args: tuple[str, ...]
    operation: str
    channel_name: str
    error: str
    command_json: bool = False

    def argv(self, *, json_output: bool) -> list[str]:
        """Return the arguments, with ``--json`` where the case puts it."""
        if not json_output:
            return list(self.args)
        if self.command_json:
            return [*self.args, "--json"]
        return ["--json", *self.args]


API_CASES = [
    Case(("channel", "archive", "missing", "--yes"), "archive", "missing", NOT_FOUND),
    Case(("channel", "archive", "  missing  ", "--yes"), "archive", "missing", NOT_FOUND),
    Case(("channel", "unarchive", "missing", "--yes"), "unarchive", "missing", NOT_FOUND),
    Case(("channel", "update", "missing", "--description", "x"), "update", "missing", NOT_FOUND),
    Case(("channel", "topic-policy", "missing", "--policy", "allow"), "topic-policy", "missing", NOT_FOUND),
    Case(("channel", "topic-policy", "missing"), "topic-policy", "missing", NOT_FOUND),
    Case(
        ("channel", "topic-policy", "missing", "--policy", "allow"),
        "topic-policy",
        "missing",
        NOT_FOUND,
        command_json=True,
    ),
]

VALIDATION_CASES = [
    Case(
        ("channel", "archive", "general"),
        "archive",
        "general",
        "Refusing to archive without --yes. Re-run with --yes to confirm.",
    ),
    Case(
        ("channel", "unarchive", "general"),
        "unarchive",
        "general",
        "Refusing to unarchive without explicit confirmation. Re-run with --yes to proceed.",
    ),
    Case(
        ("channel", "archive", "--channel-id", "abc", "--yes"),
        "archive",
        "",
        "--channel-id must be a numeric channel ID.",
    ),
    Case(
        ("channel", "unarchive", "--channel-id", "abc", "--yes"),
        "unarchive",
        "",
        "--channel-id must be a numeric channel ID.",
    ),
    Case(
        ("channel", "update", "--description", "x"),
        "update",
        "",
        "Exactly one of [channel] or --channel-id is required",
    ),
    Case(
        ("channel", "update", "general", "--channel-id", "7", "--description", "x"),
        "update",
        "general",
        "Specify only one of [channel] or --channel-id, not both",
    ),
    Case(
        ("channel", "update", "general"),
        "update",
        "general",
        "channel update requires at least one setting to change "
        "(--name, --description, --type, --topic-policy, --allow-group, "
        "--folder, --subscribe, --can-remove-subscribers-group, "
        "--can-add-subscribers-group, --can-administer-channel-group, "
        "or --can-send-message-group)",
    ),
    Case(
        ("channel", "update", "general", "--type", "secret"),
        "update",
        "general",
        "Invalid --type 'secret'; expected one of private, public, web-public",
    ),
    Case(
        ("channel", "topic-policy", "general", "--policy", "bogus"),
        "topic-policy",
        "general",
        "Invalid --policy 'bogus'; expected one of allow, deny, follow-default",
        command_json=True,
    ),
    Case(
        ("channel", "topic-policy"),
        "topic-policy",
        "",
        "Exactly one of [channel] or --channel-id is required",
        command_json=True,
    ),
]


def _case_id(case: Case) -> str:
    return " ".join(case.argv(json_output=True))


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> dict[str, mock.MagicMock]:
    """Patch the client and every API function to fail as not found."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    mocks = {"get_client": mock.MagicMock(return_value=mock.MagicMock())}
    for name in API_FUNCTIONS:
        mocks[name] = mock.MagicMock(side_effect=ZulipNotFoundError(NOT_FOUND))
    for name, value in mocks.items():
        monkeypatch.setattr(zulip_mod, name, value, raising=False)
    return mocks


def _assert_error_payload(result: Result, case: Case) -> None:
    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout) == {
        "status": "error",
        "channel_id": None,
        "channel_name": case.channel_name,
        "operation": case.operation,
        "error": case.error,
    }
    assert result.stderr == ""


@XFAIL
@pytest.mark.parametrize("case", API_CASES, ids=_case_id)
def test_api_failure_emits_json_payload(api: dict[str, mock.MagicMock], case: Case) -> None:
    """An API failure under --json is the error payload on stdout."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    _assert_error_payload(result, case)


@XFAIL
def test_config_failure_emits_json_payload(api: dict[str, mock.MagicMock]) -> None:
    """A client configuration failure under --json is the error payload."""
    api["get_client"].side_effect = ZulipConfigError("No zuliprc found")
    case = Case(("channel", "archive", "missing", "--yes"), "archive", "missing", "No zuliprc found")

    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    _assert_error_payload(result, case)


@XFAIL
@pytest.mark.parametrize("case", VALIDATION_CASES, ids=_case_id)
def test_validation_failure_emits_json_payload(api: dict[str, mock.MagicMock], case: Case) -> None:
    """A flag validation failure under --json is the error payload."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    _assert_error_payload(result, case)
    for name in API_FUNCTIONS:
        assert not api[name].called, name


@pytest.mark.parametrize("case", API_CASES + VALIDATION_CASES, ids=_case_id)
def test_failure_without_json_writes_stderr(api: dict[str, mock.MagicMock], case: Case) -> None:
    """Without --json a failure stays an error line on stderr."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=False))

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert result.stderr == f"Error: {case.error}\n"
