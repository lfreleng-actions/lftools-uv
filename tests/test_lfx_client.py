# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the LFX v2 API client: configuration, token, requests and lookup.

``responses`` answers every request, so no test reaches a server.
"""

from __future__ import annotations

import base64
import configparser
import json
import logging
import stat
import time
from typing import TYPE_CHECKING, SupportsIndex
from urllib.parse import quote, quote_plus

import pytest
import requests
import responses
from responses import matchers

from lftools_uv import config as lf_config
from lftools_uv.api.endpoints import lfx
from lftools_uv.api.endpoints.lfx import client as lfx_client
from lftools_uv.api.endpoints.lfx import config as lfx_config

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

BASE = "https://lfx.example.org"
TOKEN = "s3cr3t-token-value"  # noqa: S105
UID = "11111111-2222-4333-8444-555555555555"
OTHER_UID = "99999999-2222-4333-8444-555555555555"
GROUP = "example-gerrit-foo-committers"
REAL_GET_SETTING = lf_config.get_setting


def make_jwt(claims: object) -> str:
    """Return an unsigned JWT-shaped token carrying ``claims``."""

    def part(value: object) -> str:
        return base64.urlsafe_b64encode(json.dumps(value).encode()).rstrip(b"=").decode()

    return f"{part({'alg': 'RS256', 'typ': 'JWT'})}.{part(claims)}.c2lnbmF0dXJl"


def resource(uid: str, sso_group_name: str) -> dict[str, object]:
    return {
        "type": "committee",
        "id": f"committee:{uid}",
        "data": {"uid": uid, "name": "Example Committers", "sso_group_name": sso_group_name},
    }


def write_stub_lfx(directory: Path, script: str) -> None:
    """Create an executable ``lfx`` stub in ``directory`` at run time."""
    stub = directory / "lfx"
    stub.write_text(f"#!/bin/sh\n{script}\n")
    stub.chmod(stub.stat().st_mode | stat.S_IXUSR)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Clear the LFX variables, hide lftools.ini and any real ``lfx``."""
    monkeypatch.delenv("LFX_TOKEN", raising=False)
    monkeypatch.delenv("LFX_API_URL", raising=False)

    def no_section(section: str, option: str) -> str:
        raise configparser.NoSectionError(section)

    monkeypatch.setattr(lfx_config.lf_config, "get_setting", no_section)
    empty = tmp_path / "empty-path"
    empty.mkdir()
    monkeypatch.setenv("PATH", str(empty))


@pytest.fixture
def rsps() -> Iterator[responses.RequestsMock]:
    with responses.RequestsMock() as mock:
        yield mock


def client() -> lfx.LfxClient:
    return lfx.LfxClient(base_url=BASE, token=TOKEN)


# Base URL


def test_base_url_defaults() -> None:
    assert lfx.resolve_base_url() == lfx.DEFAULT_API_URL


def test_base_url_from_ini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lfx_config.lf_config, "get_setting", lambda s, o: "https://ini.example.org/")
    assert lfx.resolve_base_url() == "https://ini.example.org"


