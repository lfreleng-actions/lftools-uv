# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the ``lftools-uv lfx committee`` commands.

The commands run through the root Typer app, so ``--debug`` takes the
path a user's does. ``responses`` answers every request, so no test
reaches a server.
"""

from __future__ import annotations

import base64
import configparser
import csv
import io
import json
import logging
import time
import uuid
from typing import TYPE_CHECKING

import pytest
import responses
import yaml
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


# committee list

SLUG = "example"
PROJECT_UID = "66666666-7777-4888-8999-000000000000"


def committee_data(uid: str, name: str, sso_group_name: str = "", *, sso: bool = True) -> dict[str, object]:
    return {"uid": uid, "name": name, "sso_group_name": sso_group_name, "sso_group_enabled": sso}


def add_project(rsps: responses.RequestsMock, slugs: list[str]) -> None:
    rsps.get(
        f"{BASE}/query/resources",
        json={
            "resources": [
                {"type": "project", "id": f"project:{uid}", "data": {"uid": uid, "slug": slug, "name": slug}}
                for slug, uid in ((slug, PROJECT_UID if slug == SLUG else OTHER_UID) for slug in slugs)
            ],
            "page_token": None,
        },
        match=[matchers.query_param_matcher({"v": "1", "type": "project", "filters": f"slug:{SLUG}"})],
    )


def add_committees(rsps: responses.RequestsMock, pages: list[list[dict[str, object]]]) -> None:
    base_params = {"v": "1", "type": "committee", "tags": f"project_slug:{SLUG}"}
    for index, page in enumerate(pages):
        params = dict(base_params)
        if index:
            params["page_token"] = f"page-{index}"
        rsps.get(
            f"{BASE}/query/resources",
            json={
                "resources": [{"type": "committee", "id": f"committee:{data['uid']}", "data": data} for data in page],
                "page_token": f"page-{index + 1}" if index + 1 < len(pages) else None,
            },
            match=[matchers.query_param_matcher(params)],
        )


LIST_COMMITTEES = [
    committee_data(OTHER_UID, "TSC", "example-tsc"),
    committee_data(UID, "Example Committers", GROUP),
    committee_data("22222222-2222-4333-8444-555555555555", "Marketing", sso=False),
]


def test_list_sorted_by_name(rsps: responses.RequestsMock) -> None:
    add_project(rsps, [SLUG])
    add_committees(rsps, [LIST_COMMITTEES])

    code, out, err = run("lfx", "committee", "list", "--project", SLUG)

    assert code == 0, err
    assert out.splitlines() == [
        f"{GROUP}\t{UID}\tExample Committers",
        "\t22222222-2222-4333-8444-555555555555\tMarketing",
        f"example-tsc\t{OTHER_UID}\tTSC",
    ]


def test_list_sso_only(rsps: responses.RequestsMock) -> None:
    add_project(rsps, [SLUG])
    add_committees(rsps, [LIST_COMMITTEES])

    code, out, _ = run("lfx", "committee", "list", "--project", SLUG, "--sso-only")

    assert code == 0
    assert out.splitlines() == [f"{GROUP}\t{UID}\tExample Committers", f"example-tsc\t{OTHER_UID}\tTSC"]


def test_list_json(rsps: responses.RequestsMock) -> None:
    add_project(rsps, [SLUG])
    add_committees(rsps, [LIST_COMMITTEES])

    code, out, _ = run("lfx", "committee", "list", "--project", SLUG, "--json")

    assert code == 0
    assert json.loads(out) == [LIST_COMMITTEES[1], LIST_COMMITTEES[2], LIST_COMMITTEES[0]]


def test_list_spans_two_pages(rsps: responses.RequestsMock) -> None:
    add_project(rsps, [SLUG])
    add_committees(rsps, [LIST_COMMITTEES[:1], LIST_COMMITTEES[1:]])

    code, out, _ = run("lfx", "committee", "list", "--project", SLUG)

    assert code == 0
    assert len(out.splitlines()) == 3


def test_list_unknown_slug_exits_3(rsps: responses.RequestsMock) -> None:
    add_project(rsps, [f"{SLUG}-other"])

    code, out, err = run("lfx", "committee", "list", "--project", SLUG)

    assert code == 3
    assert out == ""
    assert SLUG in err


def test_list_no_committees_exits_0(rsps: responses.RequestsMock, caplog: pytest.LogCaptureFixture) -> None:
    add_project(rsps, [SLUG])
    add_committees(rsps, [[]])
    caplog.set_level(logging.INFO)

    code, out, _ = run("lfx", "committee", "list", "--project", SLUG)

    assert code == 0
    assert out == ""
    assert "no committee" in caplog.text


# committee members

MEMBERS_XFAIL = pytest.mark.xfail(strict=True, reason="lfx committee members is not implemented yet")


def member(username: str, email: str, first: str, last: str, organization: object = None) -> dict[str, object]:
    body: dict[str, object] = {
        "uid": str(uuid.uuid5(uuid.NAMESPACE_URL, email)),
        "committee_uid": UID,
        "committee_name": "Example Committers",
        "username": username,
        "email": email,
        "first_name": first,
        "last_name": last,
        "role": {"name": "None"},
        "status": "Active",
        "voting": {"status": "None"},
    }
    if organization is not None:
        body["organization"] = organization
    return body


MEMBERS = [
    member("jdoe", "jdoe@example.org", "Jane", "Doe", {"id": "", "name": "Example Corp", "website": ""}),
    member("", "zed@example.org", "Zed", "Nobody"),
    member("Bob", "bob@example.com", "Bob", "Smith, Jr.", {"id": "", "name": "", "website": ""}),
    member("lfservices_releng", "releng@example.org", "LF", "Releng"),
    member("cobrien", "conor@corp.example.com", "Conor", "O'Brien"),
    member("", "amy@example.net", "Amy", "Newcomer"),
]


def add_members(rsps: responses.RequestsMock, status: int = 200, body: object = MEMBERS) -> None:
    rsps.get(
        f"{BASE}/committees/{UID}/members",
        status=status,
        json=body,
        match=[matchers.query_param_matcher({"v": "1"})],
    )


@MEMBERS_XFAIL
def test_members_text_sorted(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [UID])
    add_members(rsps)

    code, out, err = run("lfx", "committee", "members", GROUP)

    assert code == 0, err
    assert out.splitlines() == [
        "Bob <bob@example.com>",
        "cobrien <conor@corp.example.com>",
        "jdoe <jdoe@example.org>",
        "lfservices_releng <releng@example.org>",
        "(no username) <amy@example.net>",
        "(no username) <zed@example.org>",
    ]


@MEMBERS_XFAIL
def test_members_csv(rsps: responses.RequestsMock) -> None:
    add_committee(rsps)
    add_members(rsps)

    code, out, err = run("lfx", "committee", "members", UID, "--format", "csv")

    assert code == 0, err
    assert f'{GROUP},Bob,"Bob Smith, Jr.",bob@example.com' in out.splitlines()
    assert list(csv.reader(io.StringIO(out))) == [
        [GROUP, "Bob", "Bob Smith, Jr.", "bob@example.com"],
        [GROUP, "cobrien", "Conor O'Brien", "conor@corp.example.com"],
        [GROUP, "jdoe", "Jane Doe", "jdoe@example.org"],
        [GROUP, "lfservices_releng", "LF Releng", "releng@example.org"],
        [GROUP, "", "Amy Newcomer", "amy@example.net"],
        [GROUP, "", "Zed Nobody", "zed@example.org"],
    ]


@MEMBERS_XFAIL
def test_members_csv_group_falls_back_to_name(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, body={**COMMITTEE, "sso_group_name": ""})
    add_members(rsps, body=MEMBERS[:1])

    code, out, _ = run("lfx", "committee", "members", UID, "--format", "csv")

    assert code == 0
    assert out.splitlines() == ["Example Committers,jdoe,Jane Doe,jdoe@example.org"]


@MEMBERS_XFAIL
@pytest.mark.parametrize("first", ["Jane\rAnn", "Jane\nAnn", "Jane\r\nAnn"])
def test_members_csv_line_break_in_field(first: str) -> None:
    # Called directly: CliRunner folds CRLF in captured output into LF.
    from lftools_uv.api.endpoints.lfx import format_csv

    out = format_csv([member("jdoe", "jdoe@example.org", first, "Doe")], GROUP)

    assert out.endswith(",jdoe@example.org\n")
    assert not out.endswith("\r\n")
    assert list(csv.reader(io.StringIO(out, newline=""))) == [[GROUP, "jdoe", f"{first} Doe", "jdoe@example.org"]]


@MEMBERS_XFAIL
def test_members_info_yaml(rsps: responses.RequestsMock, caplog: pytest.LogCaptureFixture) -> None:
    add_members(rsps)
    caplog.set_level(logging.INFO)

    code, out, err = run("lfx", "committee", "members", UID, "--format", "info-yaml")

    assert code == 0, err
    assert out == (
        "    - name: 'Bob Smith, Jr.'\n"
        "      email: 'bob@example.com'\n"
        "      company: 'example'\n"
        "      id: 'Bob'\n"
        "      timezone: 'Unknown/Unknown'\n"
        "    - name: 'Conor O''Brien'\n"
        "      email: 'conor@corp.example.com'\n"
        "      company: 'corp.example'\n"
        "      id: 'cobrien'\n"
        "      timezone: 'Unknown/Unknown'\n"
        "    - name: 'Jane Doe'\n"
        "      email: 'jdoe@example.org'\n"
        "      company: 'Example Corp'\n"
        "      id: 'jdoe'\n"
        "      timezone: 'Unknown/Unknown'\n"
    )
    parsed = yaml.safe_load(f"committers:\n{out}")["committers"]
    assert [entry["name"] for entry in parsed] == ["Bob Smith, Jr.", "Conor O'Brien", "Jane Doe"]
    assert "2 members without a username" in caplog.text
    assert "amy@example.net" not in caplog.text + err
    assert "zed@example.org" not in caplog.text + err


@pytest.mark.parametrize(
    "name",
    [
        "Example\nCorp",
        "Example\r\nCorp",
        "Bell\x07 and \x7f Corp",
        "Next\x85Line\u2028Sep\u2029Corp",
        'O\'Brien "Quoted" \\ Corp\n',
    ],
)
@MEMBERS_XFAIL
def test_members_info_yaml_control_characters(rsps: responses.RequestsMock, name: str) -> None:
    add_members(rsps, body=[member("jdoe", "jdoe@example.org", "Jane", "Doe", {"name": name})])

    code, out, err = run("lfx", "committee", "members", UID, "--format", "info-yaml")

    assert code == 0, err
    assert len(out.splitlines()) == 5
    parsed = yaml.safe_load(f"committers:\n{out}")["committers"]
    assert parsed == [
        {
            "name": "Jane Doe",
            "email": "jdoe@example.org",
            "company": name,
            "id": "jdoe",
            "timezone": "Unknown/Unknown",
        }
    ]


@MEMBERS_XFAIL
def test_members_json_unchanged(rsps: responses.RequestsMock) -> None:
    add_members(rsps)

    code, out, _ = run("lfx", "committee", "members", UID, "--json")

    assert code == 0
    assert json.loads(out) == MEMBERS


@MEMBERS_XFAIL
@pytest.mark.parametrize("fmt", ["text", "csv", "info-yaml"])
def test_members_json_refuses_format(rsps: responses.RequestsMock, fmt: str) -> None:
    code, out, err = run("lfx", "committee", "members", UID, "--json", "--format", fmt)

    assert code == 2
    assert out == ""
    assert "--format" in err
    assert len(rsps.calls) == 0


@MEMBERS_XFAIL
def test_members_403_names_auditor(rsps: responses.RequestsMock) -> None:
    add_members(rsps, status=403, body={"message": "access denied"})

    code, out, err = run("lfx", "committee", "members", UID)

    assert code == 1
    assert out == ""
    assert "HTTP 403" in err
    assert "auditor" in err


@MEMBERS_XFAIL
def test_members_unknown_committee_exits_3(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [])

    code, out, err = run("lfx", "committee", "members", GROUP)

    assert code == 3
    assert out == ""
    assert "cannot see" in err


@MEMBERS_XFAIL
def test_members_404_exits_3(rsps: responses.RequestsMock) -> None:
    add_members(rsps, status=404, body={"message": "committee not found"})

    code, _, err = run("lfx", "committee", "members", UID)

    assert code == 3
    assert "committee not found" in err
