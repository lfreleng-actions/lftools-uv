# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for Gerrit commands that reported success after failing.

``gerrit addgithubrights`` must exit 1, granting nothing, when the
"GitHub Replication" group is missing. ``gerrit abandonchanges`` must
abandon every open change, not only the first, and exit 1 naming any it
could not abandon. ``gerrit addmavenconfig`` must stop before committing
or pushing when its settings are malformed.

Every network and git call is mocked: no test reaches a server or pushes.
"""

import configparser
import json
from collections.abc import Callable
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.git.gerrit import Gerrit as GitGerrit
from lftools_uv.typer_apps.gerrit import gerrit_app

FQDN = "gerrit.example.org"
PROJECT = "foo/bar"
PROJECT_ENCODED = "foo%2Fbar"
NEXUS3 = "nexus3.example.org"
CONTENT_LINK = "jenkins-config/managed-config-files/mavenSettings/foo-bar-settings/content"
CREDS_FILE = "jenkins-config/managed-config-files/mavenSettings/foo-bar-settings/serverCredentialMappings.yaml"

_REST_SETTINGS = {
    "username": "user",
    "password": "pass",
    "endpoint": "https://gerrit.example.org/a/",
}

Route = Callable[[str, str], requests.Response]


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, ["gerrit", *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(gerrit_app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])

XFAIL_855 = pytest.mark.xfail(strict=True, reason="#855: bad maven settings are still pushed")


def _response(status: int, body: object = None) -> requests.Response:
    """Build a Gerrit-style response, JSON behind the ``)]}'`` guard line."""
    response = requests.Response()
    response.status_code = status
    if body is None:
        response.headers["Content-Type"] = "text/plain"
        response._content = b"error" if status >= 400 else b""
    else:
        response.headers["Content-Type"] = "application/json"
        response._content = (")]}'\n" + json.dumps(body)).encode()
    return response


@pytest.fixture
def gerrit_api():
    """Route Gerrit REST calls to a per-test handler and record each one."""
    calls: list[tuple[str, str]] = []
    handler: dict[str, Route] = {}

    def fake_request(_session, method, url, **_kwargs):
        calls.append((method, url))
        return handler["route"](method, url)

    def install(route: Route) -> list[tuple[str, str]]:
        handler["route"] = route
        return calls

    with (
        patch("lftools_uv.api.endpoints.gerrit.config.get_setting", side_effect=lambda _s, o: _REST_SETTINGS[o]),
        patch("lftools_uv.api.endpoints.gerrit.time.sleep"),
        patch.object(requests.Session, "request", fake_request),
    ):
        yield install


def _posts(calls: list[tuple[str, str]]) -> list[str]:
    return [url for method, url in calls if method == "POST"]


# ---------------------------------------------------------------------------
# addgithubrights
# ---------------------------------------------------------------------------


def _github_route(groups: dict[str, object]) -> Route:
    def route(method: str, url: str) -> requests.Response:
        if method == "GET" and "groups/?m=GitHub%20Replication" in url:
            return _response(200, groups)
        if method == "POST" and f"projects/{PROJECT_ENCODED}/access" in url:
            return _response(200, {"refs/*": {}})
        return _response(404)

    return route


@FRONT_ENDS
def test_addgithubrights_missing_group_exits_1(run, gerrit_api):
    """With no GitHub Replication group, nothing is granted and it fails."""
    calls = gerrit_api(_github_route({}))

    result = run(["addgithubrights", FQDN, PROJECT])

    assert result.exit_code == 1
    assert _posts(calls) == []
    assert "GitHub rights added" not in result.output


@FRONT_ENDS
def test_addgithubrights_with_group_exits_0(run, gerrit_api):
    """With the group present, the access change is sent and it succeeds."""
    calls = gerrit_api(_github_route({"GitHub Replication": {"id": "abc123"}}))

    result = run(["addgithubrights", FQDN, PROJECT])

    assert result.exit_code == 0
    assert _posts(calls) == [f"https://gerrit.example.org/a/projects/{PROJECT_ENCODED}/access"]


# ---------------------------------------------------------------------------
# abandonchanges
# ---------------------------------------------------------------------------


def _abandon_route(
    change_ids: list[str],
    statuses: dict[str, int] | None = None,
    unreachable: frozenset[str] = frozenset(),
) -> Route:
    statuses = statuses or {}

    def route(method: str, url: str) -> requests.Response:
        if method == "GET" and "changes/?q=" in url:
            return _response(200, [{"id": cid, "status": "NEW"} for cid in change_ids])
        if method == "POST" and url.endswith("/abandon"):
            change_id = url.rsplit("/", 2)[-2]
            if change_id in unreachable:
                msg = f"connection lost abandoning {change_id}"
                raise requests.ConnectionError(msg)
            status = statuses.get(change_id, 200)
            if status == 200:
                return _response(200, {"id": change_id, "status": "ABANDONED"})
            return _response(status)
        return _response(404)

    return route


def _abandoned(calls: list[tuple[str, str]]) -> list[str]:
    return [url.rsplit("/", 2)[-2] for url in _posts(calls) if url.endswith("/abandon")]


@FRONT_ENDS
def test_abandonchanges_abandons_every_open_change(run, gerrit_api):
    """Every open change is abandoned, in order, and only open ones are queried."""
    calls = gerrit_api(_abandon_route(["c1", "c2", "c3"]))

    result = run(["abandonchanges", FQDN, PROJECT])

    assert result.exit_code == 0
    assert _abandoned(calls) == ["c1", "c2", "c3"]
    query = next(url for method, url in calls if method == "GET")
    assert f"project:{PROJECT_ENCODED}+status:open" in query


