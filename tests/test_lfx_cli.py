# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``lftools-uv lfx committee show``.

The commands run through the root Typer app, so ``--debug`` takes the
path a user's does. ``responses`` answers every request, so no test
reaches a server.
"""

from __future__ import annotations

import base64
import configparser
import json
import logging
import time
from typing import TYPE_CHECKING

import pytest
import responses
from responses import matchers
from typer.testing import CliRunner

from lftools_uv.api.endpoints.lfx import config as lfx_config
from lftools_uv.typer_apps.root import app

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

BASE = "https://lfx.example.org"
TOKEN = "s3cr3t-token-value"  # noqa: S105
UID = "11111111-2222-4333-8444-555555555555"
OTHER_UID = "99999999-2222-4333-8444-555555555555"
GROUP = "example-gerrit-foo-committers"

COMMITTEE = {
    "uid": UID,
    "name": "Example Committers",
    "category": "Committers",
    "description": "People who may merge",
    "project_uid": "66666666-7777-4888-8999-000000000000",
    "project_name": "Example",
    "sso_group_enabled": True,
    "sso_group_name": GROUP,
    "join_mode": "closed",
    "public": False,
    "enable_voting": True,
    "total_members": 9,
}

EXPECTED_LINES = [
    f"uid: {UID}",
    "name: Example Committers",
    "category: Committers",
    "project_uid: 66666666-7777-4888-8999-000000000000",
    "project_name: Example",
    "sso_group_enabled: true",
    f"sso_group_name: {GROUP}",
    "join_mode: closed",
    "public: false",
    "total_members: 9",
]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the client at a mocked API with a token, and hide lftools.ini."""
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    monkeypatch.setenv("LFX_API_URL", BASE)

    def no_section(section: str, option: str) -> str:
        raise configparser.NoSectionError(section)

    monkeypatch.setattr(lfx_config.lf_config, "get_setting", no_section)
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock() as mock:
        yield mock


def run(*args: str) -> tuple[int, str, str]:
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.stdout, result.stderr


def add_query(rsps: responses.RequestsMock, uids: list[str]) -> None:
    rsps.get(
        f"{BASE}/query/resources",
        json={
            "resources": [
                {"type": "committee", "id": f"committee:{uid}", "data": {"uid": uid, "sso_group_name": GROUP}}
                for uid in uids
            ],
            "page_token": None,
        },
        match=[matchers.query_param_matcher({"v": "1", "type": "committee", "tags": f"sso_group_name:{GROUP}"})],
    )


def add_committee(rsps: responses.RequestsMock, status: int = 200, body: object = COMMITTEE) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=status, json=body, match=[matchers.query_param_matcher({"v": "1"})])


def test_show_by_sso_group_name(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [UID])
    add_committee(rsps)

    code, out, err = run("lfx", "committee", "show", GROUP)

    assert code == 0, err
    assert out.splitlines() == EXPECTED_LINES
    assert err == ""


def test_show_by_uid_json(rsps: responses.RequestsMock) -> None:
    add_committee(rsps)

    code, out, _ = run("lfx", "committee", "show", UID, "--json")

    assert code == 0
    assert json.loads(out) == COMMITTEE
    assert len(rsps.calls) == 1


def test_show_by_uid_plain(rsps: responses.RequestsMock) -> None:
    add_committee(rsps)

    code, out, _ = run("lfx", "committee", "show", UID)

    assert code == 0
    assert out.splitlines() == EXPECTED_LINES


def test_show_unknown_name_exits_3(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [])

    code, out, err = run("lfx", "committee", "show", GROUP)

    assert code == 3
    assert out == ""
    assert "cannot see" in err


def test_show_404_exits_3(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, status=404, body={"message": "committee not found"})

    code, _, err = run("lfx", "committee", "show", UID)

    assert code == 3
    assert "committee not found" in err
    assert "cannot see" in err


def test_show_403_explains_causes(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, status=403, body={"message": "access denied"})

    code, _, err = run("lfx", "committee", "show", UID)

    assert code == 1
    assert "HTTP 403" in err
    assert "access denied" in err
    assert "missing, expired or without access" in err
    assert "may not exist" in err


