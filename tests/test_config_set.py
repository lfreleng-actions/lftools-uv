# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``config set`` on a section or file that does not exist yet.

``config set`` must add a missing section, so that a new server can be
configured, and create ``lftools.ini`` when there is none. The file holds
credentials, so one ``config set`` creates is readable by its owner only;
an existing file keeps its permissions.

Every test works on a configuration file under ``tmp_path``, never the
user's own.
"""

import os
import stat
from collections.abc import Iterator
from pathlib import Path

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv import config
from lftools_uv.cli import cli
from lftools_uv.typer_apps.root import app

XFAIL = pytest.mark.xfail(strict=True, reason="#1007: config set cannot add a section or create the file")


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, args, obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


@pytest.fixture
def ini_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point lftools at ``tmp_path / "lftools.ini"``, which does not exist yet."""
    path = tmp_path / "lftools.ini"
    monkeypatch.setattr(config, "LFTOOLS_CONFIG_FILE", str(path))
    return path


@pytest.fixture
def permissive_umask() -> Iterator[None]:
    """Run with a umask that would leave a new file readable by everyone."""
    previous = os.umask(0o022)
    try:
        yield
    finally:
        os.umask(previous)


def _mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


@XFAIL
def test_set_setting_adds_missing_section(ini_path: Path) -> None:
    ini_path.write_text("[nexus]\nusername = alice\n")

    config.set_setting("gerrit.example.org", "password", "p%ss")

    assert config.get_setting("gerrit.example.org", "password") == "p%ss"
    assert config.get_setting("nexus", "username") == "alice"


@XFAIL
@pytest.mark.usefixtures("permissive_umask")
def test_set_setting_creates_private_file(ini_path: Path) -> None:
    config.set_setting("gerrit.example.org", "password", "s3cret")

    assert config.get_setting("gerrit.example.org", "password") == "s3cret"
    assert _mode(ini_path) == 0o600


def test_set_setting_default_section(ini_path: Path) -> None:
    """The DEFAULT section is written to the defaults, as ConfigParser does, not added."""
    ini_path.write_text("[nexus]\nusername = alice\n")

    config.set_setting("DEFAULT", "timeout", "30")

    assert config.get_setting("nexus", "timeout") == "30"
    assert "[DEFAULT]" in ini_path.read_text()


@pytest.mark.parametrize("mode", [0o644, 0o600])
@pytest.mark.usefixtures("permissive_umask")
def test_set_setting_keeps_existing_file_mode(ini_path: Path, mode: int) -> None:
    ini_path.write_text("[nexus]\nusername = alice\n")
    ini_path.chmod(mode)

    config.set_setting("nexus", "password", "s3cret")

    assert config.get_setting("nexus", "password") == "s3cret"
    assert _mode(ini_path) == mode


@XFAIL
@FRONT_ENDS
def test_config_set_new_section(run, ini_path: Path) -> None:  # type: ignore[no-untyped-def]
    ini_path.write_text("[nexus]\nusername = alice\n")

    result = run(["config", "set", "gerrit.example.org", "password", "s3cret"])

    assert result.exit_code == 0, result.output
    assert run(["config", "get", "gerrit.example.org", "password"]).output.strip() == "s3cret"