def test_base_url_env_beats_ini(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(lfx_config.lf_config, "get_setting", lambda s, o: "https://ini.example.org")
    monkeypatch.setenv("LFX_API_URL", "https://env.example.org")
    assert lfx.resolve_base_url() == "https://env.example.org"


@pytest.mark.parametrize("url", ["http://lfx.example.org", "lfx.example.org", "https://"])
def test_base_url_refuses_non_https(monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, url: str) -> None:
    monkeypatch.setenv("LFX_API_URL", url)
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    with pytest.raises(lfx.LfxConfigError, match="https://"):
        lfx.LfxClient()
    assert len(rsps.calls) == 0


@pytest.mark.parametrize("url", ["http://lfx.example.org", "lfx.example.org", "https://", ""])
def test_explicit_base_url_refuses_non_https(rsps: responses.RequestsMock, url: str) -> None:
    with pytest.raises(lfx.LfxConfigError, match="https://"):
        lfx.LfxClient(base_url=url, token=TOKEN)
    assert len(rsps.calls) == 0


@pytest.mark.parametrize(
    "url", ["https://[broken", "https://lfx.example.org:notaport", "https://lfx.example.org:99999"]
)
def test_malformed_base_url_is_config_error(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, url: str
) -> None:
    monkeypatch.setenv("LFX_API_URL", url)
    with pytest.raises(lfx.LfxConfigError, match="https://") as raised:
        lfx.LfxClient()
    assert "LFX_TOKEN" not in str(raised.value)
    assert len(rsps.calls) == 0


@pytest.mark.parametrize(
    "url",
    [
        "https://lfx.example.org/api?key=k3y",
        "https://lfx.example.org/api#fr4g",
        "https://lfx.example.org/api?",
        "https://lfx.example.org/api#",
    ],
)
def test_base_url_refuses_query_or_fragment(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, url: str
) -> None:
    for build in (lambda: lfx.LfxClient(base_url=url, token=TOKEN), lfx.LfxClient):
        monkeypatch.setenv("LFX_API_URL", url)
        monkeypatch.setenv("LFX_TOKEN", TOKEN)
        with pytest.raises(lfx.LfxConfigError, match="query or fragment") as raised:
            build()
        assert "k3y" not in str(raised.value)
        assert "fr4g" not in str(raised.value)
    assert len(rsps.calls) == 0


def test_refused_base_url_credentials_redacted() -> None:
    with pytest.raises(lfx.LfxConfigError) as raised:
        lfx.LfxClient(base_url="http://alice:hunter2@lfx.example.org/api?key=k3y#frag", token=TOKEN)
    assert "hunter2" not in str(raised.value)
    assert "k3y" not in str(raised.value)
    assert "lfx.example.org" not in str(raised.value)
    assert str(raised.value).startswith("base_url must be an https:// URL")


@pytest.mark.parametrize(
    "url",
    [
        f"http://lfx.example.org/{TOKEN}",
        f"https://{TOKEN}.example.org/api?",
        f"https://lfx.example.org/{TOKEN}#",
        f"https://lfx.example.org:{TOKEN}",
    ],
)
def test_refused_base_url_never_shows_token(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, url: str
) -> None:
    monkeypatch.setenv("LFX_API_URL", url)
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    with pytest.raises(lfx.LfxConfigError) as raised:
        lfx.LfxClient()
    assert TOKEN not in str(raised.value)
    assert str(raised.value).startswith("LFX_API_URL ")
    assert len(rsps.calls) == 0


@pytest.mark.parametrize(
    "ini",
    [
        f"[lfx]\nurl = {BASE}\n{TOKEN}\n",
        f"{TOKEN}\n[lfx]\n",
        f"[lfx]\n{TOKEN} = 1\n{TOKEN} = 2\n",
        f"[{TOKEN}]\n[{TOKEN}]\n[lfx]\n",
    ],
    ids=["parsing", "missing-section-header", "duplicate-option", "duplicate-section"],
)
def test_malformed_ini_never_shows_token(
    monkeypatch: pytest.MonkeyPatch,
    rsps: responses.RequestsMock,
    caplog: pytest.LogCaptureFixture,
    tmp_path: Path,
    ini: str,
) -> None:
    path = tmp_path / "lftools.ini"
    _ = path.write_text(ini)
    monkeypatch.setattr(lf_config, "LFTOOLS_CONFIG_FILE", str(path))
    monkeypatch.setattr(lf_config, "get_setting", REAL_GET_SETTING)
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    with caplog.at_level(logging.DEBUG), pytest.raises(lfx.LfxConfigError) as raised:
        lfx.LfxClient()
    assert str(raised.value) == "lftools.ini cannot be parsed; fix it or set LFX_API_URL"
    assert raised.value.__suppress_context__
    assert TOKEN not in caplog.text
    assert len(rsps.calls) == 0


def test_base_url_credentials_not_logged_or_shown(
    rsps: responses.RequestsMock, caplog: pytest.LogCaptureFixture
) -> None:
    secret_base = "https://alice:hunter2@lfx.example.org"
    rsps.get(f"{secret_base}/committees/{UID}", json={"uid": UID})
    rsps.get(f"{secret_base}/committees/x", body=requests.ConnectionError(f"failed: {secret_base}/committees/x"))
    secret_client = lfx.LfxClient(base_url=secret_base, token=TOKEN)
    with caplog.at_level(logging.DEBUG, logger="lftools_uv.api.endpoints.lfx"):
        secret_client.get_json(f"/committees/{UID}")
        with pytest.raises(lfx.LfxAPIError) as raised:
            secret_client.get_json("/committees/x")
    assert caplog.records
    assert "hunter2" not in caplog.text
    assert "hunter2" not in str(raised.value)
    assert "hunter2" not in repr(secret_client)


# Token


def test_token_from_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    assert lfx.resolve_token() == TOKEN


def test_token_from_lfx_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_stub_lfx(tmp_path, f'[ "$1 $2" = "auth token" ] && echo {TOKEN} || exit 9')
    monkeypatch.setenv("PATH", str(tmp_path))
    assert lfx.resolve_token() == TOKEN


def test_env_token_beats_lfx_cli(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_stub_lfx(tmp_path, "echo from-cli")
    monkeypatch.setenv("PATH", str(tmp_path))
    monkeypatch.setenv("LFX_TOKEN", TOKEN)
    assert lfx.resolve_token() == TOKEN


def test_no_token_names_both_sources() -> None:
    with pytest.raises(lfx.LfxConfigError) as raised:
        lfx.resolve_token()
    assert "LFX_TOKEN" in str(raised.value)
    assert "lfx auth token" in str(raised.value)


def test_failing_lfx_cli_reported(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    write_stub_lfx(tmp_path, f"echo {TOKEN}; echo 'refresh failed for {TOKEN}' >&2; exit 4")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(lfx.LfxConfigError) as raised:
        lfx.resolve_token()
    assert "exit status 4" in str(raised.value)
    assert "lfx auth login" in str(raised.value)
    assert "refresh failed" not in str(raised.value)
    assert TOKEN not in str(raised.value)


def test_expired_jwt_refused_before_any_request(monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock) -> None:
    token = make_jwt({"sub": "someone", "exp": int(time.time()) - 60})
    monkeypatch.setenv("LFX_TOKEN", token)
    with pytest.raises(lfx.LfxConfigError, match="expired") as raised:
        lfx.LfxClient(base_url=BASE)
    assert token not in str(raised.value)
    assert len(rsps.calls) == 0


def test_explicit_expired_jwt_refused_before_any_request(rsps: responses.RequestsMock) -> None:
    token = make_jwt({"exp": int(time.time()) - 60})
    with pytest.raises(lfx.LfxConfigError, match="expired") as raised:
        lfx.LfxClient(base_url=BASE, token=token)
    assert token not in str(raised.value)
    assert len(rsps.calls) == 0


def test_jwt_expiring_mid_lookup_stops_before_next_request(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock
) -> None:
    clock = {"now": 1_000_000.0}
    monkeypatch.setattr(lfx_config.time, "time", lambda: clock["now"])
    token = make_jwt({"exp": 1_000_100})

    def first_page(request: requests.PreparedRequest) -> tuple[int, dict[str, str], str]:
        clock["now"] = 1_000_200.0
        body = {"resources": [resource(OTHER_UID, f"{GROUP}-extra")], "page_token": "next"}
        return 200, {}, json.dumps(body)

    rsps.add_callback(responses.GET, f"{BASE}/query/resources", callback=first_page)
    with pytest.raises(lfx.LfxConfigError, match="expired") as raised:
        lfx.resolve_committee_uid(lfx.LfxClient(base_url=BASE, token=token), GROUP)
    assert token not in str(raised.value)
    assert len(rsps.calls) == 1


@pytest.mark.parametrize(
    "token",
    [f"{TOKEN}\nX-Extra: {TOKEN}", f"{TOKEN}\r\nX: y", f"{TOKEN} more", f"{TOKEN}\x00", f"{TOKEN}\u00e9"],
    ids=["embedded-newline", "embedded-crlf", "space", "nul", "non-ascii"],
)
def test_unsendable_token_refused_before_any_request(rsps: responses.RequestsMock, token: str) -> None:
    with pytest.raises(lfx.LfxConfigError, match="cannot be sent") as raised:
        lfx.LfxClient(base_url=BASE, token=token)
    assert TOKEN not in str(raised.value)
    assert len(rsps.calls) == 0


def test_explicit_empty_token_refused_before_any_request(rsps: responses.RequestsMock) -> None:
    with pytest.raises(lfx.LfxConfigError, match="no LFX token"):
        lfx.LfxClient(base_url=BASE, token="")
    assert len(rsps.calls) == 0


def test_unsendable_token_refused_from_every_source(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, tmp_path: Path
) -> None:
    monkeypatch.setenv("LFX_TOKEN", f"{TOKEN}\nX-Extra: {TOKEN}")
    with pytest.raises(lfx.LfxConfigError, match="cannot be sent") as raised:
        lfx.LfxClient(base_url=BASE)
    assert TOKEN not in str(raised.value)
    monkeypatch.delenv("LFX_TOKEN")
    write_stub_lfx(tmp_path, f"printf '%s\\n%s\\n' '{TOKEN}' 'X-Extra: {TOKEN}'")
    monkeypatch.setenv("PATH", str(tmp_path))
    with pytest.raises(lfx.LfxConfigError, match="cannot be sent") as raised:
        lfx.LfxClient(base_url=BASE)
    assert TOKEN not in str(raised.value)
    assert len(rsps.calls) == 0


@pytest.mark.parametrize(
    "token",
    [
        TOKEN,
        make_jwt({"exp": int(time.time()) + 3600}),
        make_jwt({"exp": "yesterday"}),
        make_jwt(["not", "an", "object"]),
        "a.b.c",
    ],
    ids=["opaque", "valid-jwt", "non-numeric-exp", "non-object-payload", "undecodable"],
)
def test_other_tokens_sent_as_they_are(
    monkeypatch: pytest.MonkeyPatch, rsps: responses.RequestsMock, token: str
) -> None:
    monkeypatch.setenv("LFX_TOKEN", token)
    rsps.get(f"{BASE}/committees/{UID}", json={"uid": UID})
    lfx.LfxClient(base_url=BASE).get_json(f"/committees/{UID}")
    assert rsps.calls[0].request.headers["Authorization"] == f"Bearer {token}"


# Requests


def test_request_headers_and_version(rsps: responses.RequestsMock) -> None:
    rsps.get(
        f"{BASE}/committees/{UID}",
        json={"uid": UID},
        match=[
            matchers.query_param_matcher({"v": "1"}),
            matchers.header_matcher({"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}),
            matchers.request_kwargs_matcher({"timeout": lfx.DEFAULT_TIMEOUT}),
        ],
    )
    assert client().get_json(f"/committees/{UID}") == {"uid": UID}


def test_redirect_refused(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=302, headers={"Location": "https://elsewhere.example.org/"})
    with pytest.raises(lfx.LfxAPIError, match="redirect") as raised:
        client().get_json(f"/committees/{UID}")
    assert raised.value.status == 302
    assert len(rsps.calls) == 1


def test_malformed_redirect_location_refused(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=302, headers={"Location": "https://[broken"})
    with pytest.raises(lfx.LfxAPIError, match="redirect") as raised:
        client().get_json(f"/committees/{UID}")
    assert raised.value.status == 302
    assert len(rsps.calls) == 1


def test_error_body_message_shown(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=500, json={"message": "backend unavailable"})
    with pytest.raises(lfx.LfxAPIError) as raised:
        client().get_json(f"/committees/{UID}")
    assert raised.value.status == 500
    assert "HTTP 500" in str(raised.value)
    assert "backend unavailable" in str(raised.value)


def test_token_redacted_from_diagnostics(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/a", status=401, json={"message": f"bad bearer {TOKEN}"})
    rsps.get(f"{BASE}/committees/b", status=302, headers={"Location": f"https://x.example.org/{TOKEN}"})
    rsps.get(f"{BASE}/committees/c", body=requests.ConnectionError(f"reset while sending {TOKEN}"))
    for path in ("a", "b", "c"):
        with pytest.raises(lfx.LfxAPIError) as raised:
            client().get_json(f"/committees/{path}")
        assert TOKEN not in str(raised.value)
        assert "<redacted>" in str(raised.value)


def test_redirect_target_secrets_not_shown(rsps: responses.RequestsMock) -> None:
    location = "https://alice:hunter2@x.example.org/next?key=k3y#fr4g"
    rsps.get(f"{BASE}/committees/{UID}", status=302, headers={"Location": location})
    with pytest.raises(lfx.LfxAPIError) as raised:
        client().get_json(f"/committees/{UID}")
    for secret in ("hunter2", "k3y", "fr4g"):
        assert secret not in str(raised.value)
    assert "https://x.example.org/next" in str(raised.value)


def test_error_body_not_json(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=502, body="<html>bad gateway</html>")
    with pytest.raises(lfx.LfxAPIError, match=r"HTTP 502$"):
        client().get_json(f"/committees/{UID}")


# Lookup


def test_uuid_taken_as_uid_without_request(rsps: responses.RequestsMock) -> None:
    assert lfx.resolve_committee_uid(client(), UID.upper()) == UID
    assert len(rsps.calls) == 0


def _query(rsps: responses.RequestsMock, body: dict[str, object], page_token: str | None = None) -> None:
    params = {"v": "1", "type": "committee", "tags": f"sso_group_name:{GROUP}"}
    if page_token:
        params["page_token"] = page_token
    rsps.get(f"{BASE}/query/resources", json=body, match=[matchers.query_param_matcher(params)])


def test_lookup_spans_two_pages(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"resources": [resource(OTHER_UID, f"{GROUP}-extra")], "page_token": "next"})
    _query(rsps, {"resources": [resource(UID, GROUP)], "page_token": ""}, page_token="next")
    assert lfx.resolve_committee_uid(client(), GROUP) == UID
    assert len(rsps.calls) == 2


def test_page_token_not_logged_by_either_layer(rsps: responses.RequestsMock, caplog: pytest.LogCaptureFixture) -> None:
    _query(rsps, {"resources": [], "page_token": TOKEN})
    _query(rsps, {"resources": [resource(UID, GROUP)]}, page_token=TOKEN)
    with caplog.at_level(logging.DEBUG):
        assert lfx.resolve_committee_uid(client(), GROUP) == UID
        # responses replaces urllib3, so emit the record its pool logs per request.
        logging.getLogger("urllib3.connectionpool").debug(
            '%s://%s:%s "%s %s %s" %s %s',
            "https",
            "lfx.example.org",
            443,
            "GET",
            f"/query/resources?v=1&page_token={TOKEN}&type=committee",
            "HTTP/1.1",
            200,
            2,
        )
    assert len(rsps.calls) == 2
    assert "page_token" in caplog.text
    assert "page_token=<redacted>&type=<redacted>" in caplog.text
    assert TOKEN not in caplog.text


def test_idna_host_and_encoded_token_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    token = "opaque/token+value="  # noqa: S105
    lfx.LfxClient(base_url="https://b\u00fccher.example.org", token=token)
    with caplog.at_level(logging.DEBUG):
        # requests sends the host IDNA-encoded and the query URL-encoded.
        logging.getLogger("urllib3.connectionpool").debug(
            '%s://%s:%s "%s %s %s" %s %s',
            "https",
            "xn--bcher-kva.example.org",
            443,
            "GET",
            "/query/resources?v=1&page_token=opaque%2Ftoken%2Bvalue%3D&type=committee",
            "HTTP/1.1",
            200,
            2,
        )
        logging.getLogger("urllib3.connectionpool").debug("echo %s %s", "elsewhere", "opaque%2Ftoken%2Bvalue%3D")
    assert "page_token=<redacted>&type=<redacted>" in caplog.text
    assert "echo elsewhere <redacted>" in caplog.text
    assert "opaque%2Ftoken%2Bvalue%3D" not in caplog.text
    assert token not in caplog.text


def test_token_registered_while_filtering_a_record(caplog: pytest.LogCaptureFixture) -> None:
    client()
    lfx.LfxClient(base_url=BASE, token="first-other-token")  # noqa: S106
    late = "late-registered-token"  # noqa: S105

    class _RegistersOnFind(str):
        """A message that builds a client mid-filter, as another thread might."""

        __slots__ = ()

        def find(self, sub: str, start: SupportsIndex | None = None, end: SupportsIndex | None = None) -> int:
            lfx.LfxClient(base_url=BASE, token=late)
            return str(self).find(sub, start, end)

    with caplog.at_level(logging.DEBUG):
        logging.getLogger("urllib3.connectionpool").debug(_RegistersOnFind(f"echo {TOKEN}"))
        logging.getLogger("urllib3.connectionpool").debug("echo %s", late)
    assert TOKEN not in caplog.text
    assert late not in caplog.text
    assert caplog.text.count("echo <redacted>") == 2


@pytest.fixture
def isolated_log_filter(monkeypatch: pytest.MonkeyPatch) -> None:
    """Restore the process-wide log filter's registrations after the test."""
    log_filter = lfx_client._TRANSPORT_LOG_FILTER  # noqa: SLF001
    monkeypatch.setattr(log_filter, "hosts", log_filter.hosts)
    monkeypatch.setattr(log_filter, "tokens", log_filter.tokens)


@pytest.mark.usefixtures("isolated_log_filter")
def test_overlapping_tokens_fully_redacted(caplog: pytest.LogCaptureFixture) -> None:
    shorter, longer = "opaque-token-value", "opaque-token-value-extension-2"
    lfx.LfxClient(base_url=BASE, token=shorter)
    lfx.LfxClient(base_url=BASE, token=longer)
    lfx.LfxClient(base_url=BASE, token="value-extension-2-tail")  # noqa: S106
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("urllib3.connectionpool").debug("echo %s", longer)
        logging.getLogger("urllib3.connectionpool").debug("echo %s", "opaque-token-value-extension-2-tail")
    assert caplog.messages[-2:] == ["echo <redacted>", "echo <redacted>"]


@pytest.mark.usefixtures("isolated_log_filter")
def test_token_matching_format_placeholder_keeps_message(caplog: pytest.LogCaptureFixture) -> None:
    lfx.LfxClient(base_url=BASE, token="s")
    with caplog.at_level(logging.DEBUG):
        logging.getLogger("urllib3.connectionpool").debug("%s://%s:%s", "https", "other.example.org", 443)
    assert caplog.messages[-1] == "http<redacted>://other.example.org:443"


def test_lookup_no_match(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"resources": [], "page_token": None})
    with pytest.raises(lfx.LfxNotFoundError, match="cannot see"):
        lfx.resolve_committee_uid(client(), GROUP)


def test_lookup_ignores_different_sso_group_name(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"resources": [resource(UID, GROUP.upper()), resource(OTHER_UID, f"{GROUP}-x")]})
    with pytest.raises(lfx.LfxNotFoundError):
        lfx.resolve_committee_uid(client(), GROUP)


def test_lookup_two_matches_lists_uids(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"resources": [resource(UID, GROUP), resource(OTHER_UID, GROUP)]})
    with pytest.raises(lfx.LfxAmbiguityError) as raised:
        lfx.resolve_committee_uid(client(), GROUP)
    assert UID in str(raised.value)
    assert OTHER_UID in str(raised.value)


@pytest.mark.parametrize("token", [TOKEN, "s3cr3t\\token"])
def test_lookup_errors_redact_token(rsps: responses.RequestsMock, token: str) -> None:
    rsps.get(f"{BASE}/query/resources", json={"resources": [], "page_token": None})
    rsps.get(
        f"{BASE}/query/resources",
        json={"resources": [resource(f"{UID}-{token}", token), resource(OTHER_UID, token)], "page_token": None},
    )
    token_client = lfx.LfxClient(base_url=BASE, token=token)
    for error in (lfx.LfxNotFoundError, lfx.LfxAmbiguityError):
        with pytest.raises(error) as raised:
            lfx.resolve_committee_uid(token_client, token)
        assert token not in str(raised.value)
        assert "<redacted>" in str(raised.value)


ENCODED_TOKEN = "opaque/token+value="  # noqa: S105


def _token_bearing_lookup(rsps: responses.RequestsMock, status: int, **body: object) -> str:
    """Answer a name lookup with a UID carrying the token, and its committee read."""
    uid = f"x-{ENCODED_TOKEN}"
    rsps.get(f"{BASE}/query/resources", json={"resources": [resource(uid, GROUP)], "page_token": None})
    rsps.get(f"{BASE}/committees/{quote(uid, safe='')}", status=status, **body)
    return uid


@pytest.mark.parametrize(
    ("status", "body"),
    [
        (500, {"json": {"message": "backend unavailable"}}),
        (200, {"body": "not json"}),
        (200, {"json": []}),
    ],
    ids=["http-error", "not-json", "not-object"],
)
def test_token_bearing_uid_redacted_in_committee_read(
    rsps: responses.RequestsMock, caplog: pytest.LogCaptureFixture, status: int, body: dict[str, object]
) -> None:
    _token_bearing_lookup(rsps, status, **body)
    token_client = lfx.LfxClient(base_url=BASE, token=ENCODED_TOKEN)
    with caplog.at_level(logging.DEBUG), pytest.raises(lfx.LfxAPIError) as raised:
        lfx.show_committee(token_client, GROUP)
    shown = f"{raised.value}\n{caplog.text}"
    for form in (ENCODED_TOKEN, quote(ENCODED_TOKEN, safe=""), quote_plus(ENCODED_TOKEN)):
        assert form not in shown
    assert "GET /committees/x-<redacted>" in str(raised.value)
    assert "LFX GET /committees/x-<redacted>" in caplog.text


def test_redact_masks_overlapping_token_forms() -> None:
    token_client = lfx.LfxClient(base_url=BASE, token="a/a")  # noqa: S106
    # The encoded form "a%2Fa" and the raw token share the middle "a".
    assert token_client.redact("x a%2Fa/a y") == "x <redacted> y"


def test_redact_data_keeps_structure() -> None:
    body = {"name": f"x {TOKEN} y", TOKEN: [TOKEN, 3, None, {"k": True}]}
    assert client().redact_data(body) == {"name": "x <redacted> y", "<redacted>": ["<redacted>", 3, None, {"k": True}]}


@pytest.mark.parametrize(
    ("token", "value", "expected"),
    [
        ("12345", 12345, "<redacted>"),
        ("123", 12345, "<redacted>45"),
        ("2.5", 2.5, "<redacted>"),
        ("true", True, "<redacted>"),
        ("false", False, "<redacted>"),
        ("null", None, "<redacted>"),
    ],
)
def test_redact_data_redacts_matching_scalars(token: str, value: object, expected: str) -> None:
    token_client = lfx.LfxClient(base_url=BASE, token=token)
    body = {"total_members": value, "public": False, "count": 9, "other": None}
    redacted = token_client.redact_data(body)
    assert redacted["total_members"] == expected
    assert token not in json.dumps(redacted)
    # Scalars the token does not match keep their JSON type.
    for key, kept in (("public", False), ("count", 9), ("other", None)):
        if token not in json.dumps(kept):
            assert redacted[key] is kept


def test_lookup_repeated_page_token_stops(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"resources": [], "page_token": "same"})
    _query(rsps, {"resources": [], "page_token": "same"}, page_token="same")
    with pytest.raises(lfx.LfxAPIError, match="repeated"):
        lfx.resolve_committee_uid(client(), GROUP)


def test_lookup_first_page_without_resources_is_error(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"page_token": None})
    with pytest.raises(lfx.LfxAPIError, match="'resources' list") as raised:
        lfx.resolve_committee_uid(client(), GROUP)
    assert not isinstance(raised.value, lfx.LfxNotFoundError)


