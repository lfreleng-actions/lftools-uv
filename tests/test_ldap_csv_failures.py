# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``ldap csv`` when a lookup fails.

A missing group, an unreadable member, a failed bind and a failed query
must each be reported: the rows that could be read are still printed,
but the command exits 1 and logs the LDAP error detail.

python-ldap is not installed in development or CI, so a fake ``ldap``
module stands in for it: no test reaches an LDAP server.
"""

import importlib
import logging
import sys
import types
from collections.abc import Iterator
from typing import Any

import click
import pytest
from click.testing import CliRunner

import lftools_uv.cli

SERVER = "ldaps://ldap.example.org"
USER_BASE = "ou=Users,dc=example,dc=org"
GROUP_BASE = "ou=Groups,dc=example,dc=org"

FAKE_RES_SEARCH_ENTRY = 100
FAKE_RES_SEARCH_RESULT = 101

Entry = tuple[str, dict[str, list[bytes]]]


class FakeLDAPError(Exception):
    """Stand-in for ``ldap.LDAPError``."""


class FakeDirectory:
    """Entries keyed by (base DN, filter), plus the failures to inject."""

    def __init__(self) -> None:
        self.entries: dict[tuple[str, str], list[Entry]] = {}
        self.bind_error: Exception | None = None
        self.search_errors: dict[str, Exception] = {}

    def add_group(self, name: str, members: list[str]) -> None:
        """Add a group whose members are the given uids."""
        member_dns = [f"uid={uid},{USER_BASE}".encode() for uid in members]
        self.entries[(GROUP_BASE, f"cn={name}")] = [(f"cn={name},{GROUP_BASE}", {"member": member_dns})]

    def add_user(self, uid: str, *, mail: bool = True) -> None:
        """Add a user entry, optionally without a ``mail`` attribute."""
        attrs = {"uid": [uid.encode()], "cn": [uid.capitalize().encode()]}
        if mail:
            attrs["mail"] = [f"{uid}@example.org".encode()]
        self.entries[(USER_BASE, f"uid={uid}")] = [(f"uid={uid},{USER_BASE}", attrs)]


class FakeConnection:
    """The subset of ``LDAPObject`` that ``ldap csv`` uses."""

    def __init__(self, directory: FakeDirectory) -> None:
        self.directory = directory
        self.protocol_version = 0
        self.pending: dict[int, list[Entry]] = {}

    def simple_bind_s(self) -> None:
        if self.directory.bind_error is not None:
            raise self.directory.bind_error

    def search(self, dn: str, scope: int, search_filter: str, attrs: list[str]) -> int:
        del scope, attrs
        if search_filter in self.directory.search_errors:
            raise self.directory.search_errors[search_filter]
        msgid = len(self.pending) + 1
        self.pending[msgid] = list(self.directory.entries.get((dn, search_filter), []))
        return msgid

    def result(self, msgid: int, _all: int) -> tuple[Any, list[Entry]]:
        entries = self.pending[msgid]
        if entries:
            return FAKE_RES_SEARCH_ENTRY, [entries.pop(0)]
        return FAKE_RES_SEARCH_RESULT, []

    def unbind_s(self) -> None:
        return None


@pytest.fixture
def directory() -> FakeDirectory:
    """An empty fake directory for each test to populate."""
    return FakeDirectory()


@pytest.fixture
def ldap_group(monkeypatch: pytest.MonkeyPatch, directory: FakeDirectory) -> Iterator[click.Group]:
    """Load the real ``ldap_cli`` module against a fake ``ldap`` module."""
    fake = types.ModuleType("ldap")
    attributes = {
        "LDAPError": FakeLDAPError,
        "VERSION3": 3,
        "SCOPE_SUBTREE": 2,
        "RES_SEARCH_ENTRY": FAKE_RES_SEARCH_ENTRY,
        "initialize": lambda server: FakeConnection(directory),
    }
    for name, value in attributes.items():
        setattr(fake, name, value)
    monkeypatch.setitem(sys.modules, "ldap", fake)
    monkeypatch.delitem(sys.modules, "lftools_uv.cli.ldap_cli", raising=False)
    # Importing the module rebinds the package attribute; restore it after.
    monkeypatch.setattr(lftools_uv.cli, "ldap_cli", lftools_uv.cli.ldap_cli)
    module = importlib.import_module("lftools_uv.cli.ldap_cli")
    yield module.ldap_cli
    sys.modules.pop("lftools_uv.cli.ldap_cli", None)


def _run_csv(group: click.Group, groups: str) -> Any:
    args = ["csv", groups, "--ldap-server", SERVER, "--ldap-user-base", USER_BASE, "--ldap-group-base", GROUP_BASE]
    return CliRunner().invoke(group, args)


def test_readable_group_exits_zero(ldap_group: click.Group, directory: FakeDirectory) -> None:
    """Every member readable: one row per member and exit 0."""
    directory.add_group("grp", ["alice", "bob"])
    directory.add_user("alice")
    directory.add_user("bob")

    result = _run_csv(ldap_group, "grp")

    assert result.exit_code == 0, result.output
    assert result.output.splitlines() == ["grp,alice,Alice,alice@example.org", "grp,bob,Bob,bob@example.org"]


@pytest.mark.xfail(strict=True, reason="#865: ldap csv exits 0 on an unreadable member")
def test_member_without_mail_fails(
    ldap_group: click.Group, directory: FakeDirectory, caplog: pytest.LogCaptureFixture
) -> None:
    """A member lacking ``mail`` is logged and fails the run."""
    directory.add_group("grp", ["alice", "bob"])
    directory.add_user("alice")
    directory.add_user("bob", mail=False)

    with caplog.at_level(logging.ERROR):
        result = _run_csv(ldap_group, "grp")

    assert result.exit_code == 1
    assert "grp,alice,Alice,alice@example.org" in result.output
    assert "Error parsing user: uid=bob" in caplog.text


@pytest.mark.xfail(strict=True, reason="#865: ldap csv exits 0 on a missing user entry")
def test_member_without_entry_fails(ldap_group: click.Group, directory: FakeDirectory) -> None:
    """A member with no user entry fails the run; other rows still print."""
    directory.add_group("grp", ["alice", "ghost"])
    directory.add_user("alice")

    result = _run_csv(ldap_group, "grp")

    assert result.exit_code == 1
    assert "grp,alice,Alice,alice@example.org" in result.output


@pytest.mark.xfail(strict=True, reason="#865: ldap csv exits 0 on an unknown group")
def test_unknown_group_fails(ldap_group: click.Group, caplog: pytest.LogCaptureFixture) -> None:
    """A group that does not exist is named in an error and fails the run."""
    with caplog.at_level(logging.ERROR):
        result = _run_csv(ldap_group, "nosuchgroup")

    assert result.exit_code == 1
    assert "nosuchgroup" in caplog.text


@pytest.mark.xfail(strict=True, reason="#865: ldap csv exits 0 on an unknown group")
def test_unknown_group_keeps_other_rows(ldap_group: click.Group, directory: FakeDirectory) -> None:
    """An unknown group fails the run, but later groups are still read."""
    directory.add_group("grp", ["alice"])
    directory.add_user("alice")

    result = _run_csv(ldap_group, "nosuchgroup grp")

    assert result.exit_code == 1
    assert "grp,alice,Alice,alice@example.org" in result.output


@pytest.mark.xfail(strict=True, reason="#865: a bind failure raises AttributeError for .message")
@pytest.mark.parametrize(
    ("error", "detail"),
    [
        (
            FakeLDAPError({"desc": "Can't contact LDAP server", "info": "TLS failure"}),
            "Can't contact LDAP server: TLS failure",
        ),
        (FakeLDAPError("plain failure"), "plain failure"),
    ],
)
def test_bind_failure_logs_detail(
    ldap_group: click.Group,
    directory: FakeDirectory,
    caplog: pytest.LogCaptureFixture,
    error: Exception,
    detail: str,
) -> None:
    """A failed bind exits 1 and logs the server and the LDAP error detail."""
    directory.bind_error = error

    with caplog.at_level(logging.ERROR):
        result = _run_csv(ldap_group, "grp")

    assert isinstance(result.exception, SystemExit)
    assert result.exit_code == 1
    assert SERVER in caplog.text
    assert detail in caplog.text


@pytest.mark.xfail(strict=True, reason="#865: a failed query exits 1 without logging")
def test_query_failure_logs_detail(
    ldap_group: click.Group, directory: FakeDirectory, caplog: pytest.LogCaptureFixture
) -> None:
    """A failed query logs the filter, the base DN and the error detail."""
    directory.search_errors["cn=grp"] = FakeLDAPError({"desc": "Size limit exceeded"})

    with caplog.at_level(logging.ERROR):
        result = _run_csv(ldap_group, "grp")

    assert result.exit_code == 1
    assert "Size limit exceeded" in caplog.text
    assert "cn=grp" in caplog.text
    assert GROUP_BASE in caplog.text
