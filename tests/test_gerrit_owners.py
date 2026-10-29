# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the owners ``gerrit list-project-permissions`` prints.

Only ``ALLOW`` owner rules count, and each group shows by name: the cn
for an LDAP group, the ``groups`` map's name for any other.

Every network call is mocked: no test reaches a server.
"""

import json
from unittest.mock import patch

import pytest
import requests
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.typer_apps.gerrit import gerrit_app

FQDN = "gerrit.example.org"
PROJECT = "foo/bar"

LDAP_UUID = "ldap:cn=lf-foo-owners,ou=Groups,dc=freestandards,dc=org"
SAML_UUID = "0123456789abcdef0123456789abcdef01234567"
REGISTERED_UUID = "global:Registered-Users"

GROUPS = {
    LDAP_UUID: {"name": "ldap/lf-foo-owners"},
    SAML_UUID: {"name": "saml/lf-foo-owners"},
    REGISTERED_UUID: {"name": "Registered Users"},
}

_REST_SETTINGS = {
    "username": "user",
    "password": "pass",
    "endpoint": "https://gerrit.example.org/a/",
}


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, ["gerrit", *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(gerrit_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


def _access_body(rules: dict[str, dict[str, str]]) -> dict[str, object]:
    return {PROJECT: {"local": {"refs/*": {"permissions": {"owner": {"rules": rules}}}}, "groups": GROUPS}}


@pytest.fixture
def gerrit_access():
    """Answer the access request with the owner rules a test supplies."""
    body: dict[str, object] = {}

    def fake_request(_session, _method, _url, **_kwargs):
        response = requests.Response()
        response.status_code = 200
        response.headers["Content-Type"] = "application/json"
        response._content = (")]}'\n" + json.dumps(body["access"])).encode()
        return response

    def install(rules: dict[str, dict[str, str]]) -> None:
        body["access"] = _access_body(rules)

    with (
        patch("lftools_uv.api.endpoints.gerrit.config.get_setting", side_effect=lambda _s, o: _REST_SETTINGS[o]),
        patch.object(requests.Session, "request", fake_request),
    ):
        yield install


def _owners(output: str) -> list[str]:
    return [line.strip("'\"") for line in output.splitlines() if line]


@pytest.mark.xfail(strict=True, reason="#973: owners show by UUID and BLOCK rules count")
@FRONT_ENDS
def test_owners_by_name_without_block(run, gerrit_access):
    """LDAP and SAML owners show by name; a BLOCK rule is not an owner."""
    gerrit_access(
        {
            LDAP_UUID: {"action": "ALLOW"},
            SAML_UUID: {"action": "ALLOW"},
            REGISTERED_UUID: {"action": "BLOCK"},
        }
    )

    result = run(["list-project-permissions", FQDN, PROJECT])

    assert result.exit_code == 0
    assert _owners(result.output) == ["lf-foo-owners", "saml/lf-foo-owners"]


@pytest.mark.xfail(strict=True, reason="#973: owners show by UUID and DENY rules count")
@FRONT_ENDS
def test_owners_without_deny(run, gerrit_access):
    """A DENY rule is not an owner."""
    gerrit_access({SAML_UUID: {"action": "ALLOW"}, REGISTERED_UUID: {"action": "DENY"}})

    result = run(["list-project-permissions", FQDN, PROJECT])

    assert result.exit_code == 0
    assert _owners(result.output) == ["saml/lf-foo-owners"]


@FRONT_ENDS
def test_ldap_owner_shows_cn(run, gerrit_access):
    """An LDAP owner shows by its cn, as before."""
    gerrit_access({LDAP_UUID: {"action": "ALLOW"}})

    result = run(["list-project-permissions", FQDN, PROJECT])

    assert result.exit_code == 0
    assert _owners(result.output) == ["lf-foo-owners"]
