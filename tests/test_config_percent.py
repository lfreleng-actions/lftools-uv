# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for a literal ``%`` in ``lftools.ini``.

A value holding a stray ``%`` must read back as written rather than
raise ``InterpolationSyntaxError``, and a ``%`` under ``[global]`` must
not break every command. ``config set`` must store a ``%`` so that it
reads back unchanged.

Every test reads a configuration file under ``tmp_path``, never the
user's own.
"""

from pathlib import Path

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv import config
from lftools_uv.cli import cli
from lftools_uv.typer_apps.root import app

PASSWORD = "Xy7%k2!q"

INI = """\
[global]
username = alice
password = Xy7%k2!q

[gerrit.example.org]
password = p%ss
escaped = a%%b
"""


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(cli, args, obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(app, args)


FRONT_ENDS = pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])


@pytest.fixture
def ini_file(tmp_path, monkeypatch):
    """Point lftools at an ``lftools.ini`` holding literal ``%`` values."""
    path: Path = tmp_path / "lftools.ini"
    _ = path.write_text(INI)
    monkeypatch.setattr(config, "LFTOOLS_CONFIG_FILE", str(path))
    return path


@pytest.mark.xfail(strict=True, reason="#971: a literal % raises InterpolationSyntaxError")
def test_get_setting_reads_literal_percent(ini_file):
    """A value with a stray ``%`` reads back as written."""
    assert config.get_setting("global", "password") == PASSWORD
    assert config.get_setting("gerrit.example.org", "password") == "p%ss"


def test_get_setting_reads_escaped_percent(ini_file):
    """A ``%%`` escape still reads as a single ``%``."""
    assert config.get_setting("gerrit.example.org", "escaped") == "a%b"


@pytest.mark.xfail(strict=True, reason="#971: a % under [global] breaks every command")
@FRONT_ENDS
def test_passgen_with_percent_in_global(run, ini_file):
    """A ``%`` in the global password does not stop an unrelated command."""
    result = run(["utils", "passgen", "12"])

    assert result.exit_code == 0
    assert len(result.output.rstrip("\n")) == 12


@pytest.mark.xfail(strict=True, reason="#971: a literal % raises InterpolationSyntaxError")
@FRONT_ENDS
def test_config_get_option_with_percent(run, ini_file):
    """``config get`` prints a value holding a ``%`` as written."""
    result = run(["config", "get", "global", "password"])

    assert result.exit_code == 0
    assert result.output.strip() == PASSWORD


@pytest.mark.xfail(strict=True, reason="#971: a literal % raises InterpolationSyntaxError")
@FRONT_ENDS
def test_config_get_section_with_percent(run, ini_file):
    """``config get`` on a section prints every value as it reads back."""
    result = run(["config", "get", "gerrit.example.org"])

    assert result.exit_code == 0
    assert "password: p%ss" in result.output
    assert "escaped: a%b" in result.output


@pytest.mark.xfail(strict=True, reason="#971: config set cannot store a %")
@FRONT_ENDS
def test_config_set_stores_percent(run, ini_file):
    """``config set`` escapes a ``%`` so the value reads back unchanged."""
    result = run(["config", "set", "global", "token", "a%b"])

    assert result.exit_code == 0
    assert config.get_setting("global", "token") == "a%b"
    assert "token = a%%b" in ini_file.read_text()
