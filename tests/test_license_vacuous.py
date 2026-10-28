# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for licence checks that used to pass having checked nothing.

A licence check must fail on a directory that does not exist, on a
directory where no file matches the regex, and against a reference header
with no ``#`` comment lines, whose empty text every file "contains". The
Typer ``license check`` must also accept ``-r/--regex`` for a directory.

Every file lives under ``tmp_path``; ``tests/fixtures/license`` is untouched.
"""

from collections.abc import Callable
from pathlib import Path

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli import cli
from lftools_uv.license import check_license_directory
from lftools_uv.typer_apps.license import license_app

HEADER = "# Example licence header used by these tests.\n# Every checked file must carry it.\n"
PLAIN_REFERENCE = "Example licence terms written without any comment marker.\n"

Runner = Callable[..., ClickResult | TyperResult]


def _click_check(reference: Path, source: Path) -> ClickResult:
    return ClickRunner().invoke(cli, ["license", "check", str(source), "-l", str(reference)], obj={})


def _click_check_dir(reference: Path, directory: Path, *extra: str) -> ClickResult:
    args = ["license", "check-dir", str(directory), "-l", str(reference), *extra]
    return ClickRunner().invoke(cli, args, obj={})


def _typer_check(reference: Path, source: Path, *extra: str) -> TyperResult:
    return TyperRunner().invoke(license_app, ["check", str(source), "-l", str(reference), *extra])


DIR_FRONT_ENDS = pytest.mark.parametrize("run", [_click_check_dir, _typer_check], ids=["click", "typer"])
FILE_FRONT_ENDS = pytest.mark.parametrize("run", [_click_check, _typer_check], ids=["click", "typer"])


@pytest.fixture
def reference(tmp_path: Path) -> Path:
    """Write the reference licence header."""
    path = tmp_path / "license-header.txt"
    path.write_text(HEADER)
    return path


@pytest.fixture
def plain_reference(tmp_path: Path) -> Path:
    """Write a reference header with no ``#`` comment lines."""
    path = tmp_path / "plain-header.txt"
    path.write_text(PLAIN_REFERENCE)
    return path


@pytest.fixture
def source_dir(tmp_path: Path) -> Path:
    """Create an empty directory to scan."""
    path = tmp_path / "src"
    path.mkdir()
    return path


def test_click_check_dir_missing_directory_fails(reference: Path, tmp_path: Path) -> None:
    """Click ``check-dir`` exits 1 on a directory that does not exist."""
    result = _click_check_dir(reference, tmp_path / "missing")
    assert result.exit_code == 1


def test_check_license_directory_missing_directory_fails(reference: Path, tmp_path: Path) -> None:
    """``check_license_directory`` exits 1 on a directory that does not exist."""
    with pytest.raises(SystemExit) as excinfo:
        check_license_directory(str(reference), str(tmp_path / "missing"))
    assert excinfo.value.code == 1


def test_typer_check_missing_path_fails(reference: Path, tmp_path: Path) -> None:
    """Typer ``check`` already exits 1 on a path that does not exist."""
    result = _typer_check(reference, tmp_path / "missing")
    assert result.exit_code == 1


@DIR_FRONT_ENDS
def test_empty_directory_fails(run: Runner, reference: Path, source_dir: Path) -> None:
    """A directory with no files at all fails the scan."""
    result = run(reference, source_dir)
    assert result.exit_code == 1


@DIR_FRONT_ENDS
def test_directory_without_matching_files_fails(run: Runner, reference: Path, source_dir: Path) -> None:
    """A directory whose files do not match the regex fails the scan."""
    (source_dir / "build.sh").write_text(HEADER + "echo build\n")
    result = run(reference, source_dir)
    assert result.exit_code == 1


@FILE_FRONT_ENDS
def test_plain_reference_fails_single_file(run: Runner, plain_reference: Path, source_dir: Path) -> None:
    """A reference header without ``#`` lines fails a single-file check."""
    code = source_dir / "module.py"
    code.write_text('print("no header")\n')
    result = run(plain_reference, code)
    assert result.exit_code == 1


@DIR_FRONT_ENDS
def test_plain_reference_fails_directory(run: Runner, plain_reference: Path, source_dir: Path) -> None:
    """A reference header without ``#`` lines fails a directory scan."""
    (source_dir / "module.py").write_text('print("no header")\n')
    result = run(plain_reference, source_dir)
    assert result.exit_code == 1


def test_typer_check_accepts_regex(reference: Path, source_dir: Path) -> None:
    """Typer ``check DIR -r`` scans the files the regex names."""
    (source_dir / "build.sh").write_text(HEADER + "echo build\n")
    result = _typer_check(reference, source_dir, "-r", r".+\.sh$")
    assert result.exit_code == 0, result.output


@DIR_FRONT_ENDS
def test_directory_with_headers_passes(run: Runner, reference: Path, source_dir: Path) -> None:
    """A directory whose matching files all carry the header passes."""
    (source_dir / "one.py").write_text(HEADER + "VALUE = 1\n")
    nested = source_dir / "pkg"
    nested.mkdir()
    (nested / "two.py").write_text(HEADER + "VALUE = 2\n")
    result = run(reference, source_dir)
    assert result.exit_code == 0, result.output
