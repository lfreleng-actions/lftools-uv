# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Unit tests for the Zulip Typer CLI layer.

Covers the foundation helpers (``MISSING_EXTRA_MESSAGE`` guard,
``--help`` resilient-parsing short-circuit, ``mutation_result`` and
``bulk_mutation_result`` output shaping). Per-command tests live
alongside the user-story slices that introduce them.
"""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest
from typer.testing import CliRunner

import lftools_uv.typer_apps.zulip as zulip_mod
from lftools_uv.api.endpoints.zulip import ZulipConfigError
from lftools_uv.typer_apps.zulip import (
    MISSING_EXTRA_MESSAGE,
    bulk_mutation_result,
    mutation_result,
    zulip_app,
)


def test_zulip_app_registered() -> None:
    """The zulip Typer app exposes help even without subcommands."""
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--help"])
    assert result.exit_code == 0
    assert "zulip" in result.stdout.lower()


def test_missing_extra_message_is_canonical() -> None:
    """The FR-022 canonical install hint must be exposed for reuse."""
    assert 'pip install "lftools-uv[zulip]"' in MISSING_EXTRA_MESSAGE
    assert MISSING_EXTRA_MESSAGE.startswith("Zulip support requires the zulip extra.")


def test_zulip_help_works_without_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--help`` for the zulip group must render even when the extra is gone.

    Typer walks the command tree with ``resilient_parsing=True`` while
    rendering help, so the top-level callback must short-circuit before
    enforcing the FR-022 extra-required guard. Otherwise users could not
    discover commands until after installing the extra.
    """
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: False)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--help"])
    assert result.exit_code == 0
    assert "zulip" in result.stdout.lower()


# ---------------------------------------------------------------------------
# Output-shape helpers
# ---------------------------------------------------------------------------


def test_mutation_result_minimal_payload() -> None:
    """``mutation_result`` always returns the four canonical fields."""
    payload = mutation_result(
        status="success",
        operation="create",
        channel_id=42,
        channel_name="general",
    )
    assert payload == {
        "status": "success",
        "channel_id": 42,
        "channel_name": "general",
        "operation": "create",
    }


def test_mutation_result_merges_extra_fields() -> None:
    """Operation-specific extras (e.g. ``type``) merge into the result."""
    payload = mutation_result(
        status="success",
        operation="create",
        channel_id=42,
        channel_name="general",
        extra={"type": "public"},
    )
    assert payload["type"] == "public"
    assert payload["status"] == "success"


def test_bulk_mutation_result_success_status() -> None:
    """Bulk results with only successes derive ``status == 'success'``."""
    payload = bulk_mutation_result(
        operation="subscribe",
        channel_id=42,
        channel_name="general",
        results=[{"user": "a", "status": "subscribed"}],
        errors=[],
    )
    assert payload["status"] == "success"
    assert payload["results"] == [{"user": "a", "status": "subscribed"}]
    assert payload["errors"] == []


def test_bulk_mutation_result_partial_status() -> None:
    """A mix of results and errors derives ``status == 'partial'``."""
    payload = bulk_mutation_result(
        operation="subscribe",
        channel_id=42,
        channel_name="general",
        results=[{"user": "a", "status": "subscribed"}],
        errors=[{"user": "b", "error": "not found"}],
    )
    assert payload["status"] == "partial"


def test_bulk_mutation_result_error_status() -> None:
    """All-error bulk results derive ``status == 'error'``."""
    payload = bulk_mutation_result(
        operation="subscribe",
        channel_id=42,
        channel_name="general",
        results=[],
        errors=[{"user": "b", "error": "not found"}],
    )
    assert payload["status"] == "error"


# ---------------------------------------------------------------------------
# T020 — channel list command
# ---------------------------------------------------------------------------


_LIST_RESPONSE = {
    "result": "success",
    "streams": [
        {
            "stream_id": 1,
            "name": "general",
            "description": "General discussion",
            "invite_only": False,
            "is_web_public": False,
            "is_archived": False,
            "subscriber_count": 42,
        },
        {
            "stream_id": 2,
            "name": "secret",
            "description": "private things",
            "invite_only": True,
            "is_web_public": False,
            "is_archived": False,
            "subscriber_count": 5,
        },
    ],
}


