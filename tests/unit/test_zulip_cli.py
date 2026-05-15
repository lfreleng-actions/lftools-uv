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

Tests are populated by subsequent tasks in the implementation plan.
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