def test_lookup_later_page_without_resources_is_error(rsps: responses.RequestsMock) -> None:
    _query(rsps, {"resources": [resource(UID, GROUP)], "page_token": "next"})
    _query(rsps, {"page_token": None}, page_token="next")
    with pytest.raises(lfx.LfxAPIError, match="'resources' list"):
        lfx.resolve_committee_uid(client(), GROUP)


def test_lookup_404_is_not_found(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/query/resources", status=404, json={"message": "no route"})
    with pytest.raises(lfx.LfxNotFoundError, match="no route.*cannot see"):
        lfx.resolve_committee_uid(client(), GROUP)


def test_get_committee_404_is_not_found(rsps: responses.RequestsMock) -> None:
    rsps.get(f"{BASE}/committees/{UID}", status=404, json={"message": "no such committee"})
    with pytest.raises(lfx.LfxNotFoundError, match="no such committee"):
        lfx.get_committee(client(), UID)


def test_token_never_in_repr() -> None:
    assert TOKEN not in repr(client())
    assert TOKEN not in repr(client()._session.auth)  # noqa: SLF001


@pytest.mark.parametrize(
    ("token", "path"),
    [
        (TOKEN, TOKEN),
        ("opaque/token+value=", quote("opaque/token+value=", safe="")),
        ("opaque\\token", "opaque\\token"),
    ],
    ids=["raw", "url-encoded", "backslash"],
)
def test_token_in_base_url_never_in_repr(token: str, path: str) -> None:
    shown = repr(lfx.LfxClient(base_url=f"{BASE}/{path}", token=token))
    assert path not in shown
    assert repr(path)[1:-1] not in shown
    assert lfx_client.REDACTED in shown