def test_show_two_matches_exits_1(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [UID, OTHER_UID])

    code, _, err = run("lfx", "committee", "show", GROUP)

    assert code == 1
    assert UID in err
    assert OTHER_UID in err


def test_show_redirect_refused(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=301, headers={"Location": "https://elsewhere.example.org/"})

    code, out, err = run("lfx", "committee", "show", UID)

    assert code == 1
    assert out == ""
    assert "redirect" in err


def test_show_error_message_from_body(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, status=500, body={"message": "backend unavailable"})

    code, _, err = run("lfx", "committee", "show", UID)

    assert code == 1
    assert "backend unavailable" in err


def test_show_without_token_exits_1(monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock) -> None:
    monkeypatch.delenv("LFX_TOKEN")

    code, _, err = run("lfx", "committee", "show", UID)

    assert code == 1
    assert "LFX_TOKEN" in err
    assert len(rsps.calls) == 0


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_show_redacts_token_in_response(rsps: responses.RequestsMock, extra: list[str]) -> None:
    add_committee(rsps, body={**COMMITTEE, "name": f"leak {TOKEN}", "description": TOKEN})

    code, out, _ = run("lfx", "committee", "show", UID, *extra)

    assert code == 0
    assert TOKEN not in out
    if extra:
        assert json.loads(out)["name"] == "leak <redacted>"
    else:
        assert "name: leak <redacted>" in out.splitlines()


@pytest.mark.parametrize(("token", "field"), [("12345", "total_members"), ("true", "public")])
def test_show_json_redacts_token_in_scalar(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, token: str, field: str
) -> None:
    monkeypatch.setenv("LFX_TOKEN", token)
    add_committee(rsps, body={**COMMITTEE, "total_members": 12345, "public": True})

    code, out, _ = run("lfx", "committee", "show", UID, "--json")

    assert code == 0
    assert token not in out
    shown = json.loads(out)
    assert shown[field] == "<redacted>"
    # A scalar the token does not match keeps its JSON type.
    if token == "true":
        assert shown["enable_voting"] == "<redacted>"
    else:
        assert shown["enable_voting"] is True


def test_show_token_matching_field_name_keeps_values(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock
) -> None:
    monkeypatch.setenv("LFX_TOKEN", "name")
    add_committee(rsps)

    code, out, _ = run("lfx", "committee", "show", UID)

    assert code == 0
    lines = out.splitlines()
    assert "<redacted>: Example Committers" in lines
    assert "project_<redacted>: Example" in lines
    assert "null" not in out


def _expired_jwt() -> str:
    def part(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256'})}.{part({'exp': int(time.time()) - 60})}.c2ln"


@pytest.mark.parametrize(
    "scenario",
    ["success", "json", "not-found", "forbidden", "redirect", "expired", "bad-url"],
)
def test_token_never_printed_or_logged(
    monkeypatch: pytest.MonkeyPatch,
    rsps: responses.RequestsMock,
    caplog: pytest.LogCaptureFixture,
    scenario: str,
) -> None:
    token = TOKEN
    extra: list[str] = []
    if scenario in ("success", "json"):
        add_committee(rsps)
        extra = ["--json"] if scenario == "json" else []
    elif scenario == "not-found":
        add_committee(rsps, status=404, body={"message": "nope"})
    elif scenario == "forbidden":
        add_committee(rsps, status=403, body={"message": "nope"})
    elif scenario == "redirect":
        rsps.get(f"{BASE}/committees/{UID}", status=302, headers={"Location": "https://elsewhere.example.org/"})
    elif scenario == "expired":
        token = _expired_jwt()
    elif scenario == "bad-url":
        monkeypatch.setenv("LFX_API_URL", "http://lfx.example.org")
    monkeypatch.setenv("LFX_TOKEN", token)
    caplog.set_level(logging.DEBUG)

    result = CliRunner().invoke(app, ["--debug", "lfx", "committee", "show", UID, *extra])

    assert result.exception is None or isinstance(result.exception, SystemExit)
    assert token not in result.stdout
    assert token not in result.stderr
    assert token not in caplog.text
    assert "LFX GET" in caplog.text or scenario in ("expired", "bad-url")
