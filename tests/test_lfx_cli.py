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


def test_members_csv_group_falls_back_to_name(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, body={**COMMITTEE, "sso_group_name": ""})
    add_members(rsps, body=MEMBERS[:1])

    code, out, _ = run("lfx", "committee", "members", UID, "--format", "csv")

    assert code == 0
    assert out.splitlines() == ["Example Committers,jdoe,Jane Doe,jdoe@example.org"]


@pytest.mark.parametrize("first", ["Jane\rAnn", "Jane\nAnn", "Jane\r\nAnn"])
def test_members_csv_line_break_in_field(first: str) -> None:
    # Called directly: CliRunner folds CRLF in captured output into LF.
    from lftools_uv.api.endpoints.lfx import format_csv

    out = format_csv([member("jdoe", "jdoe@example.org", first, "Doe")], GROUP)

    assert out.endswith(",jdoe@example.org\n")
    assert not out.endswith("\r\n")
    assert list(csv.reader(io.StringIO(out, newline=""))) == [[GROUP, "jdoe", f"{first} Doe", "jdoe@example.org"]]


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


def test_members_json_unchanged(rsps: responses.RequestsMock) -> None:
    add_members(rsps)

    code, out, _ = run("lfx", "committee", "members", UID, "--json")

    assert code == 0
    assert json.loads(out) == MEMBERS


@pytest.mark.parametrize("fmt", ["text", "csv", "info-yaml"])
def test_members_json_refuses_format(rsps: responses.RequestsMock, fmt: str) -> None:
    code, out, err = run("lfx", "committee", "members", UID, "--json", "--format", fmt)

    assert code == 2
    assert out == ""
    assert "cannot be combined with" in err
    assert len(rsps.calls) == 0


def test_members_403_names_auditor(rsps: responses.RequestsMock) -> None:
    add_members(rsps, status=403, body={"message": "access denied"})

    code, out, err = run("lfx", "committee", "members", UID)

    assert code == 1
    assert out == ""
    assert "HTTP 403" in err
    assert "auditor" in err


def test_members_unknown_committee_exits_3(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [])

    code, out, err = run("lfx", "committee", "members", GROUP)

    assert code == 3
    assert out == ""
    assert "cannot see" in err


def test_members_404_exits_3(rsps: responses.RequestsMock) -> None:
    add_members(rsps, status=404, body={"message": "committee not found"})

    code, _, err = run("lfx", "committee", "members", UID)

    assert code == 3
    assert "committee not found" in err


# committee create

COMMITTEE_NAME = "gerrit-foo-committers"

CREATED = {
    "uid": UID,
    "name": COMMITTEE_NAME,
    "category": "Committers",
    "project_uid": PROJECT_UID,
    "sso_group_enabled": True,
    "sso_group_name": GROUP,
    "join_mode": "closed",
    "public": False,
}

DEFAULT_CREATE_BODY = {
    "name": COMMITTEE_NAME,
    "category": "Committers",
    "project_uid": PROJECT_UID,
    "join_mode": "closed",
    "public": False,
    "sso_group_enabled": True,
}