def _patched_channel_client(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> mock.MagicMock:
    """Patch ``get_client`` and return the fake client used by tests."""
    fake = mock.MagicMock()
    fake.call_endpoint.return_value = response
    monkeypatch.setattr(zulip_mod, "get_client", lambda **_kw: fake)
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    return fake


def test_channel_list_table_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default invocation prints a table with the documented columns."""
    _patched_channel_client(monkeypatch, _LIST_RESPONSE)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list"])
    assert result.exit_code == 0, result.stdout
    assert "Name" in result.stdout
    assert "Description" in result.stdout
    assert "Type" in result.stdout
    assert "Subscribers" in result.stdout
    assert "general" in result.stdout
    assert "secret" in result.stdout
    # Status column is hidden unless --include-archived
    assert "Status" not in result.stdout


def test_channel_list_json_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--json`` emits the documented envelope with normalized fields."""
    _patched_channel_client(monkeypatch, _LIST_RESPONSE)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--json", "channel", "list"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "channels" in payload
    by_id = {c["stream_id"]: c for c in payload["channels"]}
    assert by_id[1]["type"] == "public"
    assert by_id[2]["type"] == "private"
    assert by_id[1]["subscriber_count"] == 42
    assert by_id[1]["is_archived"] is False


def test_channel_list_accepts_global_zuliprc(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--zuliprc`` is accepted before the channel subcommands."""
    seen: dict[str, Any] = {}
    fake = mock.MagicMock()
    fake.call_endpoint.return_value = {"result": "success", "streams": []}

    def _get_client(**kwargs: Any) -> mock.MagicMock:
        seen.update(kwargs)
        return fake

    monkeypatch.setattr(zulip_mod, "get_client", _get_client)
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--zuliprc", "custom.rc", "channel", "list"])

    assert result.exit_code == 0, result.stdout
    assert str(seen["zuliprc"]) == "custom.rc"


def test_channel_list_include_archived_adds_status_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--include-archived`` adds Status, includes archived rows, and
    propagates ``include_archived=True`` to the underlying API call."""
    active = list(_LIST_RESPONSE["streams"])
    archived_extra = {
        "stream_id": 9,
        "name": "old",
        "description": "",
        "invite_only": False,
        "is_web_public": False,
        "is_archived": True,
        "subscriber_count": 0,
    }
    fake = mock.MagicMock()

    def _side_effect(*, url: str, method: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        assert url == "streams"
        assert method == "GET"
        if request and request.get("include_archived"):
            return {"result": "success", "streams": active + [archived_extra]}
        return {"result": "success", "streams": active}

    fake.call_endpoint.side_effect = _side_effect
    monkeypatch.setattr(zulip_mod, "get_client", lambda **_kw: fake)
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)

    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list", "--include-archived"])
    assert result.exit_code == 0, result.stdout
    assert "Status" in result.stdout
    assert "old" in result.stdout
    assert "archived" in result.stdout
    # The CLI must have propagated the flag to the API request.
    seen_archived = any(
        (call.kwargs.get("request") or {}).get("include_archived") is True for call in fake.call_endpoint.call_args_list
    )
    assert seen_archived, "expected --include-archived to set include_archived=True on the API request"


def test_channel_list_blocked_without_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the zulip extra is missing, the FR-022 guard fires (exit code 1)."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: False)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list"])
    assert result.exit_code == 1
    assert "zulip extra" in result.stderr or "zulip extra" in result.stdout


def test_channel_list_empty_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty channel list still prints headers and exits 0."""
    _patched_channel_client(monkeypatch, {"result": "success", "streams": []})
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list"])
    assert result.exit_code == 0, result.stdout
    assert "Name" in result.stdout
    assert "general" not in result.stdout


def test_channel_list_empty_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--json`` on an empty server returns ``{"channels": []}``."""
    _patched_channel_client(monkeypatch, {"result": "success", "streams": []})
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--json", "channel", "list"])
    assert result.exit_code == 0, result.stdout
    assert json.loads(result.stdout) == {"channels": []}


