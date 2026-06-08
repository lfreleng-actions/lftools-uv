# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Tests for Zulip channel folder API and CLI support."""

from __future__ import annotations

import json
from typing import Any
from unittest import mock

import pytest
from typer.testing import CliRunner

import lftools_uv.typer_apps.zulip as zulip_cli
from lftools_uv.api.endpoints.zulip import (
    FEATURE_LEVELS,
    ZulipAmbiguityError,
    ZulipAPIError,
    ZulipFeatureLevelError,
    ZulipNotFoundError,
    ZulipValidationError,
    archive_channel_folder,
    create_channel,
    create_channel_folder,
    list_channel_folders,
    resolve_channel_folder_token,
    unarchive_channel_folder,
    update_channel,
    update_channel_folder,
)
from lftools_uv.typer_apps.zulip import zulip_app
from tests.test_utils import clean_cli_output

FOLDERS = [
    {
        "id": 10,
        "name": "Projects",
        "description": "Project channels",
        "rendered_description": "<p>Project channels</p>",
        "order": 1,
        "is_archived": False,
        "date_created": 1761955200,
        "creator_id": 42,
    },
    {
        "id": 11,
        "name": "Old Projects",
        "description": "Archived projects",
        "rendered_description": "<p>Archived projects</p>",
        "is_archived": True,
        "date_created": 1761955300,
        "creator_id": 43,
    },
]


def _folder_client(
    *,
    feature_level: int = 500,
    folders: list[dict[str, Any]] | None = None,
    folder_response: dict[str, Any] | None = None,
    limits: dict[str, int] | None = None,
    streams: list[dict[str, Any]] | None = None,
) -> mock.MagicMock:
    """Return a mock Zulip client wired for folder operations."""
    client = mock.MagicMock()
    client.get_server_settings.return_value = {
        "result": "success",
        "zulip_feature_level": feature_level,
    }
    folder_list = FOLDERS if folders is None else folders
    streams_list = streams if streams is not None else [{"stream_id": 1, "name": "general", "is_archived": False}]
    client.last_requests = []

    def call_endpoint(*, url: str, method: str, request: dict[str, Any] | None = None) -> dict[str, Any]:
        client.last_requests.append({"url": url, "method": method, "request": request})
        if url == "register" and method == "GET":
            return {"result": "success", **(limits or {})}
        if url == "channel_folders" and method == "GET":
            include_archived = bool((request or {}).get("include_archived"))
            visible = (
                folder_list if include_archived else [folder for folder in folder_list if not folder.get("is_archived")]
            )
            return {"result": "success", "channel_folders": visible}
        if url == "channel_folders/create" and method == "POST":
            return folder_response or {"result": "success", "channel_folder_id": 99}
        if url.startswith("channel_folders/") and method == "PATCH":
            return folder_response or {"result": "success"}
        if url == "streams" and method == "GET":
            return {"result": "success", "streams": streams_list}
        if url.startswith("streams/") and method == "PATCH":
            client.last_patch = {"url": url, "request": request}
            return {"result": "success"}
        if url == "users/me/subscriptions" and method == "POST":
            client.last_create = {"url": url, "request": request}
            return {"result": "success", "subscribed": {}}
        return {"result": "error", "msg": f"unexpected endpoint {method} {url}"}

    client.call_endpoint.side_effect = call_endpoint
    return client


# API helpers


def test_feature_level_table_contains_folder_keys() -> None:
    """Feature level constants document folder support thresholds."""
    assert FEATURE_LEVELS["channel-folders"] == 389
    assert FEATURE_LEVELS["channel-folders-order"] == 414


def test_list_channel_folders_active_only_and_missing_order() -> None:
    """Default folder listing filters archived folders and tolerates no order."""
    client = _folder_client()
    folders = list_channel_folders(client)
    assert [folder["id"] for folder in folders] == [10]
    assert folders[0]["order"] == 1

    all_folders = list_channel_folders(client, include_archived=True)
    assert [folder["id"] for folder in all_folders] == [10, 11]
    assert all_folders[1]["order"] is None


