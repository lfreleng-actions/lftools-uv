# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``--json`` flag-check failures of ``channel subscribe``.

Under ``--json`` a flag-check failure of ``channel subscribe`` must
print the FR-008 bulk error payload on stdout, with nothing on stderr,
and exit 1, as ``channel unsubscribe`` does. Without ``--json`` the
failure stays an ``Error: ...`` line on stderr with empty stdout.
``user show`` shares the ``--by-*`` check and must not change.

The client and every API function are mocks: no test reaches a Zulip
server or the network.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from unittest import mock

import pytest
from typer.testing import CliRunner

import lftools_uv.typer_apps.zulip as zulip_mod
from lftools_uv.typer_apps.zulip import zulip_app

API_FUNCTIONS = ("get_client", "resolve_channel", "subscribe_users")
NO_MODE = "Specify exactly one of --by-email, --by-id, or --by-name"


@dataclass(frozen=True)
class Case:
    """One failing invocation and the error payload it should produce."""

    args: tuple[str, ...]
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


CASES = [
    Case(("channel", "subscribe", "general", "alice"), "general", NO_MODE),
    Case(
        ("channel", "subscribe", "general", "alice", "--by-email", "--by-id"),
        "general",
        "--by-email, --by-id, and --by-name are mutually exclusive",
    ),
    Case(
        ("channel", "subscribe", "--channel-id", "abc", "alice", "--by-email"),
        "",
        "--channel-id must be a numeric channel ID.",
    ),
    Case(
        ("channel", "subscribe", "--channel-id", "7", "--by-email"),
        "",
        "Provide at least one USER, or omit --channel-id and pass [CHANNEL] USER...",
    ),
    Case(
        ("channel", "subscribe", "general", "--by-email"),
        "general",
        "Provide [CHANNEL] followed by at least one USER, or use --channel-id.",
    ),
    Case(
        ("channel", "subscribe", "--by-email"),
        "",
        "Provide [CHANNEL] followed by at least one USER, or use --channel-id.",
    ),
    Case(("channel", "subscribe", "general", "alice"), "general", NO_MODE, command_json=True),
]


def _case_id(case: Case) -> str:
    return " ".join(case.argv(json_output=True))


@pytest.fixture
def api(monkeypatch: pytest.MonkeyPatch) -> dict[str, mock.MagicMock]:
    """Patch the client and the subscribe API functions with plain mocks."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    mocks = {name: mock.MagicMock() for name in API_FUNCTIONS}
    for name, value in mocks.items():
        monkeypatch.setattr(zulip_mod, name, value, raising=False)
    return mocks


@pytest.mark.xfail(strict=True, reason="subscribe flag checks print no --json error payload")
@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_flag_failure_emits_json_payload(api: dict[str, mock.MagicMock], case: Case) -> None:
    """A flag-check failure under --json is the bulk error payload."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=True))

    assert result.exit_code == 1, result.output
    assert json.loads(result.stdout) == {
        "status": "error",
        "channel_id": None,
        "channel_name": case.channel_name,
        "operation": "subscribe",
        "results": [],
        "errors": [{"user": None, "error": case.error}],
    }
    assert result.stderr == ""
    for name in API_FUNCTIONS:
        assert not api[name].called, name


@pytest.mark.parametrize("case", CASES, ids=_case_id)
def test_flag_failure_without_json_writes_stderr(api: dict[str, mock.MagicMock], case: Case) -> None:
    """Without --json a flag-check failure stays an error line on stderr."""
    result = CliRunner().invoke(zulip_app, case.argv(json_output=False))

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert result.stderr == f"Error: {case.error}\n"


def test_user_show_id_mode_failure_unchanged(api: dict[str, mock.MagicMock]) -> None:
    """``user show`` keeps its stderr error for the shared --by-* check."""
    result = CliRunner().invoke(zulip_app, ["--json", "user", "show", "alice"])

    assert result.exit_code == 1, result.output
    assert result.stdout == ""
    assert result.stderr == f"Error: {NO_MODE}\n"