def test_channel_list_config_error_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ZulipConfigError`` from ``get_client`` is rendered via emit_error."""

    def _raise(**_kw: Any) -> Any:
        raise ZulipConfigError("zuliprc not found at any of the expected paths")

    monkeypatch.setattr(zulip_mod, "get_client", _raise)
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list"])
    assert result.exit_code == 1
    combined = result.stdout + result.stderr
    assert "zuliprc not found" in combined
    assert "Error:" in combined


# ---------------------------------------------------------------------------
# T024 — ``user list`` CLI
# ---------------------------------------------------------------------------


def _patched_user_client(monkeypatch: pytest.MonkeyPatch, members: list[dict[str, Any]]) -> mock.MagicMock:
    """Patch ``zulip_available``/``get_client`` so the CLI runs end-to-end."""
    client = mock.MagicMock()
    client.get_members.return_value = {"result": "success", "members": members}
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    monkeypatch.setattr(zulip_mod, "get_client", lambda **_kw: client)
    return client


CLI_MEMBERS = [
    {
        "user_id": 10,
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "is_bot": False,
        "is_active": True,
    },
    {
        "user_id": 11,
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "is_bot": False,
        "is_active": False,
    },
    {
        "user_id": 12,
        "full_name": "Welcome Bot",
        "email": "welcome-bot@example.com",
        "is_bot": True,
        "is_active": True,
    },
]


def test_user_list_table_default(monkeypatch: pytest.MonkeyPatch) -> None:
    """``user list`` default renders a table of active human users only."""
    _patched_user_client(monkeypatch, CLI_MEMBERS)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["user", "list"])
    assert result.exit_code == 0, result.stdout
    # Header order matches contracts/cli-commands.md: Full Name, Email, User ID.
    assert "Full Name" in result.stdout
    assert "Email" in result.stdout
    assert "User ID" in result.stdout
    assert result.stdout.index("Full Name") < result.stdout.index("Email") < result.stdout.index("User ID")
    # Optional columns are omitted unless the corresponding flag is set.
    assert "Bot" not in result.stdout
    assert "Deactivated" not in result.stdout
    assert "Alice Smith" in result.stdout
    assert "alice@example.com" in result.stdout
    assert "10" in result.stdout
    # Bots and deactivated users are excluded by default.
    assert "Bob Jones" not in result.stdout
    assert "Welcome Bot" not in result.stdout


def test_user_list_table_optional_columns(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--include-bots`` / ``--include-deactivated`` add labeled columns."""
    _patched_user_client(monkeypatch, CLI_MEMBERS)
    runner = CliRunner()
    result = runner.invoke(
        zulip_app,
        ["user", "list", "--include-bots", "--include-deactivated"],
    )
    assert result.exit_code == 0, result.stdout
    assert "Bot" in result.stdout
    assert "Deactivated" in result.stdout