def test_list_channel_folders_limit_and_feature_gate() -> None:
    """Folder list supports --limit and fails before API calls below FL 389."""
    client = _folder_client(folders=[{**FOLDERS[0], "id": idx, "name": f"f{idx}"} for idx in range(5)])
    assert [folder["id"] for folder in list_channel_folders(client, limit=2)] == [0, 1]

    old_client = _folder_client(feature_level=388)
    with pytest.raises(ZulipFeatureLevelError):
        list_channel_folders(old_client)
    assert not any(call["url"] == "channel_folders" for call in old_client.last_requests)


def test_create_channel_folder_payload_and_limits() -> None:
    """Create sends name/description and validates known length limits."""
    client = _folder_client(limits={"max_channel_folder_name_length": 20, "max_channel_folder_description_length": 30})
    result = create_channel_folder(client, "Projects", "Project channels")
    assert result == {"status": "success", "folder_id": 99, "folder_name": "Projects", "operation": "create"}
    create_call = next(call for call in client.last_requests if call["url"] == "channel_folders/create")
    assert create_call["request"] == {"name": "Projects", "description": "Project channels"}

    with pytest.raises(ZulipValidationError, match="Folder name"):
        create_channel_folder(client, "", "")
    with pytest.raises(ZulipValidationError, match="description"):
        create_channel_folder(client, "Projects", "x" * 31)


def test_update_archive_unarchive_channel_folder_payloads() -> None:
    """Update and archive wrappers PATCH only requested fields."""
    client = _folder_client()
    result = update_channel_folder(client, 10, name="Engineering")
    assert result["operation"] == "update"
    patch_call = next(call for call in client.last_requests if call["url"] == "channel_folders/10")
    assert patch_call["request"] == {"name": "Engineering"}

    client = _folder_client()
    archive_channel_folder(client, 10)
    assert client.last_requests[-1]["request"] == {"is_archived": True}

    client = _folder_client()
    unarchive_channel_folder(client, 10)
    assert client.last_requests[-1]["request"] == {"is_archived": False}


def test_folder_mutation_permission_errors_surface_as_api_errors() -> None:
    """Server permission errors are not preflighted client-side."""
    client = _folder_client(folder_response={"result": "error", "msg": "Insufficient permission"})
    with pytest.raises(ZulipAPIError, match="Insufficient permission"):
        create_channel_folder(client, "Projects")


def test_resolve_channel_folder_token_variants() -> None:
    """Folder resolver accepts names, id:N, none, and numeric-name hints."""
    client = _folder_client(folders=[*FOLDERS, {**FOLDERS[0], "id": 12, "name": "123"}])
    assert resolve_channel_folder_token(client, "projects") == 10
    assert resolve_channel_folder_token(client, "id:11") == 11
    assert resolve_channel_folder_token(client, "none") is None
    assert resolve_channel_folder_token(client, "123") == 12

    with pytest.raises(ZulipNotFoundError, match="id:999"):
        resolve_channel_folder_token(client, "999")
    with pytest.raises(ZulipValidationError, match="positive"):
        resolve_channel_folder_token(client, "id:0")


def test_resolve_channel_folder_token_ambiguity() -> None:
    """Duplicate folder names raise ambiguity with disambiguation matches."""
    client = _folder_client(folders=[FOLDERS[0], {**FOLDERS[0], "id": 12, "name": "projects"}])
    with pytest.raises(ZulipAmbiguityError) as exc_info:
        resolve_channel_folder_token(client, "Projects")
    assert {match["id"] for match in exc_info.value.matches} == {10, 12}


