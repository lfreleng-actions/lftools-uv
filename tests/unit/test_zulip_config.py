# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Unit tests for Zulip configuration resolution (T015)."""

from __future__ import annotations

import configparser
from pathlib import Path
from unittest import mock

import pytest

from lftools_uv.api.endpoints.zulip import (
    ZulipConfig,
    ZulipConfigError,
    get_client,
    resolve_config,
)

ZULIPRC_CONTENT = """\
[api]
email=bot@example.com
key=apikey1234
site=https://zulip.example.com
"""


@pytest.fixture()
def zuliprc_file(tmp_path: Path) -> Path:
    """Return a path to a valid zuliprc file."""
    path = tmp_path / "zuliprc"
    _ = path.write_text(ZULIPRC_CONTENT, encoding="utf-8")
    return path


def test_resolve_config_uses_explicit_zuliprc(zuliprc_file: Path, tmp_path: Path) -> None:
    """The --zuliprc argument wins over every other source."""
    cwd = tmp_path / "elsewhere"
    cwd.mkdir()
    config = resolve_config(zuliprc=zuliprc_file, cwd=cwd, home=cwd)
    assert config.config_path == zuliprc_file
    assert config.source == str(zuliprc_file)


def test_resolve_config_falls_back_to_cwd_zuliprc(tmp_path: Path) -> None:
    """A ./zuliprc file in the cwd is the second precedence level."""
    cwd = tmp_path / "work"
    cwd.mkdir()
    rc = cwd / "zuliprc"
    _ = rc.write_text(ZULIPRC_CONTENT, encoding="utf-8")
    config = resolve_config(zuliprc=None, cwd=cwd, home=tmp_path / "home")
    assert config.config_path == rc


def test_resolve_config_uses_lftools_ini(tmp_path: Path) -> None:
    """The ``[zulip]`` section in lftools.ini is the third level."""
    cwd = tmp_path / "work"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    with (
        mock.patch(
            "lftools_uv.api.endpoints.zulip.lf_config.has_section",
            return_value=True,
        ),
        mock.patch(
            "lftools_uv.api.endpoints.zulip.lf_config.get_setting",
            side_effect=[
                "bot@example.com",
                "apikey1234",
                "https://zulip.example.com",
            ],
        ),
    ):
        config = resolve_config(zuliprc=None, cwd=cwd, home=home)
    assert config.config_path is None
    assert config.email == "bot@example.com"
    assert config.api_key == "apikey1234"
    assert config.site == "https://zulip.example.com"
    assert config.source == "lftools.ini[zulip]"


def test_resolve_config_falls_back_to_home_zuliprc(tmp_path: Path) -> None:
    """``~/.zuliprc`` is the final fallback in the precedence chain."""
    cwd = tmp_path / "work"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    rc = home / ".zuliprc"
    _ = rc.write_text(ZULIPRC_CONTENT, encoding="utf-8")
    with mock.patch(
        "lftools_uv.api.endpoints.zulip.lf_config.has_section",
        return_value=False,
    ):
        config = resolve_config(zuliprc=None, cwd=cwd, home=home)
    assert config.config_path == rc


def test_resolve_config_missing_all_sources(tmp_path: Path) -> None:
    """A clear error is raised when no source produces a configuration."""
    cwd = tmp_path / "work"
    cwd.mkdir()
    home = tmp_path / "home"
    home.mkdir()
    with mock.patch(
        "lftools_uv.api.endpoints.zulip.lf_config.has_section",
        return_value=False,
    ):
        with pytest.raises(ZulipConfigError, match="No Zulip configuration found"):
            _ = resolve_config(zuliprc=None, cwd=cwd, home=home)


def test_resolve_config_explicit_path_missing(tmp_path: Path) -> None:
    """--zuliprc that points at a non-existent path fails clearly."""
    missing = tmp_path / "no-such-file"
    with pytest.raises(ZulipConfigError, match="does not exist"):
        _ = resolve_config(zuliprc=missing)


def test_resolve_config_malformed_file(tmp_path: Path) -> None:
    """A zuliprc without the [api] section is rejected with a clear error."""
    rc = tmp_path / "zuliprc"
    _ = rc.write_text("[other]\nfoo=bar\n", encoding="utf-8")
    with pytest.raises(ZulipConfigError, match=r"missing required \[api\] section"):
        _ = resolve_config(zuliprc=rc)


