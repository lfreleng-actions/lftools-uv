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
from lftools_uv.api.endpoints.zulip import (
    ZulipAmbiguityError,
    ZulipConfigError,
)
from lftools_uv.typer_apps.zulip import (
    MISSING_EXTRA_MESSAGE,
    bulk_mutation_result,
    mutation_result,
    zulip_app,
)
from tests.test_utils import clean_cli_output


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
    json_output: bool = False,
    list_groups_return: Any = None,
    list_groups_exc: BaseException | None = None,
    get_client_exc: BaseException | None = None,
) -> Any:
    """Invoke ``zulip group list`` with the API layer fully mocked."""
    runner = CliRunner()
    global_args = ["--json"] if json_output else []
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
        result = runner.invoke(zulip_app, [*global_args, "group", "list", *args])
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
    """Global ``--json`` emits the standard ``{"groups": [...]}`` schema."""
    result, _ = _invoke_group_list([], json_output=True, list_groups_return=_FAKE_GROUPS)
    assert result.exit_code == 0, result.stdout
    payload = json.loads(result.stdout)
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
    """A ``ZulipAmbiguityError`` from the API surfaces with exit code 1.

    The per-spec contract requires that the matches list (group IDs +
    names) is rendered to stderr so the user can pick one for
    ``--group-id``.
    """
    exc = ZulipAmbiguityError(
        "Group name 'design' matched 2 groups",
        matches=[
            {"group_id": 11, "name": "design"},
            {"group_id": 12, "name": "Design"},
        ],
    )
    result, _ = _invoke_group_list(["--group-name", "design"], list_groups_exc=exc)
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "design" in combined.lower()
    # Matches list rendered with both ids.
    assert "11" in combined
    assert "12" in combined


def test_group_list_config_error_display() -> None:
    """A ``ZulipConfigError`` from ``get_client`` is surfaced cleanly."""
    result, _ = _invoke_group_list(
        [],
        get_client_exc=ZulipConfigError("No Zulip configuration found."),
    )
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "No Zulip configuration" in combined


