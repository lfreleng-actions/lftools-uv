# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``yaml4info`` and ``infofile create-info-file`` reading LFX committees.

``helper_yaml4info`` and the ``yaml4info`` console script list the
members of the committee whose SSO group name they are given, as INFO.yaml
committer entries. ``responses`` answers every request, and ``PATH`` holds
nothing, so no test reaches a server or runs another program.
"""

from __future__ import annotations

import configparser
import sys
from typing import TYPE_CHECKING, Any

import pytest
import responses
from click.testing import CliRunner as ClickRunner
from responses import matchers
from typer.testing import CliRunner as TyperRunner

from lftools_uv import ldap_cli
from lftools_uv.api.endpoints.lfx import LfxAPIError, LfxNotFoundError
from lftools_uv.api.endpoints.lfx import config as lfx_config
from lftools_uv.cli import cli
from lftools_uv.cli_app import app as typer_app
from lftools_uv.shell import yaml4info

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from pytest_mock import MockerFixture

BASE = "https://lfx.example.org"
TOKEN = "s3cr3t-token-value"  # noqa: S105
UID = "11111111-2222-4333-8444-555555555555"
GROUP = "example-gerrit-foo-bar-committers"

MEMBERS = [
    {"username": "jdoe", "email": "jdoe@example.org", "first_name": "Jane", "last_name": "Doe"},
    {
        "username": "cobrien",
        "email": "conor@corp.example.com",
        "first_name": "Conor",
        "last_name": "O'Brien",
        "organization": {"name": "Example Corp"},
    },
    {"username": "", "email": "amy@example.net", "first_name": "Amy", "last_name": "Newcomer"},
]

ENTRIES = (
    "    - name: 'Conor O''Brien'\n"
    "      email: 'conor@corp.example.com'\n"
    "      company: 'Example Corp'\n"
    "      id: 'cobrien'\n"
    "      timezone: 'Unknown/Unknown'\n"
    "    - name: 'Jane Doe'\n"
    "      email: 'jdoe@example.org'\n"
    "      company: 'example'\n"
    "      id: 'jdoe'\n"
    "      timezone: 'Unknown/Unknown'\n"
)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the client at a mocked API with a token, and hide lftools.ini and PATH."""
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    monkeypatch.setenv("LFX_API_URL", BASE)

    def no_section(section: str, option: str) -> str:
        raise configparser.NoSectionError(section)

    monkeypatch.setattr(lfx_config.lf_config, "get_setting", no_section)
    monkeypatch.setenv("PATH", str(tmp_path))


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    # Each test checks the calls it needs, so an expected failure that stops
    # before a request does not turn into a teardown error.
    with responses.RequestsMock(assert_all_requests_are_fired=False) as mock:
        yield mock


def add_query(rsps: responses.RequestsMock, uids: list[str], group: str = GROUP) -> None:
    rsps.get(
        f"{BASE}/query/resources",
        json={
            "resources": [{"type": "committee", "data": {"uid": uid, "sso_group_name": group}} for uid in uids],
            "page_token": None,
        },
        match=[matchers.query_param_matcher({"v": "1", "type": "committee", "tags": f"sso_group_name:{group}"})],
    )


def add_members(rsps: responses.RequestsMock, status: int = 200, body: Any = MEMBERS) -> None:
    rsps.get(f"{BASE}/committees/{UID}/members", status=status, json=body)


# ---------------------------------------------------------------------------
# helper_yaml4info


def test_helper_lists_committee_members(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [UID])
    add_members(rsps)

    assert ldap_cli.helper_yaml4info(GROUP) == ENTRIES


def test_helper_unknown_committee_raises(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [])

    with pytest.raises(LfxNotFoundError):
        ldap_cli.helper_yaml4info(GROUP)


def test_helper_403_raises(rsps: responses.RequestsMock) -> None:
    add_query(rsps, [UID])
    add_members(rsps, status=403, body={"message": "access denied"})

    with pytest.raises(LfxAPIError) as excinfo:
        ldap_cli.helper_yaml4info(GROUP)
    assert excinfo.value.status == 403