def test_create_channel_with_folder_id_in_subscription() -> None:
    """Channel create includes folder_id in the subscription payload."""
    client = _folder_client(streams=[{"stream_id": 42, "name": "general", "is_archived": False}])
    result = create_channel(client, name="general", folder_id=10, folder_id_specified=True)
    assert result["folder_id"] == 10
    assert client.last_create["request"]["subscriptions"] == [{"name": "general", "folder_id": 10}]


@pytest.mark.parametrize("bad_folder_id", [0, -1, True, False])
def test_create_channel_rejects_invalid_folder_id(bad_folder_id: int) -> None:
    """Channel create validates folder assignments before API calls."""
    client = _folder_client()
    with pytest.raises(ZulipValidationError, match="positive integer"):
        create_channel(client, name="general", folder_id=bad_folder_id, folder_id_specified=True)
    assert not any(call["url"] == "users/me/subscriptions" for call in client.last_requests)


def test_update_channel_folder_id_and_clear() -> None:
    """Channel update sends folder_id for assignment and clearing."""
    client = _folder_client()
    result = update_channel(client, name="general", folder_id=10, folder_id_specified=True)
    assert result["folder_id"] == 10
    assert client.last_patch["request"] == {"folder_id": 10}

    client = _folder_client()
    result = update_channel(client, name="general", folder_id=None, folder_id_specified=True)
    assert result["folder_id"] is None
    assert client.last_patch["request"] == {"folder_id": None}


@pytest.mark.parametrize("bad_folder_id", [0, -1, True, False])
def test_update_channel_rejects_invalid_folder_id(bad_folder_id: int) -> None:
    """Channel update validates folder assignments before API calls."""
    client = _folder_client()
    with pytest.raises(ZulipValidationError, match="positive integer"):
        update_channel(client, name="general", folder_id=bad_folder_id, folder_id_specified=True)
    assert not any(call["url"].startswith("streams/") for call in client.last_requests)


def test_channel_folder_assignment_feature_gate() -> None:
    """Channel folder assignment fails before mutation below FL 389."""
    client = _folder_client(feature_level=388)
    with pytest.raises(ZulipFeatureLevelError):
        create_channel(client, name="general", folder_id=10, folder_id_specified=True)
    assert not any(call["url"] == "users/me/subscriptions" for call in client.last_requests)


# CLI commands


def _patch_cli_client(monkeypatch: pytest.MonkeyPatch, client: mock.MagicMock) -> None:
    monkeypatch.setattr(zulip_cli, "get_client", lambda **_kw: client)
    monkeypatch.setattr(zulip_cli, "zulip_available", lambda: True)


