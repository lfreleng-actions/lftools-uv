# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``lftools-uv lfx committee inactive`` and ``inactivecommitters``.

``responses`` answers both the LFX API and Gerrit, so no test reaches a
server. The mocked Gerrit answers a change query as a real one does: with
its ``)]}'`` prefix, and with HTTP 400 ``Account ... not found`` for an
LFID it does not know.
"""

from __future__ import annotations

import configparser
import json
import re
import sys
from datetime import date, timedelta
from importlib.metadata import entry_points
from typing import TYPE_CHECKING
from urllib.parse import parse_qs, urlsplit

import pytest
import requests
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
GROUP = "example-gerrit-foo-committers"
GERRIT = "https://gerrit.example.org/r"
CHANGES = re.compile(re.escape(GERRIT) + r"/changes/")

TODAY = date.today()
RECENT = TODAY - timedelta(days=30)
OLD = TODAY - timedelta(days=500)


def member(username: str, email: str, first: str, last: str) -> dict[str, object]:
    return {"username": username, "email": email, "first_name": first, "last_name": last}


MEMBERS = [
    member("dave", "dave@example.org", "Dave", "Example"),
    member("bob", "bob@example.org", "Bob", "Example"),
    member("", "zed@example.org", "Zed", "Nobody"),
    member("carol", "carol@example.org", "Carol", "Example"),
    member("alice", "alice@example.org", "Alice", "Example"),
]

EXPECTED_LINES = [
    f"  OK alice, Alice Example, alice@example.org last submission or review {RECENT}",
    f"  WARNING bob, Bob Example, bob@example.org inactive since {OLD} 500 days ago",
    "  ERROR carol, Carol Example, carol@example.org has no activity",
    "  ERROR dave, Dave Example, dave@example.org has no Gerrit account",
]


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the client at a mocked API with a token, and hide lftools.ini and ~/.netrc."""
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    monkeypatch.setenv("LFX_API_URL", BASE)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("NETRC", raising=False)

    def no_section(section: str, option: str) -> str:
        raise configparser.NoSectionError(section)

    monkeypatch.setattr(lfx_config.lf_config, "get_setting", no_section)
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def run(*args: str) -> tuple[int, str, str]:
    result = CliRunner().invoke(app, list(args))
    return result.exit_code, result.stdout, result.stderr


def add_committee(rsps: responses.RequestsMock, members: list[dict[str, object]] = MEMBERS) -> None:
    rsps.get(
        f"{BASE}/query/resources",
        json={
            "resources": [
                {"type": "committee", "id": f"committee:{UID}", "data": {"uid": UID, "sso_group_name": GROUP}}
            ],
            "page_token": None,
        },
        match=[matchers.query_param_matcher({"v": "1", "type": "committee", "tags": f"sso_group_name:{GROUP}"})],
    )
    rsps.get(f"{BASE}/committees/{UID}/members", json=members, match=[matchers.query_param_matcher({"v": "1"})])


def _change(updated: date) -> str:
    return json.dumps([{"id": "1", "updated": f"{updated} 10:00:00.000000000"}], separators=(",", ":"))


