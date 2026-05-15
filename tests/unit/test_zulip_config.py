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

from pathlib import Path
from unittest import mock

import pytest

from lftools_uv.api.endpoints.zulip import (
    ZulipConfigError,
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