def test_user_list_json_envelope(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--json`` emits the canonical ``{"users": [...]}`` envelope."""
    _patched_user_client(monkeypatch, CLI_MEMBERS)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--json", "user", "list"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert "users" in payload
    assert len(payload["users"]) == 1
    user = payload["users"][0]
    assert user == {
        "user_id": 10,
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "is_bot": False,
        "is_active": True,
    }


def test_user_list_include_bots(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--include-bots`` adds bot accounts to the output."""
    _patched_user_client(monkeypatch, CLI_MEMBERS)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--json", "user", "list", "--include-bots"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    ids = sorted(u["user_id"] for u in payload["users"])
    assert ids == [10, 12]


def test_user_list_include_deactivated(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--include-deactivated`` adds deactivated humans to the output."""
    _patched_user_client(monkeypatch, CLI_MEMBERS)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--json", "user", "list", "--include-deactivated"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    ids = sorted(u["user_id"] for u in payload["users"])
    assert ids == [10, 11]


def test_user_list_accepts_global_zuliprc(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--zuliprc`` is accepted before the user subcommands."""
    seen: dict[str, Any] = {}
    client = mock.MagicMock()
    client.get_members.return_value = {"result": "success", "members": []}

    def _get_client(**kwargs: Any) -> mock.MagicMock:
        seen.update(kwargs)
        return client

    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    monkeypatch.setattr(zulip_mod, "get_client", _get_client)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--zuliprc", "custom.rc", "user", "list"])

    assert result.exit_code == 0, result.stdout
    assert str(seen["zuliprc"]) == "custom.rc"


def test_user_list_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty members response renders an empty JSON envelope."""
    _patched_user_client(monkeypatch, [])
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--json", "user", "list"])
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
    assert payload == {"users": []}


def test_user_list_config_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Config errors are surfaced via the canonical ``Error:`` channel."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)

    def boom(**_kw: Any) -> Any:
        raise ZulipConfigError("no zuliprc found")

    monkeypatch.setattr(zulip_mod, "get_client", boom)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["user", "list"])
    assert result.exit_code == 1
    # Click/Typer split stderr separately on some versions and mix it
    # into stdout on others; check both to remain robust.
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "Error" in combined
    assert "no zuliprc found" in combined


def test_user_list_missing_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the optional extra is missing, invoking ``user list`` errors."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: False)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["user", "list"])
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "zulip extra" in combined


# ---------------------------------------------------------------------------
# T028 — ``zulip group list`` (US3)
# ---------------------------------------------------------------------------


_FAKE_GROUPS = [
    {
        "group_id": 10,
        "name": "engineering",
        "description": "Engineering team",
        "member_count": 15,
        "type": "custom",
    },
    {
        "group_id": 21,
        "name": "Administrators",
        "description": "Administrators of this organization",
        "member_count": 3,
        "type": "system",
    },
]


def _invoke_group_list(
    args: list[str],
    *,
    list_groups_return: Any = None,
    list_groups_exc: BaseException | None = None,
    get_client_exc: BaseException | None = None,
) -> Any:
    """Invoke ``zulip group list`` with the API layer fully mocked."""
    runner = CliRunner()
    global_args: list[str] = []
    command_args = list(args)
    if "--json" in command_args:
        command_args.remove("--json")
        global_args.append("--json")
    with (
        mock.patch.object(zulip_mod, "get_client") as get_client_mock,
        mock.patch.object(zulip_mod, "list_groups") as list_groups_mock,
        mock.patch.object(zulip_mod, "zulip_available", return_value=True),
    ):
        if get_client_exc is not None:
            get_client_mock.side_effect = get_client_exc
        else:
            get_client_mock.return_value = mock.MagicMock()
        if list_groups_exc is not None:
            list_groups_mock.side_effect = list_groups_exc
        else:
            list_groups_mock.return_value = list_groups_return or []
        result = runner.invoke(zulip_app, [*global_args, "group", "list", *command_args])
        return result, list_groups_mock


def test_group_list_table_output() -> None:
    """Default table output renders the expected column headers and rows."""
    result, _ = _invoke_group_list([], list_groups_return=_FAKE_GROUPS)
    assert result.exit_code == 0, result.stdout
    assert "engineering" in result.stdout
    assert "Administrators" in result.stdout
    # Required columns from the contract.
    for header in ("Name", "Group ID", "Type", "Description", "Members"):
        assert header in result.stdout


def test_group_list_json_output_schema() -> None:
    """``--json`` emits the standard ``{"groups": [...]}`` schema."""
    result, _ = _invoke_group_list(["--json"], list_groups_return=_FAKE_GROUPS)
    assert result.exit_code == 0, result.stdout
    payload = _json.loads(result.stdout)
    assert set(payload.keys()) == {"groups"}
    assert payload["groups"] == _FAKE_GROUPS


def test_group_list_passes_group_name_filter() -> None:
    """``--group-name`` is forwarded to the API helper as ``group_name``."""
    _, list_mock = _invoke_group_list(
        ["--group-name", "engineering"],
        list_groups_return=[_FAKE_GROUPS[0]],
    )
    _, kwargs = list_mock.call_args
    assert kwargs.get("group_name") == "engineering"
    assert kwargs.get("group_id") is None


def test_group_list_passes_group_id_filter() -> None:
    """``--group-id`` is forwarded to the API helper as ``group_id``."""
    _, list_mock = _invoke_group_list(
        ["--group-id", "21"],
        list_groups_return=[_FAKE_GROUPS[1]],
    )
    _, kwargs = list_mock.call_args
    assert kwargs.get("group_id") == 21
    assert kwargs.get("group_name") is None


def test_group_list_accepts_global_zuliprc() -> None:
    """``--zuliprc`` is accepted before the group subcommands."""
    runner = CliRunner()
    with (
        mock.patch.object(zulip_mod, "get_client") as get_client_mock,
        mock.patch.object(zulip_mod, "list_groups", return_value=[]),
        mock.patch.object(zulip_mod, "zulip_available", return_value=True),
    ):
        get_client_mock.return_value = mock.MagicMock()
        result = runner.invoke(zulip_app, ["--zuliprc", "custom.rc", "group", "list"])

    assert result.exit_code == 0, result.stdout
    _, kwargs = get_client_mock.call_args
    assert str(kwargs["zuliprc"]) == "custom.rc"


def test_group_list_ambiguity_error_display() -> None:
    """A ``ZulipAmbiguityError`` from the API surfaces with exit code 1."""
    exc = ZulipAmbiguityError(
        "Group name 'design' matched 2 groups",
        matches=[
            {"group_id": 11, "name": "design"},
            {"group_id": 12, "name": "Design"},
        ],
    )
    result, _ = _invoke_group_list(["--group-name", "design"], list_groups_exc=exc)
    assert result.exit_code == 1
    assert "design" in result.stderr.lower()


def test_group_list_config_error_display() -> None:
    """A ``ZulipConfigError`` from ``get_client`` is surfaced cleanly."""
    result, _ = _invoke_group_list(
        [],
        get_client_exc=ZulipConfigError("No Zulip configuration found."),
    )
    assert result.exit_code == 1
    assert "No Zulip configuration" in result.stderr


def test_group_list_help_renders() -> None:
    """``zulip group list --help`` produces usable help text."""
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["group", "list", "--help"])
    assert result.exit_code == 0
    assert "--group-name" in result.stdout
    assert "--group-id" in result.stdout
