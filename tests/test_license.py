# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Test license command."""

import logging
import os
import shutil

import pytest
from typer.testing import CliRunner

from lftools_uv import cli
from lftools_uv.typer_apps.license import license_app

FIXTURE_DIR = os.path.join(
    os.path.dirname(os.path.realpath(__file__)),
    "fixtures",
)


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "license"),
)
def test_check_license(cli_runner, datafiles):
    """Test check_license() command."""
    os.chdir(str(datafiles))

    # Check that license checker passes when file has license.
    result = cli_runner.invoke(cli.cli, ["license", "check", "license.py"], obj={})
    assert result.exit_code == 0

    # Check that license checker fails when file is missing license.
    result = cli_runner.invoke(cli.cli, ["license", "check", "no_license1.py"], obj={})
    assert result.exit_code == 1


@pytest.mark.datafiles(
    os.path.join(FIXTURE_DIR, "license"),
)
def test_check_license_directory(cli_runner, datafiles):
    """Test check_license_directory() command."""
    os.chdir(str(datafiles))

    # Check that check-dir fails due to directory containing files
    # with no license.
    result = cli_runner.invoke(cli.cli, ["license", "check-dir", "."], obj={})
    assert result.exit_code == 1

    # Check that check-dir passes when directory contains files with licenses
    os.remove("no_license1.py")
    os.remove("no_license2.py")
    result = cli_runner.invoke(cli.cli, ["license", "check-dir", "."], obj={})
    assert result.exit_code == 0


def _typer_check(tmp_path, name, caplog):
    """Run the Typer ``license check`` on one file copied into tmp_path."""
    for fixture in ("license-header.txt", "license.py", "no_license1.py"):
        shutil.copy(os.path.join(FIXTURE_DIR, "license", fixture), tmp_path)
    (tmp_path / "other_license.py").write_text(
        '# This file carries a different licence header.\n"""Test code file with a different license header."""\n'
    )
    caplog.set_level(logging.DEBUG)
    return CliRunner().invoke(
        license_app,
        ["check", str(tmp_path / name), "--license", str(tmp_path / "license-header.txt")],
    )


@pytest.mark.xfail(strict=True, reason="#856: Typer single-file check is inverted")
def test_typer_check_license_matching_header(tmp_path, caplog):
    """Typer ``license check`` passes a file whose header matches."""
    result = _typer_check(tmp_path, "license.py", caplog)
    assert result.exit_code == 0


@pytest.mark.xfail(strict=True, reason="#856: Typer single-file check is inverted")
@pytest.mark.parametrize("name", ["other_license.py", "no_license1.py"])
def test_typer_check_license_wrong_or_missing_header(tmp_path, caplog, name):
    """Typer ``license check`` fails cleanly on a wrong or missing header."""
    result = _typer_check(tmp_path, name, caplog)
    assert result.exit_code == 1
    assert "License check failed" not in caplog.text