# ---------------------------------------------------------------------------
# The yaml4info console script


def run_script(monkeypatch: pytest.MonkeyPatch, args: list[str]) -> int:
    """Run the console script as its entry point does, and return its exit status."""
    monkeypatch.setattr(sys, "argv", ["yaml4info", *args])
    code: int = yaml4info.main()
    return code


def test_script_prints_committee_members(
    rsps: responses.RequestsMock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    add_query(rsps, [UID])
    add_members(rsps)

    code = run_script(monkeypatch, [GROUP])

    out, err = capsys.readouterr()
    assert code == 0, err
    assert out == ENTRIES


def test_script_unknown_committee_fails(
    rsps: responses.RequestsMock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    add_query(rsps, [])

    code = run_script(monkeypatch, [GROUP])

    out, err = capsys.readouterr()
    assert code != 0
    assert out == ""
    assert GROUP in err
    assert len(rsps.calls) == 1


def test_script_403_names_auditor(
    rsps: responses.RequestsMock, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    add_query(rsps, [UID])
    add_members(rsps, status=403, body={"message": "access denied"})

    code = run_script(monkeypatch, [GROUP])

    out, err = capsys.readouterr()
    assert code != 0
    assert out == ""
    assert "auditor" in err
    assert TOKEN not in err


@pytest.mark.parametrize(("args", "code"), [([], 1), (["-h"], 0)], ids=["no-argument", "help"])
def test_script_usage(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, args: list[str], code: int
) -> None:
    assert run_script(monkeypatch, args) == code

    out, _ = capsys.readouterr()
    assert "Usage:" in out
    assert "sso-group-name" in out


@pytest.mark.parametrize("args", [["-x"], [GROUP, "other-group"]], ids=["unknown-option", "two-groups"])
def test_script_refuses_bad_arguments(
    capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch, args: list[str]
) -> None:
    assert run_script(monkeypatch, args) == 1

    out, err = capsys.readouterr()
    assert out == ""
    assert err


# ---------------------------------------------------------------------------
# infofile create-info-file, in both front ends


def _click(args: list[str]) -> Any:
    return ClickRunner().invoke(cli, args, obj={})


def _typer(args: list[str]) -> Any:
    return TyperRunner().invoke(typer_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_click, _typer], ids=["click", "typer"])


@pytest.fixture
def gerrit(mocker: MockerFixture) -> None:
    """Answer Gerrit's access request with a project that has an owner."""
    mocker.patch("lftools_uv.cli.infofile.config.get_setting", return_value="secret")
    rest = mocker.patch("lftools_uv.cli.infofile.GerritRestAPI")
    rest.return_value.get.return_value = {"local": {"refs/*": {"permissions": {"owner": {"rules": {"o": {}}}}}}}


@FRONT_ENDS
@pytest.mark.usefixtures("gerrit")
def test_create_info_file_lists_committee(rsps: responses.RequestsMock, run: Any) -> None:
    add_query(rsps, [UID])
    add_members(rsps)

    result = run(["infofile", "create-info-file", "gerrit.example.org", "foo/bar"])

    assert result.exit_code == 0, result.output
    assert f"    - <<: *example_foo_bar_ptl\n{ENTRIES}tsc:\n" in result.stdout


@FRONT_ENDS
@pytest.mark.usefixtures("gerrit")
@pytest.mark.parametrize("status", [None, 403], ids=["not-found", "forbidden"])
def test_create_info_file_failed_lookup_prints_nothing(
    rsps: responses.RequestsMock, run: Any, status: int | None
) -> None:
    if status is None:
        add_query(rsps, [])
    else:
        add_query(rsps, [UID])
        add_members(rsps, status=status, body={"message": "access denied"})

    result = run(["infofile", "create-info-file", "gerrit.example.org", "foo/bar"])

    assert result.exit_code != 0
    assert result.stdout == ""
    assert rsps.calls