@pytest.fixture
def create_rsps() -> Iterator[responses.RequestsMock]:
    """Mock the API without failing teardown on a request the test expects not to send."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def add_projects(rsps: responses.RequestsMock, projects: list[tuple[str, str]]) -> None:
    rsps.get(
        f"{BASE}/query/resources",
        json={
            "resources": [
                {"type": "project", "id": f"project:{uid}", "data": {"uid": uid, "slug": slug}}
                for slug, uid in projects
            ],
            "page_token": None,
        },
        match=[matchers.query_param_matcher({"v": "1", "type": "project", "filters": f"slug:{SLUG}"})],
    )


def add_create(rsps: responses.RequestsMock, status: int = 201, body: object = CREATED) -> None:
    rsps.post(f"{BASE}/committees", status=status, json=body, match=[matchers.query_param_matcher({"v": "1"})])


def run_create(*extra: str) -> tuple[int, str, str]:
    return run("lfx", "committee", "create", "--project", SLUG, "--name", COMMITTEE_NAME, *extra)


def posts(rsps: responses.RequestsMock) -> list[object]:
    bodies: list[object] = []
    for call in rsps.calls:
        if call.request.method != "POST":
            continue
        body = call.request.body
        assert isinstance(body, bytes | str)
        bodies.append(json.loads(body))
    return bodies


def test_create_defaults(create_rsps: responses.RequestsMock) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps)

    code, out, err = run_create()

    assert code == 0, err
    assert out == f"{GROUP}\t{UID}\n"
    assert posts(create_rsps) == [DEFAULT_CREATE_BODY]


@pytest.mark.parametrize(
    ("extra", "changed"),
    [
        (["--category", "Technical Steering Committee"], {"category": "Technical Steering Committee"}),
        (["--description", "Committers of foo"], {"description": "Committers of foo"}),
        (["--join-mode", "invite_only"], {"join_mode": "invite_only"}),
        (["--no-sso-group"], {"sso_group_enabled": False}),
        (["--public"], {"public": True}),
        (["--sso-group", "--private"], {}),
    ],
)
def test_create_options_in_body(
    create_rsps: responses.RequestsMock, extra: list[str], changed: dict[str, object]
) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps)

    code, _, err = run_create(*extra)

    assert code == 0, err
    assert posts(create_rsps) == [{**DEFAULT_CREATE_BODY, **changed}]


def test_create_prints_returned_sso_group_name(create_rsps: responses.RequestsMock) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps, body={**CREATED, "sso_group_name": f"{GROUP}-2"})

    code, out, _ = run_create()

    assert code == 0
    assert out == f"{GROUP}-2\t{UID}\n"


def test_create_without_sso_group_name_prints_empty_field(create_rsps: responses.RequestsMock) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps, body={**CREATED, "sso_group_enabled": False, "sso_group_name": None})

    code, out, _ = run_create("--no-sso-group")

    assert code == 0
    assert out == f"\t{UID}\n"


def test_create_json(create_rsps: responses.RequestsMock) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps)

    code, out, _ = run_create("--json")

    assert code == 0
    assert json.loads(out) == CREATED


def test_create_unknown_project_exits_3_without_post(create_rsps: responses.RequestsMock) -> None:
    add_projects(create_rsps, [("example-other", OTHER_UID)])
    add_create(create_rsps)

    code, out, err = run_create()

    assert code == 3
    assert out == ""
    assert SLUG in err
    assert posts(create_rsps) == []
    assert len(create_rsps.calls) == 1


def test_create_ambiguous_project_exits_1_without_post(create_rsps: responses.RequestsMock) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID), (SLUG, OTHER_UID)])
    add_create(create_rsps)

    code, _, err = run_create()

    assert code == 1
    assert PROJECT_UID in err
    assert OTHER_UID in err
    assert posts(create_rsps) == []


@pytest.mark.parametrize("extra", [["--category", "Committer"], ["--join-mode", "closed-ish"]])
def test_create_refuses_unknown_choice_before_any_request(
    create_rsps: responses.RequestsMock, extra: list[str]
) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps)

    code, out, err = run_create(*extra)

    assert code == 2
    assert out == ""
    assert extra[1] in err
    assert len(create_rsps.calls) == 0


@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (409, "committee already exists", ["HTTP 409", "committee already exists"]),
        (400, "name is too long", ["HTTP 400", "name is too long"]),
        (403, "access denied", ["HTTP 403", "access denied", "writer"]),
        (404, "not found", ["HTTP 404", "not found"]),
    ],
)
def test_create_errors_exit_1(
    create_rsps: responses.RequestsMock, status: int, message: str, expected: list[str]
) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps, status=status, body={"message": message})

    code, out, err = run_create()

    assert code == 1
    assert out == ""
    for text in expected:
        assert text in err
    assert len(posts(create_rsps)) == 1


@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_create_redacts_token_in_response(create_rsps: responses.RequestsMock, extra: list[str]) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    add_create(create_rsps, body={**CREATED, "sso_group_name": f"leak-{TOKEN}"})

    code, out, _ = run_create(*extra)

    assert code == 0
    assert TOKEN not in out
    assert "leak-<redacted>" in out


def test_create_token_expiring_after_lookup_sends_no_post(
    monkeypatch: pytest.MonkeyPatch, create_rsps: responses.RequestsMock
) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(lfx_config.time, "time", lambda: clock["now"])
    parts = ({"alg": "RS256"}, {"exp": 1_000_100})
    encoded = (base64.urlsafe_b64encode(json.dumps(part).encode()).rstrip(b"=").decode() for part in parts)
    token = ".".join([*encoded, "c2ln"])
    monkeypatch.setenv("LFX_TOKEN", token)

    def project_lookup(request: object) -> tuple[int, dict[str, str], str]:
        clock["now"] = 1_000_200.0
        resources = [{"type": "project", "id": f"project:{PROJECT_UID}", "data": {"uid": PROJECT_UID, "slug": SLUG}}]
        return 200, {}, json.dumps({"resources": resources, "page_token": None})

    create_rsps.add_callback(responses.GET, f"{BASE}/query/resources", callback=project_lookup)
    add_create(create_rsps)

    code, out, err = run_create()

    assert code == 1
    assert out == ""
    assert "expired" in err
    assert token not in err
    assert posts(create_rsps) == []
    assert len(create_rsps.calls) == 1


@pytest.mark.parametrize("location", ["https://elsewhere.example.org/committees", "https://[broken"])
def test_create_redirect_refused_without_follow_up(create_rsps: responses.RequestsMock, location: str) -> None:
    add_projects(create_rsps, [(SLUG, PROJECT_UID)])
    create_rsps.post(f"{BASE}/committees", status=307, headers={"Location": location})

    result = CliRunner().invoke(app, ["lfx", "committee", "create", "--project", SLUG, "--name", COMMITTEE_NAME])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert result.stdout == ""
    assert "HTTP 307" in result.stderr
    assert "refusing to follow it" in result.stderr
    assert len(posts(create_rsps)) == 1
    assert len(create_rsps.calls) == 2


# committee membership

pending = pytest.mark.xfail(strict=True, reason="committee membership commands not implemented yet")

EMAIL = "jdoe@example.org"
JDOE_UID = str(MEMBERS[0]["uid"])
INVITE_UID = "bbbbbbbb-2222-4333-8444-555555555555"
MEMBERS_URL = f"{BASE}/committees/{UID}/members"
ADDED = {**MEMBERS[0]}


@pytest.fixture
def write_rsps() -> Iterator[responses.RequestsMock]:
    """Mock the API without failing teardown on a request the test expects not to send."""
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def add_post_member(rsps: responses.RequestsMock, status: int = 201, body: object = ADDED) -> None:
    rsps.post(MEMBERS_URL, status=status, json=body, match=[matchers.query_param_matcher({"v": "1"})])


def add_get_member(rsps: responses.RequestsMock, member_uid: str = JDOE_UID, etag: str = "7") -> None:
    rsps.get(
        f"{MEMBERS_URL}/{member_uid}",
        json={**MEMBERS[0], "uid": member_uid},
        headers={"ETag": etag},
        match=[matchers.query_param_matcher({"v": "1"})],
    )


def add_delete_member(
    rsps: responses.RequestsMock, member_uid: str = JDOE_UID, status: int = 204, body: object = None
) -> None:
    rsps.delete(
        f"{MEMBERS_URL}/{member_uid}", status=status, json=body, match=[matchers.query_param_matcher({"v": "1"})]
    )


def requests_by(rsps: responses.RequestsMock, method: str) -> list[responses.Call]:
    return [call for call in rsps.calls if call.request.method == method]


def json_body(call: responses.Call) -> object:
    body = call.request.body
    assert isinstance(body, bytes | str)
    return json.loads(body)


@pending
def test_add_member_sends_body_and_skips_notification(write_rsps: responses.RequestsMock) -> None:
    add_query(write_rsps, [UID])
    add_post_member(write_rsps)

    code, out, err = run(
        "lfx",
        "committee",
        "add-member",
        GROUP,
        "--email",
        EMAIL,
        "--first-name",
        "Jane",
        "--last-name",
        "Doe",
        "--organization",
        "Example Corp",
    )

    assert code == 0, err
    assert out == f"added\tjdoe\t{JDOE_UID}\n"
    (post,) = requests_by(write_rsps, "POST")
    assert json_body(post) == {
        "email": EMAIL,
        "first_name": "Jane",
        "last_name": "Doe",
        "organization": {"name": "Example Corp"},
    }
    assert post.request.headers.get("X-Skip-Notification") == "true"


@pending
def test_add_member_notify_sends_notification(write_rsps: responses.RequestsMock) -> None:
    add_post_member(write_rsps)

    code, _, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL, "--notify")

    assert code == 0, err
    (post,) = requests_by(write_rsps, "POST")
    assert json_body(post) == {"email": EMAIL}
    assert "X-Skip-Notification" not in post.request.headers


@pending
def test_add_member_json(write_rsps: responses.RequestsMock) -> None:
    add_post_member(write_rsps)

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL, "--json")

    assert code == 0, err
    assert json.loads(out) == ADDED


@pending
def test_add_member_without_username_warns(
    write_rsps: responses.RequestsMock, caplog: pytest.LogCaptureFixture
) -> None:
    add_post_member(write_rsps, body={**ADDED, "username": ""})

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL)

    assert code == 0, err
    assert out == f"added\t(no username)\t{JDOE_UID}\n"
    assert "no LF account owns the address" in caplog.text
    assert EMAIL not in caplog.text
    assert EMAIL not in err


@pending
def test_add_member_username_matches(write_rsps: responses.RequestsMock) -> None:
    add_post_member(write_rsps)

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL, "--username", "JDoe")

    assert code == 0, err
    assert out == f"added\tjdoe\t{JDOE_UID}\n"
    assert requests_by(write_rsps, "DELETE") == []


@pending
@pytest.mark.parametrize(
    ("resolved", "expected"),
    [("jsmith", "resolved to username 'jsmith'"), ("", "resolved to no username")],
)
def test_add_member_username_mismatch_removes_member(
    write_rsps: responses.RequestsMock, resolved: str, expected: str
) -> None:
    add_post_member(write_rsps, body={**ADDED, "username": resolved})
    add_get_member(write_rsps, etag="5")
    add_delete_member(write_rsps)

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL, "--username", "jdoe")

    assert code == 1
    assert out == ""
    assert expected in err
    assert "removed the member again" in err
    assert EMAIL not in err
    (delete,) = requests_by(write_rsps, "DELETE")
    assert delete.request.headers.get("If-Match") == "5"
    assert delete.request.headers.get("X-Skip-Notification") == "true"


@pending
def test_add_member_failed_removal_reported(write_rsps: responses.RequestsMock) -> None:
    add_post_member(write_rsps, body={**ADDED, "username": "jsmith"})
    add_get_member(write_rsps)
    add_delete_member(write_rsps, status=403, body={"message": "access denied"})

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL, "--username", "jdoe")

    assert code == 1
    assert out == ""
    assert "resolved to username 'jsmith'" in err
    assert "removing it failed too" in err
    assert JDOE_UID in err
    assert "access denied" in err


@pending
@pytest.mark.parametrize(
    ("extra", "expected_code", "expected"),
    [
        ([], 0, "already a member, with username 'jdoe'"),
        (["--username", "JDOE"], 0, "already a member, with username 'jdoe'"),
        (["--username", "jsmith"], 1, "already a member, with username 'jdoe', not 'jsmith'"),
    ],
)
def test_add_member_existing_member_never_removed(
    write_rsps: responses.RequestsMock, extra: list[str], expected_code: int, expected: str
) -> None:
    add_post_member(write_rsps, status=409, body={"message": f"member with email {EMAIL} already exists"})
    add_members(write_rsps)

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", "JDoe@Example.org", *extra)

    assert code == expected_code
    assert expected in err
    assert JDOE_UID in err
    assert EMAIL not in err.lower()
    assert out == ""
    assert requests_by(write_rsps, "DELETE") == []


@pending
@pytest.mark.parametrize(
    ("given", "stored"),
    [(" JDoe@Example.org ", "jdoe@example.org"), ("JDoe@Example.org", "\tjdoe@example.org ")],
)
def test_add_member_existing_member_ignores_surrounding_whitespace(
    write_rsps: responses.RequestsMock, given: str, stored: str
) -> None:
    add_post_member(write_rsps, status=409, body={"message": "member already exists"})
    add_members(write_rsps, body=[member("jdoe", stored, "Jane", "Doe")])

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", given, "--username", "JDOE")

    assert code == 0, err
    assert "already a member, with username 'jdoe'" in err
    assert out == ""
    assert requests_by(write_rsps, "DELETE") == []


@pending
@pytest.mark.parametrize(
    ("status", "message", "expected"),
    [
        (400, "first_name is required", ["HTTP 400", "first_name is required"]),
        (403, "access denied", ["HTTP 403", "access denied", "writer"]),
    ],
)
def test_add_member_errors_exit_1(
    write_rsps: responses.RequestsMock, status: int, message: str, expected: list[str]
) -> None:
    add_post_member(write_rsps, status=status, body={"message": message})

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL)

    assert code == 1
    assert out == ""
    for text in expected:
        assert text in err
    assert requests_by(write_rsps, "DELETE") == []


@pending
@pytest.mark.parametrize("username", ["", "  "])
def test_add_member_refuses_empty_username(write_rsps: responses.RequestsMock, username: str) -> None:
    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL, "--username", username)

    assert code == 2
    assert out == ""
    assert "not be empty" in err
    assert len(write_rsps.calls) == 0


@pending
@pytest.mark.parametrize(
    "address",
    [
        '"jdoe"@example.org',
        '"j doe"@example.org',
        '"j\\"doe"@example.org',
        "jdoe@[192.0.2.1]",
        "jdoe@[IPv6:2001:db8::1]",
        "jdoe'@example.org",
        "jdoe.o'connor@example.org",
    ],
)
def test_add_member_error_hides_unusual_addresses(write_rsps: responses.RequestsMock, address: str) -> None:
    add_post_member(write_rsps, status=400, body={"message": f"cannot add {address} to the committee"})

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL)

    assert code == 1
    assert out == ""
    assert "cannot add <email> to the committee" in err
    assert "jdoe" not in err


@pending
@pytest.mark.parametrize("local", ["'", "''"])
def test_add_member_error_hides_apostrophe_only_local_part(write_rsps: responses.RequestsMock, local: str) -> None:
    add_post_member(write_rsps, status=400, body={"message": f"cannot add {local}@example.org to the committee"})

    code, out, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL)

    assert code == 1
    assert out == ""
    assert "cannot add <email> to the committee" in err
    assert "example.org" not in err


@pending
def test_add_member_error_keeps_quotes_around_address(write_rsps: responses.RequestsMock) -> None:
    add_post_member(write_rsps, status=400, body={"message": "cannot add 'jdoe@example.org' to the committee"})

    code, _, err = run("lfx", "committee", "add-member", UID, "--email", EMAIL)

    assert code == 1
    assert "cannot add '<email>' to the committee" in err


@pending
@pytest.mark.parametrize("scenario", ["mismatch", "existing", "remove"])
def test_membership_diagnostics_redact_username_before_quoting(
    monkeypatch: pytest.MonkeyPatch, write_rsps: responses.RequestsMock, scenario: str
) -> None:
    token = "tok\\en-secret"  # noqa: S105
    monkeypatch.setenv("LFX_TOKEN", token)
    held = f"y{token}"
    if scenario == "mismatch":
        add_post_member(write_rsps, body={**ADDED, "username": held})
        add_get_member(write_rsps)
        add_delete_member(write_rsps)
        args = ["add-member", UID, "--email", EMAIL]
    elif scenario == "existing":
        add_post_member(write_rsps, status=409, body={"message": "member already exists"})
        add_members(write_rsps, body=[{**MEMBERS[0], "username": held}])
        args = ["add-member", UID, "--email", EMAIL]
    else:
        add_members(write_rsps)
        args = ["remove-member", UID]

    code, _, err = run("lfx", "committee", *args, "--username", f"x{token}")

    assert code == (3 if scenario == "remove" else 1)
    assert "'x<redacted>'" in err
    if scenario != "remove":
        assert "'y<redacted>'" in err
    assert token not in err
    assert repr(token)[1:-1] not in err


@pending
@pytest.mark.parametrize("scenario", ["mismatch", "existing", "remove"])
def test_membership_diagnostics_hide_email_username_before_quoting(
    write_rsps: responses.RequestsMock, scenario: str
) -> None:
    address = '"j\\"doe"@example.org'
    held = '"k\\"roe"@example.org'
    if scenario == "mismatch":
        add_post_member(write_rsps, body={**ADDED, "username": held})
        add_get_member(write_rsps)
        add_delete_member(write_rsps)
        args = ["add-member", UID, "--email", EMAIL]
    elif scenario == "existing":
        add_post_member(write_rsps, status=409, body={"message": "member already exists"})
        add_members(write_rsps, body=[{**MEMBERS[0], "username": held}])
        args = ["add-member", UID, "--email", EMAIL]
    else:
        add_members(write_rsps)
        args = ["remove-member", UID]

    code, _, err = run("lfx", "committee", *args, "--username", address)

    assert code == (3 if scenario == "remove" else 1)
    assert err.count("'<email>'") == (1 if scenario == "remove" else 2)
    for fragment in ('"j', "doe", '"k', "roe"):
        assert fragment not in err


@pending
@pytest.mark.parametrize("found", [0, 2])
@pytest.mark.parametrize(
    ("command", "args"),
    [("add-member", ["--email", EMAIL]), ("remove-member", ["--member-uid", JDOE_UID]), ("invite", [EMAIL])],
)
def test_membership_committee_lookup_hides_email_before_quoting(
    write_rsps: responses.RequestsMock, command: str, args: list[str], found: int
) -> None:
    name = '"j\\"doe"@example.org'
    resources = [
        {"type": "committee", "id": f"committee:{uid}", "data": {"uid": uid, "sso_group_name": name}}
        for uid in (UID, OTHER_UID)[:found]
    ]
    write_rsps.get(f"{BASE}/query/resources", json={"resources": resources, "page_token": None})

    code, _, err = run("lfx", "committee", command, name, *args)

    assert code == (3 if found == 0 else 1)
    assert "SSO group name '<email>'" in err
    for fragment in ('"j', "j\\", '\\"'):
        assert fragment not in err
    assert not requests_by(write_rsps, "POST")
    assert not requests_by(write_rsps, "DELETE")


@pending
@pytest.mark.parametrize(
    "selector",
    [["--username", "JDOE"], ["--email", "JDoe@Example.org"], ["--member-uid", JDOE_UID]],
)
def test_remove_member_by_each_selector(write_rsps: responses.RequestsMock, selector: list[str]) -> None:
    add_members(write_rsps)
    add_get_member(write_rsps, etag="42")
    add_delete_member(write_rsps)

    code, out, err = run("lfx", "committee", "remove-member", UID, *selector)

    assert code == 0, err
    assert out == f"removed\t{JDOE_UID}\n"
    (delete,) = requests_by(write_rsps, "DELETE")
    assert delete.request.headers.get("If-Match") == "42"
    assert delete.request.headers.get("X-Skip-Notification") == "true"
    listed = [call for call in write_rsps.calls if (call.request.url or "").startswith(f"{MEMBERS_URL}?")]
    assert len(listed) == (0 if selector[0] == "--member-uid" else 1)


@pending
def test_remove_member_email_ignores_surrounding_whitespace(write_rsps: responses.RequestsMock) -> None:
    add_members(write_rsps)
    add_get_member(write_rsps, etag="42")
    add_delete_member(write_rsps)

    code, out, err = run("lfx", "committee", "remove-member", UID, "--email", " JDoe@Example.org ")

    assert code == 0, err
    assert out == f"removed\t{JDOE_UID}\n"


@pending
def test_remove_member_notify_sends_notification(write_rsps: responses.RequestsMock) -> None:
    add_get_member(write_rsps)
    add_delete_member(write_rsps)

    code, _, err = run("lfx", "committee", "remove-member", UID, "--member-uid", JDOE_UID, "--notify")

    assert code == 0, err
    (delete,) = requests_by(write_rsps, "DELETE")
    assert "X-Skip-Notification" not in delete.request.headers


@pending
@pytest.mark.parametrize("selector", [["--username", "nobody"], ["--email", "nobody@example.org"]])
def test_remove_member_no_match_exits_3(write_rsps: responses.RequestsMock, selector: list[str]) -> None:
    add_members(write_rsps)

    code, out, err = run("lfx", "committee", "remove-member", UID, *selector)

    assert code == 3
    assert out == ""
    assert "no member" in err
    assert "nobody@example.org" not in err
    assert requests_by(write_rsps, "DELETE") == []


@pending
def test_remove_member_two_matches_exits_1(write_rsps: responses.RequestsMock) -> None:
    twins = [member("dup", "one@example.org", "One", "Dup"), member("DUP", "two@example.org", "Two", "Dup")]
    add_members(write_rsps, body=twins)

    code, out, err = run("lfx", "committee", "remove-member", UID, "--username", "dup")

    assert code == 1
    assert out == ""
    for twin in twins:
        assert str(twin["uid"]) in err
    assert "@" not in err
    assert requests_by(write_rsps, "DELETE") == []


@pending
@pytest.mark.parametrize(("second_status", "expected_code"), [(409, 1), (204, 0)])
def test_remove_member_retries_409_once(
    write_rsps: responses.RequestsMock, second_status: int, expected_code: int
) -> None:
    add_get_member(write_rsps, etag="1")
    add_delete_member(write_rsps, status=409, body={"message": "member changed"})
    add_get_member(write_rsps, etag="2")
    add_delete_member(
        write_rsps, status=second_status, body={"message": "member changed"} if second_status == 409 else None
    )

    code, _, err = run("lfx", "committee", "remove-member", UID, "--member-uid", JDOE_UID)

    assert code == expected_code
    deletes = requests_by(write_rsps, "DELETE")
    assert [call.request.headers.get("If-Match") for call in deletes] == ["1", "2"]
    if expected_code:
        assert "HTTP 409" in err


@pending
@pytest.mark.parametrize("selectors", [[], ["--username", "jdoe", "--member-uid", JDOE_UID]])
def test_remove_member_needs_exactly_one_selector(write_rsps: responses.RequestsMock, selectors: list[str]) -> None:
    code, _, err = run("lfx", "committee", "remove-member", UID, *selectors)

    assert code == 2
    assert "exactly one of" in err
    assert len(write_rsps.calls) == 0


def add_invite(rsps: responses.RequestsMock, status: int = 201, body: object = None) -> None:
    body = body if body is not None else {"uid": INVITE_UID, "invitee_email": EMAIL, "status": "pending"}
    rsps.post(
        f"{BASE}/committees/{UID}/invites", status=status, json=body, match=[matchers.query_param_matcher({"v": "1"})]
    )


@pending
@pytest.mark.parametrize("extra", [[], ["--json"]])
def test_invite_created(write_rsps: responses.RequestsMock, extra: list[str]) -> None:
    add_invite(write_rsps)

    code, out, err = run("lfx", "committee", "invite", UID, EMAIL, *extra)

    assert code == 0, err
    if extra:
        assert json.loads(out) == {"uid": INVITE_UID, "invitee_email": EMAIL, "status": "pending"}
    else:
        assert out == f"{INVITE_UID}\tpending\n"
    (post,) = requests_by(write_rsps, "POST")
    assert json_body(post) == {"invitee_email": EMAIL}


@pending
def test_invite_conflict_exits_1(write_rsps: responses.RequestsMock) -> None:
    add_invite(write_rsps, status=409, body={"message": f"a pending invite already exists for {EMAIL}"})

    code, out, err = run("lfx", "committee", "invite", UID, EMAIL)

    assert code == 1
    assert out == ""
    assert "HTTP 409" in err
    assert "a pending invite already exists" in err
    assert EMAIL not in err