def gerrit(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
    """Answer a change query: alice is recent, bob old, carol idle, dave unknown."""
    query = parse_qs(urlsplit(request.url or "").query)["q"][0]
    json_type = {"Content-Type": "application/json; charset=utf-8"}
    if "dave" in query:
        return 400, {"Content-Type": "text/plain"}, "Account 'dave' not found\n"
    if "alice" in query:
        return 200, json_type, ")]}'\n" + _change(RECENT)
    if "bob" in query and "after:" not in query:
        return 200, json_type, ")]}'\n" + _change(OLD)
    return 200, json_type, ")]}'\n[]"


def add_gerrit(rsps: responses.RequestsMock) -> None:
    rsps.add_callback(responses.GET, CHANGES, callback=gerrit)


def queries(rsps: responses.RequestsMock) -> list[str]:
    return [
        parse_qs(urlsplit(call.request.url or "").query)["q"][0]
        for call in rsps.calls
        if "/changes/" in str(call.request.url)
    ]


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
@pytest.mark.parametrize("url", ["gerrit.example.org/r", GERRIT, GERRIT + "/"])
def test_reports_each_member(rsps: responses.RequestsMock, url: str) -> None:
    """One line per member; a member without a username is skipped and counted."""
    add_committee(rsps)
    add_gerrit(rsps)

    code, out, err = run("lfx", "committee", "inactive", url, GROUP)

    assert code == 0, err
    assert [line for line in out.splitlines() if line.startswith("  ")] == EXPECTED_LINES
    assert "1 member without a username" in err
    assert not any("zed" in query for query in queries(rsps))


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
@pytest.mark.parametrize(("first", "shown"), [("Jane\nAnn", "Jane\\nAnn"), ("Jane\r\nAnn", "Jane\\r\\nAnn")])
def test_line_break_in_name_stays_on_one_line(first: str, shown: str) -> None:
    # Called directly: CliRunner folds CRLF in captured output into LF.
    from lftools_uv.typer_apps.lfx.inactive import format_entry

    entry = {
        "username": "jdoe",
        "name": f"{first} Doe",
        "email": "jdoe@example.org",
        "status": "no_activity",
        "last_activity": None,
        "days_ago": None,
    }

    assert format_entry(entry).splitlines() == [f"  ERROR jdoe, {shown} Doe, jdoe@example.org has no activity"]


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
def test_line_break_in_name_is_kept_in_json(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, [member("carol", "carol@example.org", "Carol\nAnn", "Example")])
    add_gerrit(rsps)

    code, out, err = run("lfx", "committee", "inactive", GERRIT, GROUP, "--json")

    assert code == 0, err
    assert json.loads(out)[0]["name"] == "Carol\nAnn Example"


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
def test_unknown_account_is_not_queried_again(rsps: responses.RequestsMock) -> None:
    add_committee(rsps, [MEMBERS[0]])
    add_gerrit(rsps)

    code, _, err = run("lfx", "committee", "inactive", GERRIT, GROUP)

    assert code == 0, err
    assert len(queries(rsps)) == 1


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
@pytest.mark.parametrize(("months", "low", "high"), [(None, 364, 366), ("3", 89, 92)])
def test_months_sets_the_cut_off(rsps: responses.RequestsMock, months: str | None, low: int, high: int) -> None:
    add_committee(rsps, [MEMBERS[4]])
    add_gerrit(rsps)
    extra = ["--months", months] if months else []

    code, _, err = run("lfx", "committee", "inactive", GERRIT, GROUP, *extra)

    assert code == 0, err
    (query,) = queries(rsps)
    cut_off = date.fromisoformat(re.findall(r"after:(\S+)", query)[0])
    assert low <= (TODAY - cut_off).days <= high
    assert "reviewedby:alice" in query
    assert "owner:alice" in query


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
def test_json(rsps: responses.RequestsMock) -> None:
    add_committee(rsps)
    add_gerrit(rsps)

    code, out, err = run("lfx", "committee", "inactive", GERRIT, GROUP, "--json")

    assert code == 0, err
    report = json.loads(out)
    assert [(item["username"], item["status"], item["last_activity"]) for item in report] == [
        ("alice", "ok", str(RECENT)),
        ("bob", "inactive", str(OLD)),
        ("carol", "no_activity", None),
        ("dave", "no_account", None),
    ]
    assert report[1]["days_ago"] == 500


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
@pytest.mark.parametrize(
    "answer",
    [
        {"status": 503, "body": "Service Unavailable"},
        {"status": 400, "body": "invalid query"},
        {"status": 400, "body": "Change 'bob' not found"},
        {"body": requests.ConnectionError("cannot connect")},
    ],
)
def test_gerrit_failure_exits_1(rsps: responses.RequestsMock, answer: dict[str, object]) -> None:
    """A failed query must not make the member look inactive."""
    add_committee(rsps, [MEMBERS[1]])
    rsps.get(CHANGES, **answer)

    code, out, err = run("lfx", "committee", "inactive", GERRIT, GROUP)

    assert code == 1
    assert "  " not in out
    assert "Error:" in err


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
def test_unknown_committee_exits_3(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/query/resources", json={"resources": [], "page_token": None})

    code, out, err = run("lfx", "committee", "inactive", GERRIT, GROUP)

    assert code == 3
    assert out == ""
    assert "Error:" in err


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
def test_refuses_plain_http(rsps: responses.RequestsMock) -> None:
    """~/.netrc credentials must not travel in clear."""
    code, _, err = run("lfx", "committee", "inactive", "http://gerrit.example.org/r", GROUP)

    assert code == 2
    assert "https://" in err
    assert len(rsps.calls) == 0


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
@pytest.mark.parametrize("url", ["https://user:s3cret@gerrit.example.org/r", "user:s3cret@gerrit.example.org/r"])
def test_refuses_credentials_in_url(rsps: responses.RequestsMock, url: str) -> None:
    """A password in GERRIT_URL would be printed; ~/.netrc is the way to log in."""
    code, out, err = run("lfx", "committee", "inactive", url, GROUP)

    assert code == 2
    assert "s3cret" not in out + err
    assert ".netrc" in err
    assert len(rsps.calls) == 0


@pytest.mark.xfail(strict=True, reason="lfx committee inactive is not implemented yet")
def test_does_not_follow_a_redirect(rsps: responses.RequestsMock, tmp_path: Path) -> None:
    """Following HTTPS to HTTP would resend the ~/.netrc credentials in clear."""
    netrc = tmp_path / ".netrc"
    netrc.write_text("machine gerrit.example.org login jdoe password s3cret\n")
    netrc.chmod(0o600)
    add_committee(rsps, [MEMBERS[4]])
    insecure = re.compile(r"http://gerrit\.example\.org/")
    rsps.get(insecure, body="")
    rsps.get(
        re.compile(re.escape(GERRIT) + r"/a/changes/"),
        status=302,
        headers={"Location": "http://gerrit.example.org/r/a/changes/"},
    )

    code, out, err = run("lfx", "committee", "inactive", GERRIT, GROUP)

    gerrit_calls = [
        call.request for call in rsps.calls if "gerrit.example.org" in str(urlsplit(call.request.url).netloc)
    ]
    assert not [request.url for request in gerrit_calls if str(request.url).startswith("http://")]
    assert gerrit_calls
    assert str(gerrit_calls[0].headers.get("Authorization", "")).startswith("Basic ")
    assert code == 1
    assert "  " not in out
    assert "redirect" in err


@pytest.mark.xfail(strict=True, reason="the inactivecommitters console script still runs the shell script")
def test_console_script_takes_two_arguments(
    rsps: responses.RequestsMock, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    (entry_point,) = entry_points(group="console_scripts", name="inactivecommitters")
    main = entry_point.load()
    add_committee(rsps)
    add_gerrit(rsps)
    monkeypatch.setattr(sys, "argv", ["inactivecommitters", "gerrit.example.org/r", GROUP])

    with pytest.raises(SystemExit) as exc:
        main()

    out = capsys.readouterr().out
    assert exc.value.code == 0
    assert [line for line in out.splitlines() if line.startswith("  ")] == EXPECTED_LINES