@FRONT_ENDS
def test_abandonchanges_failure_continues_and_exits_1(run, gerrit_api):
    """A change that cannot be abandoned does not stop the rest, and fails the run."""
    calls = gerrit_api(_abandon_route(["c1", "c2", "c3"], {"c2": 403}))

    result = run(["abandonchanges", FQDN, PROJECT])

    assert _abandoned(calls) == ["c1", "c2", "c3"]
    assert result.exit_code == 1


@FRONT_ENDS
def test_abandonchanges_transport_failure_continues_and_exits_1(run, gerrit_api):
    """A connection error on one change does not stop the rest, and fails the run."""
    calls = gerrit_api(_abandon_route(["c1", "c2", "c3"], unreachable=frozenset({"c2"})))

    result = run(["abandonchanges", FQDN, PROJECT])

    assert _abandoned(calls) == ["c1", "c2", "c3"]
    assert result.exit_code == 1


@FRONT_ENDS
def test_abandonchanges_conflict_is_skipped(run, gerrit_api):
    """A change closed since the query (409) is skipped, not a failure."""
    calls = gerrit_api(_abandon_route(["c1", "c2", "c3"], {"c2": 409}))

    result = run(["abandonchanges", FQDN, PROJECT])

    assert _abandoned(calls) == ["c1", "c2", "c3"]
    assert result.exit_code == 0


@FRONT_ENDS
def test_abandonchanges_nothing_open_prints_empty_list(run, gerrit_api):
    """With no open changes the command succeeds and prints an empty list."""
    calls = gerrit_api(_abandon_route([]))

    result = run(["abandonchanges", FQDN, PROJECT])

    assert result.exit_code == 0
    assert _abandoned(calls) == []
    assert result.output.strip().splitlines()[-1] == "[]"


# ---------------------------------------------------------------------------
# addmavenconfig
# ---------------------------------------------------------------------------


@pytest.fixture
def maven_settings(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, str]:
    """Answer ``lftools.ini`` lookups from a dict, inside ``tmp_path``."""
    monkeypatch.chdir(tmp_path)
    settings: dict[str, str] = {}

    def get_setting(section: str, option: str) -> str:
        if option not in settings:
            raise configparser.NoOptionError(option, section)
        return settings[option]

    monkeypatch.setattr("lftools_uv.git.gerrit.config.get_setting", get_setting)
    return settings


@pytest.fixture
def git_gerrit(maven_settings: dict[str, str]) -> GitGerrit:
    """A git Gerrit built without its constructor, which clones a repository."""
    g = object.__new__(GitGerrit)
    g.fqdn = FQDN
    g.project = "ci-management"
    g.repo = MagicMock()
    g.origin = MagicMock()
    g.default_branch = "master"
    return g


@pytest.fixture
def commit():
    with patch.object(GitGerrit, "commit") as mock_commit:
        yield mock_commit


@XFAIL_855
def test_addmavenconfig_malformed_json_raises(git_gerrit, maven_settings, commit):
    """Malformed ``additional_credentials`` stops the change before commit."""
    maven_settings["additional_credentials"] = "{not json"

    with pytest.raises(ValueError, match="additional_credentials"):
        git_gerrit.add_maven_config(FQDN, PROJECT, None)

    commit.assert_not_called()


@XFAIL_855
@pytest.mark.parametrize("ports", ["10001,abc", "70000"])
def test_addmavenconfig_bad_port_argument_raises(git_gerrit, commit, ports):
    """A port argument that is not a port number stops the change before commit."""
    with pytest.raises(ValueError, match="nexus3_ports"):
        git_gerrit.add_maven_config(FQDN, PROJECT, None, NEXUS3, ports)

    commit.assert_not_called()


@XFAIL_855
@pytest.mark.parametrize("ports", ["10001,abc", "70000"])
def test_addmavenconfig_bad_port_setting_raises(git_gerrit, maven_settings, commit, ports):
    """A ``lftools.ini`` port that is not a port number stops the change."""
    maven_settings["nexus3"] = NEXUS3
    maven_settings["nexus3_ports"] = ports

    with pytest.raises(ValueError, match="nexus3_ports"):
        git_gerrit.add_maven_config(FQDN, PROJECT, None)

    commit.assert_not_called()


@XFAIL_855
def test_addmavenconfig_regular_file_instead_of_symlink_raises(git_gerrit, commit):
    """A regular file where a symlink belongs stops the change before commit."""
    content = Path(CONTENT_LINK)
    content.parent.mkdir(parents=True)
    content.write_text("not a link\n")

    with pytest.raises(ValueError, match="not a symlink"):
        git_gerrit.add_maven_config(FQDN, PROJECT, None)

    commit.assert_not_called()


def test_addmavenconfig_valid_settings_push(git_gerrit, maven_settings, commit):
    """Valid settings are committed and pushed for review."""
    maven_settings["additional_credentials"] = '{"docker.example.org": "docker-creds"}'
    maven_settings["nexus3"] = NEXUS3
    maven_settings["nexus3_ports"] = "10001,10002"

    git_gerrit.add_maven_config(FQDN, PROJECT, None)

    commit.assert_called_once()
    assert commit.call_args.kwargs["push"] is True
    rendered = Path(CREDS_FILE).read_text()
    assert f'"{NEXUS3}:10001"' in rendered
    assert '"docker.example.org"' in rendered


@XFAIL_855
def test_addmavenconfig_strips_port_whitespace(git_gerrit, commit):
    """Whitespace around a port does not reach the rendered server ID."""
    git_gerrit.add_maven_config(FQDN, PROJECT, None, NEXUS3, "10001, 10002")

    commit.assert_called_once()
    rendered = Path(CREDS_FILE).read_text()
    assert f'"{NEXUS3}:10001"' in rendered
    assert f'"{NEXUS3}:10002"' in rendered