def test_group_list_help_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    """``zulip group list --help`` produces usable help text."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    runner = CliRunner()
    result = runner.invoke(
        zulip_app,
        ["group", "list", "--help"],
        env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"},
    )
    assert result.exit_code == 0
    cleaned = clean_cli_output(result.stdout)
    assert "--group-name" in cleaned
    assert "--group-id" in cleaned


# ---------------------------------------------------------------------------
# T032 — ``zulip channel create`` (US4)
# ---------------------------------------------------------------------------


CREATE_STREAMS = [
    {"stream_id": 100, "name": "new-project", "description": "", "is_archived": False},
]

CREATE_MEMBERS = [
    {
        "user_id": 10,
        "full_name": "Alice Smith",
        "email": "alice@example.com",
        "delivery_email": "alice@example.com",
        "is_bot": False,
        "is_active": True,
    },
    {
        "user_id": 11,
        "full_name": "Bob Jones",
        "email": "bob@example.com",
        "delivery_email": "bob@example.com",
        "is_bot": False,
        "is_active": True,
    },
]

CREATE_CLI_GROUPS = [
    {"id": 10, "name": "engineering", "is_system_group": False, "members": [1, 2]},
    {"id": 20, "name": "role:administrators", "is_system_group": True, "members": [1]},
    {"id": 21, "name": "role:nobody", "is_system_group": True, "members": []},
    {"id": 22, "name": "role:members", "is_system_group": True, "members": [1, 2, 3]},
]


def _create_cli_client(
    *,
    feature_level: int = 400,
    streams: list[dict[str, Any]] | None = None,
    members: list[dict[str, Any]] | None = None,
    groups: list[dict[str, Any]] | None = None,
    subscribe_response: dict[str, Any] | None = None,
) -> Any:
    """Return a mock client for channel create CLI tests."""
    client = mock.MagicMock()
    client.get_server_settings.return_value = {
        "result": "success",
        "zulip_feature_level": feature_level,
    }
    client.get_members.return_value = {
        "result": "success",
        "members": members or CREATE_MEMBERS,
    }

    def call_endpoint_side_effect(*, url: str, method: str, request: Any = None) -> Any:
        if url == "users/me/subscriptions" and method == "POST":
            return subscribe_response or {"result": "success", "subscribed": {}}
        if url == "streams" and method == "GET":
            return {"result": "success", "streams": streams or CREATE_STREAMS}
        if url == "user_groups" and method == "GET":
            return {"result": "success", "user_groups": groups or CREATE_CLI_GROUPS}
        if url.startswith("streams/") and method == "PATCH":
            return {"result": "success"}
        return {"result": "error", "msg": f"unexpected endpoint: {url}"}

    client.call_endpoint.side_effect = call_endpoint_side_effect
    return client


def _invoke_create(
    args: list[str],
    *,
    client: Any = None,
    feature_level: int = 400,
    json_output: bool = False,
) -> Any:
    """Invoke ``zulip channel create`` with mocked API layer."""
    runner = CliRunner()
    global_args = ["--json"] if json_output else []
    if client is None:
        client = _create_cli_client(feature_level=feature_level)
    with (
        mock.patch.object(zulip_mod, "get_client", return_value=client),
        mock.patch.object(zulip_mod, "zulip_available", return_value=True),
    ):
        result = runner.invoke(zulip_app, [*global_args, "channel", "create", *args])
        return result


def test_channel_create_public_success() -> None:
    """Public channel creation succeeds with just a name."""
    result = _invoke_create(["new-project"])
    assert result.exit_code == 0, result.output
    assert "Created public channel" in result.output or "new-project" in result.output


def test_channel_create_public_json_output() -> None:
    """``--json`` output follows the mutation result schema."""
    result = _invoke_create(["new-project"], json_output=True)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"
    assert payload["channel_name"] == "new-project"
    assert payload["operation"] == "create"
    assert payload["type"] == "public"
    assert "channel_id" in payload


def test_channel_create_private_with_subscribe() -> None:
    """Private channel with --subscribe succeeds (lockout prevention met)."""
    result = _invoke_create(
        [
            "new-project",
            "--type",
            "private",
            "--subscribe",
            "alice@example.com",
            "--by-email",
        ]
    )
    assert result.exit_code == 0, result.output


def test_channel_create_private_without_subscribers_fails() -> None:
    """Private channel without subscribers raises lockout error."""
    result = _invoke_create(["new-project", "--type", "private"])
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "lockout" in combined.lower() or "subscribe" in combined.lower()


def test_channel_create_private_with_allow_group() -> None:
    """Private channel with --allow-group (non-Nobody) succeeds."""
    result = _invoke_create(
        [
            "new-project",
            "--type",
            "private",
            "--allow-group",
            "engineering",
        ]
    )
    assert result.exit_code == 0, result.output


def test_channel_create_private_with_nobody_fails() -> None:
    """Private channel with --allow-group Nobody fails lockout prevention."""
    result = _invoke_create(
        [
            "new-project",
            "--type",
            "private",
            "--allow-group",
            "Nobody",
        ]
    )
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "nobody" in combined.lower() or "lockout" in combined.lower()


def test_channel_create_announce_mutex() -> None:
    """--announce and --no-announce are mutually exclusive."""
    result = _invoke_create(["new-project", "--announce", "--no-announce"])
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "mutually exclusive" in combined.lower()


def test_channel_create_invalid_topic_policy() -> None:
    """Invalid --topic-policy value is rejected."""
    result = _invoke_create(["new-project", "--topic-policy", "invalid"])
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "invalid" in combined.lower() or "topic-policy" in combined.lower()


def test_channel_create_valid_topic_policies() -> None:
    """All valid --topic-policy values are accepted."""
    for policy in ["allow", "deny", "follow-default"]:
        result = _invoke_create(["new-project", "--topic-policy", policy])
        assert result.exit_code == 0, f"Failed for policy={policy}: {result.output}"


def test_channel_create_web_public_feature_level_error() -> None:
    """Web-public channel fails when feature level is too low."""
    result = _invoke_create(
        ["new-project", "--type", "web-public"],
        feature_level=10,
    )
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "feature level" in combined.lower()


def test_channel_create_invalid_type() -> None:
    """Invalid --type value is rejected."""
    result = _invoke_create(["new-project", "--type", "invalid"])
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "invalid" in combined.lower() or "type" in combined.lower()


def test_channel_create_subscribe_requires_id_mode() -> None:
    """--subscribe requires one of --by-email/--by-id/--by-name."""
    result = _invoke_create(
        [
            "new-project",
            "--type",
            "private",
            "--subscribe",
            "alice@example.com",
        ]
    )
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "by-email" in combined.lower() or "by-id" in combined.lower()


def test_channel_create_id_mode_mutex() -> None:
    """--by-email, --by-id, and --by-name are mutually exclusive."""
    result = _invoke_create(
        [
            "new-project",
            "--type",
            "private",
            "--subscribe",
            "alice@example.com",
            "--by-email",
            "--by-id",
        ]
    )
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "mutually exclusive" in combined.lower()


def test_channel_create_with_description() -> None:
    """--description is passed to the channel."""
    result = _invoke_create(["new-project", "--description", "Test channel"], json_output=True)
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert payload["status"] == "success"


def test_channel_create_can_remove_subscribers_group() -> None:
    """--can-remove-subscribers-group is accepted."""
    result = _invoke_create(
        [
            "new-project",
            "--can-remove-subscribers-group",
            "Administrators",
        ]
    )
    assert result.exit_code == 0, result.output


def test_channel_create_user_ambiguity_error() -> None:
    """Ambiguous user name raises error with match listing."""
    # Create members with duplicate names
    ambiguous_members = [
        {
            "user_id": 10,
            "full_name": "Alice Smith",
            "email": "alice@example.com",
            "delivery_email": "alice@example.com",
            "is_bot": False,
            "is_active": True,
        },
        {
            "user_id": 11,
            "full_name": "Alice Smith",
            "email": "alice2@example.com",
            "delivery_email": "alice2@example.com",
            "is_bot": False,
            "is_active": True,
        },
    ]
    client = _create_cli_client(members=ambiguous_members)
    result = _invoke_create(
        [
            "new-project",
            "--type",
            "private",
            "--subscribe",
            "Alice Smith",
            "--by-name",
        ],
        client=client,
    )
    assert result.exit_code == 1
    combined = result.output + (getattr(result, "stderr", "") or "")
    assert "ambig" in combined.lower() or "alice" in combined.lower()


def test_channel_create_help_renders(monkeypatch: pytest.MonkeyPatch) -> None:
    """``zulip channel create --help`` produces usable help text."""
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    runner = CliRunner()
    result = runner.invoke(
        zulip_app,
        ["channel", "create", "--help"],
        env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"},
    )
    assert result.exit_code == 0, result.output
    cleaned = clean_cli_output(result.output)
    assert "--type" in cleaned
    assert "--subscribe" in cleaned
    assert "--allow-group" in cleaned
    assert "--announce" in cleaned
    assert "--topic-policy" in cleaned


# ---------------------------------------------------------------------------
# T036 — `channel subscribe` CLI (US5)
# ---------------------------------------------------------------------------


def _invoke_subscribe(
    args,
    subscribe_return=None,
    subscribe_side_effect=None,
    resolve_channel_return=None,
    resolve_channel_side_effect=None,
):
    """Invoke ``zulip channel subscribe`` with API helpers patched.

    The CLI pre-resolves the channel so ``--json`` error payloads can
    include accurate channel context. Tests patch both ``resolve_channel``
    and ``subscribe_users``.
    """
    runner = CliRunner()
    command_args = list(args)
    global_args: list[str] = []
    if "--json" in command_args:
        command_args.remove("--json")
        global_args.append("--json")
    with (
        mock.patch("lftools_uv.typer_apps.zulip.get_client") as get_client,
        mock.patch("lftools_uv.typer_apps.zulip.resolve_channel") as resolve_chan,
        mock.patch("lftools_uv.typer_apps.zulip.subscribe_users") as subscribe,
        mock.patch("lftools_uv.typer_apps.zulip.zulip_available", return_value=True),
    ):
        get_client.return_value = mock.MagicMock()
        if resolve_channel_side_effect is not None:
            resolve_chan.side_effect = resolve_channel_side_effect
        else:
            resolve_chan.return_value = resolve_channel_return or {
                "stream_id": 42,
                "name": "general",
            }
        if subscribe_side_effect is not None:
            subscribe.side_effect = subscribe_side_effect
        else:
            subscribe.return_value = subscribe_return
        result = runner.invoke(zulip_app, [*global_args, "channel", "subscribe", *command_args])
    return result, subscribe


def _bulk_ok(channel_id=42, channel_name="general", users=("bob@example.com",)):
    return {
        "status": "success",
        "channel_id": channel_id,
        "channel_name": channel_name,
        "operation": "subscribe",
        "results": [{"user": u, "status": "subscribed"} for u in users],
        "errors": [],
    }


def test_channel_subscribe_single_email_success() -> None:
    """`channel subscribe general bob@example.com --by-email` succeeds."""
    result, sub = _invoke_subscribe(
        ["general", "bob@example.com", "--by-email"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0, result.stderr
    # subscribe_users was called with channel='general' and one user.
    args, kwargs = sub.call_args
    # Allow either positional or keyword passing.
    call = {**dict(zip(["client", "channel", "users", "id_mode"], args, strict=False)), **kwargs}
    assert call["channel"] == "general"
    assert list(call["users"]) == ["bob@example.com"]
    assert call["id_mode"] == "email"


def test_channel_subscribe_bulk_users() -> None:
    """Multiple positional users are all passed to subscribe_users."""
    result, sub = _invoke_subscribe(
        ["general", "a@x.com", "b@x.com", "c@x.com", "--by-email"],
        subscribe_return=_bulk_ok(users=("a@x.com", "b@x.com", "c@x.com")),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = sub.call_args
    call = {**dict(zip(["client", "channel", "users", "id_mode"], args, strict=False)), **kwargs}
    assert list(call["users"]) == ["a@x.com", "b@x.com", "c@x.com"]


def test_channel_subscribe_by_id_flag() -> None:
    """`--by-id` is forwarded as id_mode='id'."""
    result, sub = _invoke_subscribe(
        ["general", "200", "--by-id"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = sub.call_args
    call = {**dict(zip(["client", "channel", "users", "id_mode"], args, strict=False)), **kwargs}
    assert call["id_mode"] == "id"


def test_channel_subscribe_by_name_flag() -> None:
    """`--by-name` is forwarded as id_mode='name'."""
    result, sub = _invoke_subscribe(
        ["general", "Bob Jones", "--by-name"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = sub.call_args
    call = {**dict(zip(["client", "channel", "users", "id_mode"], args, strict=False)), **kwargs}
    assert call["id_mode"] == "name"


def test_channel_subscribe_missing_identifier_flag_errors() -> None:
    """Omitting all of --by-email/--by-id/--by-name exits with code 1.

    The implementation routes this through ``emit_error()`` +
    ``typer.Exit(1)`` to honour the cli-commands.md contract (exit
    codes 0/1 only — never Click's default 2 for usage errors). We
    don't assert on the error message text because Rich-panel rendering
    on CI may wrap/truncate it; the exit code is the contract.
    """
    result, _ = _invoke_subscribe(
        ["general", "bob@example.com"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 1


def test_channel_subscribe_multiple_identifier_flags_errors() -> None:
    """Specifying more than one of the identifier flags exits with code 1."""
    result, _ = _invoke_subscribe(
        ["general", "bob@example.com", "--by-email", "--by-id"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 1


def test_channel_subscribe_ambiguity_error_exits_1() -> None:
    """A ZulipAmbiguityError from the API surfaces as exit-code 1."""
    import lftools_uv.api.endpoints.zulip as zulip_api

    result, _ = _invoke_subscribe(
        ["general", "Alice Smith", "--by-name"],
        subscribe_side_effect=zulip_api.ZulipAmbiguityError(
            "User name 'Alice Smith' matched 2 users; use --by-email or --by-id to disambiguate"
        ),
    )
    assert result.exit_code == 1
    combined = (result.stdout or "") + (result.stderr or "")
    assert "Alice Smith" in combined


def test_channel_subscribe_already_subscribed_noop_exit_0() -> None:
    """An all-already-subscribed result still exits 0."""
    result, _ = _invoke_subscribe(
        ["general", "bob@example.com", "--by-email"],
        subscribe_return={
            "status": "success",
            "channel_id": 42,
            "channel_name": "general",
            "operation": "subscribe",
            "results": [{"user": "bob@example.com", "status": "already_subscribed"}],
            "errors": [],
        },
    )
    assert result.exit_code == 0, result.stderr


def test_channel_subscribe_partial_exits_1() -> None:
    """Partial results (some errors) exit with code 1."""
    result, _ = _invoke_subscribe(
        ["general", "a@x.com", "b@x.com", "--by-email"],
        subscribe_return={
            "status": "partial",
            "channel_id": 42,
            "channel_name": "general",
            "operation": "subscribe",
            "results": [{"user": "a@x.com", "status": "subscribed"}],
            "errors": [{"user": "b@x.com", "error": "unauthorized"}],
        },
    )
    assert result.exit_code == 1


def test_channel_subscribe_json_bulk_output() -> None:
    """`--json` emits the bulk-mutation payload verbatim."""
    payload = _bulk_ok(users=("a@x.com", "b@x.com"))
    result, _ = _invoke_subscribe(
        ["general", "a@x.com", "b@x.com", "--by-email", "--json"],
        subscribe_return=payload,
    )
    assert result.exit_code == 0, result.stderr
    parsed = json.loads(result.stdout)
    assert parsed["operation"] == "subscribe"
    assert parsed["channel_name"] == "general"
    assert {r["user"] for r in parsed["results"]} == {"a@x.com", "b@x.com"}


def test_channel_subscribe_channel_id_flag_uses_id() -> None:
    """`--channel-id` passes the int ID; all positionals are USERs."""
    result, sub = _invoke_subscribe(
        ["--channel-id", "42", "bob@example.com", "--by-email"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = sub.call_args
    call = {**dict(zip(["client", "channel", "users", "id_mode"], args, strict=False)), **kwargs}
    assert call["channel"] == 42
    assert list(call["users"]) == ["bob@example.com"]


def test_channel_subscribe_numeric_channel_name_treated_as_name() -> None:
    """A positional channel like '123' is forwarded as a NAME string, not an id."""
    result, sub = _invoke_subscribe(
        ["123", "bob@example.com", "--by-email"],
        subscribe_return=_bulk_ok(channel_id=99, channel_name="123"),
    )
    assert result.exit_code == 0, result.stderr
    args, kwargs = sub.call_args
    call = {**dict(zip(["client", "channel", "users", "id_mode"], args, strict=False)), **kwargs}
    # CLI must NOT coerce the positional to int; the API layer accepts only
    # ints for id-mode resolution.
    assert call["channel"] == "123"
    assert isinstance(call["channel"], str)


def test_channel_subscribe_channel_without_users_errors() -> None:
    """A single positional (channel only) with no USER args exits with code 1.

    The contract requires at least one USER positional whenever
    ``--channel-id`` is absent. Click parses ``['general']`` as a single
    positional → the CLI sees one entry, no USERs, and aborts via
    ``typer.Exit(1)`` (NOT Click's default 2 for usage errors), per
    the cli-commands.md contract.
    """
    result, _ = _invoke_subscribe(
        ["general", "--by-email"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 1


def test_channel_subscribe_channel_id_with_zero_users_errors() -> None:
    """`--channel-id` with no USER positionals is a Click usage error.

    With ``--channel-id``, ALL positionals are interpreted as USERs (per
    the contract). Zero USERs must exit with code ``1`` (the contract
    documents exit codes 0/1 only); we explicitly route this through
    :func:`typer.Exit` rather than letting Click's required-argument
    check exit with code 2.
    """
    result, _ = _invoke_subscribe(
        ["--channel-id", "42", "--by-email"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 1


def test_channel_subscribe_include_archived_forwarded() -> None:
    """`--include-archived` is forwarded to subscribe_users as a kwarg."""
    result, sub = _invoke_subscribe(
        ["general", "bob@example.com", "--by-email", "--include-archived"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0, result.stderr
    _, kwargs = sub.call_args
    assert kwargs.get("include_archived") is True


def test_channel_subscribe_include_archived_default_false() -> None:
    """Without `--include-archived`, the flag defaults to False on the API."""
    result, sub = _invoke_subscribe(
        ["general", "bob@example.com", "--by-email"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0, result.stderr
    _, kwargs = sub.call_args
    assert kwargs.get("include_archived") is False


def test_channel_subscribe_json_channel_not_found() -> None:
    """`--json` with an unknown channel emits a structured error payload.

    Contract: ``status='error'``, ``channel_id=null`` (when channel was
    looked up by name), ``channel_name=<requested>``, empty ``results``,
    and a single descriptive ``errors`` entry. Exits 1.
    """
    import lftools_uv.api.endpoints.zulip as zulip_api

    result, _ = _invoke_subscribe(
        ["unknown-channel", "bob@example.com", "--by-email", "--json"],
        resolve_channel_side_effect=zulip_api.ZulipNotFoundError("Channel 'unknown-channel' not found"),
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["channel_id"] is None
    assert payload["channel_name"] == "unknown-channel"
    assert payload["operation"] == "subscribe"
    assert payload["results"] == []
    assert len(payload["errors"]) == 1
    assert "unknown-channel" in payload["errors"][0]["error"]


def test_channel_subscribe_json_channel_id_not_found() -> None:
    """`--json` with an unknown numeric channel-id reports ``channel_id=null``.

    Per FR-008 / data-model.md, ``channel_id`` must be ``None`` when the
    target channel cannot be resolved — even if the caller supplied a
    numeric ``--channel-id``. The schema reserves ``channel_id`` for
    successfully-resolved channels only.
    """
    import lftools_uv.api.endpoints.zulip as zulip_api

    result, _ = _invoke_subscribe(
        ["--channel-id", "9999", "bob@example.com", "--by-email", "--json"],
        resolve_channel_side_effect=zulip_api.ZulipNotFoundError("No channel with id 9999"),
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["channel_id"] is None
    assert payload["operation"] == "subscribe"


def test_channel_subscribe_json_user_resolution_error_keeps_channel_context() -> None:
    """`--json` error AFTER channel resolves preserves channel context.

    When the channel resolves successfully but a downstream failure
    (e.g. user resolution) raises, the structured ``--json`` payload
    MUST thread the resolved ``channel_id`` and ``channel_name``
    through — otherwise consumers lose the ability to correlate the
    error with its target stream.
    """
    import lftools_uv.api.endpoints.zulip as zulip_api

    result, _ = _invoke_subscribe(
        ["general", "ghost@example.com", "--by-email", "--json"],
        resolve_channel_return={"stream_id": 42, "name": "general"},
        subscribe_side_effect=zulip_api.ZulipNotFoundError("No user found matching 'ghost@example.com'"),
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    # Channel context is preserved because it was resolved before the
    # downstream user-resolution failure.
    assert payload["channel_id"] == 42
    assert payload["channel_name"] == "general"
    assert payload["results"] == []
    assert len(payload["errors"]) == 1


def test_channel_subscribe_json_ambiguity_surfaces_matches() -> None:
    """`--json` payload for ZulipAmbiguityError includes ``matches``."""
    import lftools_uv.api.endpoints.zulip as zulip_api

    matches = [
        {"user_id": 1, "email": "bob.smith@example.com", "full_name": "Bob"},
        {"user_id": 2, "email": "bob.jones@example.com", "full_name": "Bob"},
    ]
    result, _ = _invoke_subscribe(
        ["general", "Bob", "--by-name", "--json"],
        resolve_channel_return={"stream_id": 42, "name": "general"},
        subscribe_side_effect=zulip_api.ZulipAmbiguityError("Ambiguous full_name match for 'Bob'", matches=matches),
    )
    assert result.exit_code == 1
    payload = _json.loads(result.stdout)
    assert payload["status"] == "error"
    assert payload["channel_id"] == 42
    assert payload["errors"][0]["matches"] == matches


def test_channel_subscribe_human_mode_surfaces_ambiguity_matches() -> None:
    """Non-JSON ambiguity errors render the candidates as a table.

    The spec requires that the operator can see the disambiguation
    candidates (user_id / email / full_name) when a name lookup is
    ambiguous, not just a single-line error message.
    """
    import lftools_uv.api.endpoints.zulip as zulip_api

    matches = [
        {"user_id": 1, "email": "bob.smith@example.com", "full_name": "Bob"},
        {"user_id": 2, "email": "bob.jones@example.com", "full_name": "Bob"},
    ]
    result, _ = _invoke_subscribe(
        ["general", "Bob", "--by-name"],
        resolve_channel_return={"stream_id": 42, "name": "general"},
        subscribe_side_effect=zulip_api.ZulipAmbiguityError("Ambiguous full_name match for 'Bob'", matches=matches),
    )
    assert result.exit_code == 1
    # Both candidate emails must appear in the rendered output.
    out = result.stdout + result.output
    assert "bob.smith@example.com" in out
    assert "bob.jones@example.com" in out


def test_channel_subscribe_table_headers_title_cased() -> None:
    """Non-JSON success output uses title-cased headers (User, Status)."""
    result, _ = _invoke_subscribe(
        ["general", "bob@example.com", "--by-email"],
        subscribe_return=_bulk_ok(),
    )
    assert result.exit_code == 0
    assert "User" in result.stdout
    assert "Status" in result.stdout
