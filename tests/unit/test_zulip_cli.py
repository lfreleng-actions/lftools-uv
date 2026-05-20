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

import pytest
from typer.testing import CliRunner

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
    import lftools_uv.typer_apps.zulip as zulip_mod

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


from typing import Any  # noqa: E402
from unittest import mock  # noqa: E402

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


def _patched_client(monkeypatch: pytest.MonkeyPatch, response: dict[str, Any]) -> mock.MagicMock:
    """Patch ``get_client`` and return the fake client used by tests."""
    import lftools_uv.typer_apps.zulip as zulip_mod

    fake = mock.MagicMock()
    fake.call_endpoint.return_value = response
    monkeypatch.setattr(zulip_mod, "get_client", lambda **_kw: fake)
    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: True)
    return fake


def test_channel_list_table_output(monkeypatch: pytest.MonkeyPatch) -> None:
    """Default invocation prints a table with the documented columns."""
    _patched_client(monkeypatch, _LIST_RESPONSE)
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
    import json as _json

    _patched_client(monkeypatch, _LIST_RESPONSE)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    payload = _json.loads(result.stdout)
    assert "channels" in payload
    by_id = {c["stream_id"]: c for c in payload["channels"]}
    assert by_id[1]["type"] == "public"
    assert by_id[2]["type"] == "private"
    assert by_id[1]["subscriber_count"] == 42
    assert by_id[1]["is_archived"] is False


def test_channel_list_include_archived_adds_status_column(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """``--include-archived`` adds the Status column and includes archived rows."""
    archived = {
        "result": "success",
        "streams": list(_LIST_RESPONSE["streams"])
        + [
            {
                "stream_id": 9,
                "name": "old",
                "description": "",
                "invite_only": False,
                "is_web_public": False,
                "is_archived": True,
                "subscriber_count": 0,
            }
        ],
    }
    _patched_client(monkeypatch, archived)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list", "--include-archived"])
    assert result.exit_code == 0, result.stdout
    assert "Status" in result.stdout
    assert "old" in result.stdout
    assert "archived" in result.stdout


def test_channel_list_blocked_without_extra(monkeypatch: pytest.MonkeyPatch) -> None:
    """When the zulip extra is missing, the FR-022 guard fires (exit code 1)."""
    import lftools_uv.typer_apps.zulip as zulip_mod

    monkeypatch.setattr(zulip_mod, "zulip_available", lambda: False)
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list"])
    assert result.exit_code == 1
    assert "zulip extra" in result.stderr or "zulip extra" in result.stdout


def test_channel_list_empty_table(monkeypatch: pytest.MonkeyPatch) -> None:
    """An empty channel list still prints headers and exits 0."""
    _patched_client(monkeypatch, {"result": "success", "streams": []})
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list"])
    assert result.exit_code == 0, result.stdout
    assert "Name" in result.stdout
    assert "general" not in result.stdout


def test_channel_list_empty_json(monkeypatch: pytest.MonkeyPatch) -> None:
    """``--json`` on an empty server returns ``{\"channels\": []}``."""
    import json as _json

    _patched_client(monkeypatch, {"result": "success", "streams": []})
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["channel", "list", "--json"])
    assert result.exit_code == 0, result.stdout
    assert _json.loads(result.stdout) == {"channels": []}


def test_channel_list_config_error_surfaces(monkeypatch: pytest.MonkeyPatch) -> None:
    """``ZulipConfigError`` from ``get_client`` is rendered via emit_error."""
    import lftools_uv.typer_apps.zulip as zulip_mod
    from lftools_uv.api.endpoints.zulip import ZulipConfigError

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