def test_resolve_config_interpolation_error(tmp_path: Path) -> None:
    """Interpolation syntax errors in zuliprc options do not leak values (#871)."""
    rc = tmp_path / "zuliprc"
    _ = rc.write_text(
        "[api]\nemail=bot@example.com\nkey=secret%value\nsite=https://zulip.example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ZulipConfigError, match=r"Malformed Zulip config file") as exc_info:
        _ = resolve_config(zuliprc=rc)
    assert "secret%value" not in str(exc_info.value)


def test_resolve_config_missing_key_option(tmp_path: Path) -> None:
    """A zuliprc without a key is rejected here, not inside zulip.Client (#871)."""
    rc = tmp_path / "zuliprc"
    _ = rc.write_text(
        "[api]\nemail=bot@example.com\nsite=https://zulip.example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ZulipConfigError, match=r"missing required key option"):
        _ = resolve_config(zuliprc=rc)


def test_resolve_config_missing_site_option(tmp_path: Path) -> None:
    """A zuliprc without a site is rejected here, not as MissingURLError (#871)."""
    rc = tmp_path / "zuliprc"
    _ = rc.write_text(
        "[api]\nemail=bot@example.com\nkey=apikey1234\n",
        encoding="utf-8",
    )
    with pytest.raises(ZulipConfigError, match=r"missing required site option"):
        _ = resolve_config(zuliprc=rc)


def test_resolve_config_missing_email_option(tmp_path: Path) -> None:
    """A zuliprc without an email is rejected here, not inside zulip.Client (#871)."""
    rc = tmp_path / "zuliprc"
    _ = rc.write_text(
        "[api]\nkey=apikey1234\nsite=https://zulip.example.com\n",
        encoding="utf-8",
    )
    with pytest.raises(ZulipConfigError, match=r"missing required email option"):
        _ = resolve_config(zuliprc=rc)


def _fake_zulip_module(client: mock.Mock, error_cls: type[BaseException] | None = None) -> mock.Mock:
    """A stand-in for the ``zulip`` package: its error surface, our client."""
    module = mock.Mock()
    module.ZulipError = type("ZulipError", (Exception,), {}) if error_cls is None else error_cls
    module.Client = client
    return module


def test_get_client_wraps_no_option_error(zuliprc_file: Path) -> None:
    """zulip's configparser.NoOptionError becomes a ZulipConfigError (#871)."""
    client = mock.Mock(side_effect=configparser.NoOptionError("option 'key'", "section: 'api'"))
    with mock.patch(
        "lftools_uv.api.endpoints.zulip._require_zulip",
        return_value=_fake_zulip_module(client),
    ):
        with pytest.raises(ZulipConfigError, match="Cannot construct Zulip client from") as exc_info:
            _ = get_client(zuliprc=zuliprc_file)
    assert str(zuliprc_file) in str(exc_info.value)


def test_get_client_wraps_zulip_error(zuliprc_file: Path) -> None:
    """zulip.MissingURLError becomes a ZulipConfigError with the source (#871)."""
    base_error = type("ZulipError", (Exception,), {})
    missing_url = type("MissingURLError", (base_error,), {})
    client = mock.Mock(side_effect=missing_url("Missing Zulip server URL"))
    module = _fake_zulip_module(client, error_cls=base_error)
    module.MissingURLError = missing_url
    with mock.patch("lftools_uv.api.endpoints.zulip._require_zulip", return_value=module):
        with pytest.raises(ZulipConfigError, match="Missing Zulip server URL"):
            _ = get_client(zuliprc=zuliprc_file)


def test_get_client_wraps_zulip_error_for_credentials() -> None:
    """The credentials path gets the same wrapping as the config-file path."""
    base_error = type("ZulipError", (Exception,), {})
    client = mock.Mock(side_effect=base_error("bad key"))
    module = _fake_zulip_module(client, error_cls=base_error)
    config = ZulipConfig(
        email="bot@example.com",
        api_key="apikey1234",
        site="https://zulip.example.com",
        source="lftools.ini[zulip]",
    )
    with mock.patch("lftools_uv.api.endpoints.zulip._require_zulip", return_value=module):
        with pytest.raises(ZulipConfigError, match=r"lftools\.ini\[zulip\]") as exc_info:
            _ = get_client(config=config)
    assert "bad key" in str(exc_info.value)


def test_get_client_returns_the_client_for_a_complete_file(zuliprc_file: Path) -> None:
    """A complete zuliprc reaches zulip.Client unchanged."""
    sentinel = object()
    client = mock.Mock(return_value=sentinel)
    with mock.patch(
        "lftools_uv.api.endpoints.zulip._require_zulip",
        return_value=_fake_zulip_module(client),
    ):
        assert get_client(zuliprc=zuliprc_file) is sentinel
    client.assert_called_once_with(config_file=str(zuliprc_file))