def test_folder_list_cli_table_json_and_status(monkeypatch: pytest.MonkeyPatch) -> None:
    """Folder list renders table and JSON contracts."""
    client = _folder_client()
    _patch_cli_client(monkeypatch, client)
    runner = CliRunner()

    result = runner.invoke(zulip_app, ["folder", "list"])
    assert result.exit_code == 0, result.output
    assert "Folder ID" in result.stdout
    assert "Projects" in result.stdout
    assert "Old Projects" not in result.stdout
    assert "Status" not in result.stdout

    result = runner.invoke(zulip_app, ["folder", "list", "--include-archived"])
    assert result.exit_code == 0, result.output
    assert "Status" in result.stdout
    assert "Archived" in result.stdout

    result = runner.invoke(zulip_app, ["--json", "folder", "list", "--include-archived", "--limit", "1"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.stdout)
    assert list(payload) == ["folders"]
    assert len(payload["folders"]) == 1


def test_folder_mutation_cli_success_and_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    """Folder create/update/archive/unarchive CLI paths emit mutation JSON."""
    client = _folder_client()
    _patch_cli_client(monkeypatch, client)
    runner = CliRunner()

    result = runner.invoke(zulip_app, ["--json", "folder", "create", "--name", "Projects"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["operation"] == "create"

    result = runner.invoke(zulip_app, ["folder", "update", "--folder-id", "10"])
    assert result.exit_code == 1
    assert "at least one" in (result.stdout + result.stderr)

    result = runner.invoke(zulip_app, ["--json", "folder", "update", "--folder-id", "10", "--name", "Engineering"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["operation"] == "update"

    result = runner.invoke(zulip_app, ["--json", "folder", "archive", "--folder-id", "10"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["operation"] == "archive"

    result = runner.invoke(zulip_app, ["--json", "folder", "unarchive", "--folder-id", "10"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["operation"] == "unarchive"


def test_folder_cli_feature_level_error(monkeypatch: pytest.MonkeyPatch) -> None:
    """Folder commands surface canonical feature-level errors."""
    client = _folder_client(feature_level=388)
    _patch_cli_client(monkeypatch, client)
    result = CliRunner().invoke(zulip_app, ["folder", "list"])
    assert result.exit_code == 1
    assert "feature level 389" in (result.stdout + result.stderr)


def test_channel_create_cli_folder_name(monkeypatch: pytest.MonkeyPatch) -> None:
    """Channel create --folder resolves names and sends folder_id."""
    client = _folder_client(streams=[{"stream_id": 42, "name": "new-project", "is_archived": False}])
    _patch_cli_client(monkeypatch, client)
    result = CliRunner().invoke(zulip_app, ["--json", "channel", "create", "new-project", "--folder", "Projects"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["folder_id"] == 10
    assert client.last_create["request"]["subscriptions"][0]["folder_id"] == 10


def test_channel_update_cli_folder_variants(monkeypatch: pytest.MonkeyPatch) -> None:
    """Channel update supports --folder id:N, none, and --folder-id 0."""
    client = _folder_client()
    _patch_cli_client(monkeypatch, client)
    runner = CliRunner()

    result = runner.invoke(zulip_app, ["--json", "channel", "update", "general", "--folder", "id:10"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["folder_id"] == 10
    assert client.last_patch["request"] == {"folder_id": 10}

    result = runner.invoke(zulip_app, ["--json", "channel", "update", "general", "--folder", "none"])
    assert result.exit_code == 0, result.output
    assert json.loads(result.stdout)["folder_id"] is None
    assert client.last_patch["request"] == {"folder_id": None}

    result = runner.invoke(zulip_app, ["channel", "update", "general", "--folder-id", "0"])
    assert result.exit_code == 0, result.output
    assert client.last_patch["request"] == {"folder_id": None}

    result = runner.invoke(zulip_app, ["channel", "update", "general", "--folder-id", "10"])
    assert result.exit_code == 1
    assert "--folder id:N" in (result.stdout + result.stderr)


def test_channel_update_cli_no_folder_preserves_behavior(monkeypatch: pytest.MonkeyPatch) -> None:
    """Existing channel update flags still work without folder options."""
    client = _folder_client()
    _patch_cli_client(monkeypatch, client)
    result = CliRunner().invoke(zulip_app, ["channel", "update", "general", "--description", "new"])
    assert result.exit_code == 0, result.output
    assert client.last_patch["request"] == {"description": "new"}


def test_folder_help_output_has_no_spec_ids(monkeypatch: pytest.MonkeyPatch) -> None:
    """New folder help text avoids leaking internal spec identifiers."""
    monkeypatch.setattr(zulip_cli, "zulip_available", lambda: True)
    runner = CliRunner()
    for args in (
        ["folder", "--help"],
        ["folder", "list", "--help"],
        ["folder", "create", "--help"],
        ["channel", "create", "--help"],
        ["channel", "update", "--help"],
    ):
        result = runner.invoke(zulip_app, args, env={"COLUMNS": "200", "NO_COLOR": "1", "TERM": "dumb"})
        assert result.exit_code == 0, result.output
        cleaned = clean_cli_output(result.output)
        assert "--folder" in cleaned or args[0] == "folder"
        assert "US#" not in cleaned
        assert "T###" not in cleaned
        assert "FR-###" not in cleaned
