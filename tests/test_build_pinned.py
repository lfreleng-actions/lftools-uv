# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``scripts/build_pinned.py``.

The build packages the tree HEAD commits, so the ``pinned`` extra must come
from HEAD's uv.lock too, not from an uncommitted change to the working copy.
Its artefacts reach the output directory only when the wheel and the sdist
each declare one pinned requirement per pin. Arguments pass through to
``python -m build``, except a source directory naming the repository.
"""

import argparse
import importlib.util
import io
import os
import shutil
import subprocess
import tarfile
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "scripts" / "build_pinned.py"

# The sdist ships tests/ but neither the script nor uv.lock.
pytestmark = pytest.mark.skipif(
    not (SCRIPT.is_file() and (ROOT / "uv.lock").is_file()),
    reason="needs a repository checkout with scripts/build_pinned.py and uv.lock",
)

VERSION = "1.2.3"
PINS = ["idna==3.10", "requests==2.32.3"]


def _load_script() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_pinned", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture(autouse=True)
def _isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    for kind in ("AUTHOR", "COMMITTER"):
        monkeypatch.setenv(f"GIT_{kind}_NAME", "Scratch Author")
        monkeypatch.setenv(f"GIT_{kind}_EMAIL", "scratch@example.org")
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", os.devnull)
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")


def _metadata(pinned: list[str]) -> str:
    lines = ["Metadata-Version: 2.4", "Name: lftools-uv", f"Version: {VERSION}", "Requires-Dist: requests>=2"]
    lines += [f"Requires-Dist: {pin}; extra == 'pinned'" for pin in pinned]
    lines.append("Requires-Dist: python-ldap; extra == 'ldap'")
    return "\n".join(lines) + "\n"


def _write_wheel(outdir: Path, pinned: list[str]) -> Path:
    wheel = outdir / f"lftools_uv-{VERSION}-py3-none-any.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr(f"lftools_uv-{VERSION}.dist-info/METADATA", _metadata(pinned))
    return wheel


def _write_sdist(outdir: Path, pinned: list[str]) -> Path:
    sdist = outdir / f"lftools_uv-{VERSION}.tar.gz"
    data = _metadata(pinned).encode()
    info = tarfile.TarInfo(f"lftools_uv-{VERSION}/PKG-INFO")
    info.size = len(data)
    with tarfile.open(sdist, "w:gz") as tar:
        tar.addfile(info, io.BytesIO(data))
    return sdist


def test_check_accepts_artefacts_carrying_every_pin(tmp_path: Path) -> None:
    """A wheel and an sdist that each declare one pinned requirement per pin pass."""
    script = _load_script()
    _write_wheel(tmp_path, PINS)
    _write_sdist(tmp_path, PINS)

    script.check(tmp_path, VERSION, PINS)


@pytest.mark.parametrize(
    ("wheel_pins", "sdist_pins"),
    [(PINS[:1], PINS), (PINS, PINS[:1]), ([*PINS, "six==1.17.0"], PINS)],
    ids=["wheel-missing", "sdist-missing", "wheel-extra"],
)
def test_check_rejects_a_pin_count_mismatch(tmp_path: Path, wheel_pins: list[str], sdist_pins: list[str]) -> None:
    """Either artefact declaring a different number of pinned requirements fails."""
    script = _load_script()
    _write_wheel(tmp_path, wheel_pins)
    _write_sdist(tmp_path, sdist_pins)

    with pytest.raises(SystemExit, match="pinned requirements, uv.lock gives 2"):
        script.check(tmp_path, VERSION, PINS)


def test_check_rejects_a_directory_without_artefacts(tmp_path: Path) -> None:
    """A build that left no sdist or wheel for the version fails."""
    script = _load_script()

    with pytest.raises(SystemExit, match="no sdist or wheel"):
        script.check(tmp_path, VERSION, PINS)


def test_publish_copies_checked_artefacts(tmp_path: Path) -> None:
    """Artefacts that pass the check reach the output directory."""
    script = _load_script()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    wheel = _write_wheel(build_dir, PINS)
    sdist = _write_sdist(build_dir, PINS)
    outdir = tmp_path / "out"

    script.publish(build_dir, outdir, VERSION, PINS)

    assert sorted(path.name for path in outdir.iterdir()) == sorted([wheel.name, sdist.name])


def test_publish_leaves_the_output_directory_alone_on_failure(tmp_path: Path) -> None:
    """Artefacts that fail the check never reach the output directory."""
    script = _load_script()
    build_dir = tmp_path / "build"
    build_dir.mkdir()
    _write_wheel(build_dir, PINS[:1])
    _write_sdist(build_dir, PINS)
    outdir = tmp_path / "out"
    outdir.mkdir()
    earlier = outdir / f"lftools_uv-{VERSION}-py3-none-any.whl"
    earlier.write_bytes(b"earlier build")

    with pytest.raises(SystemExit):
        script.publish(build_dir, outdir, VERSION, PINS)

    assert list(outdir.iterdir()) == [earlier]
    assert earlier.read_bytes() == b"earlier build"


def _parser() -> argparse.ArgumentParser:
    """Return build's argument parser, or one shaped like it when build is absent."""
    try:
        parser: argparse.ArgumentParser = _load_script().build_parser()
    except ModuleNotFoundError:
        parser = argparse.ArgumentParser()
        parser.add_argument("srcdir", nargs="?", default=os.getcwd())
        parser.add_argument("--outdir", "-o")
        parser.add_argument("--sdist", "-s", action="store_true")
        parser.add_argument("--wheel", "-w", action="store_true")
    return parser


@pytest.mark.parametrize(
    ("args", "forward"),
    [
        ([], []),
        (["."], []),
        ([str(ROOT)], []),
        (["--wheel", "."], ["--wheel"]),
        ([".", "-w"], ["-w"]),
        (["-o", ".", "."], ["-o", "."]),
        ([".", "-o", "."], ["-o", "."]),
        (["-w", "--", "."], ["-w"]),
        (["-wo", "out"], ["-wo", "out"]),
    ],
)
def test_split_args_drops_a_source_directory_naming_the_repository(
    monkeypatch: pytest.MonkeyPatch, args: list[str], forward: list[str]
) -> None:
    """``tox -e build -- .`` builds as before, with the archived tree as the only source."""
    script = _load_script()
    monkeypatch.chdir(ROOT)

    assert script.split_args(_parser(), args, ROOT)[1] == forward


def test_split_args_rejects_another_source(tmp_path: Path) -> None:
    """A source directory other than the repository fails rather than being ignored."""
    script = _load_script()

    with pytest.raises(SystemExit, match="takes no other source"):
        script.split_args(_parser(), [str(tmp_path)], ROOT)


@pytest.mark.skipif(shutil.which("uv") is None, reason="needs uv")
def test_pins_come_from_head_not_the_working_tree(tmp_path: Path) -> None:
    """A working-tree uv.lock that differs from HEAD's does not reach the extra."""
    script = _load_script()
    repo = tmp_path / "repo"
    repo.mkdir()
    for name in ("pyproject.toml", "uv.lock"):
        shutil.copy2(ROOT / name, repo / name)
    _git(repo, "init", "-q")
    _git(repo, "add", "pyproject.toml", "uv.lock")
    _git(repo, "commit", "-q", "-m", "Add project")
    committed = (repo / "uv.lock").read_text(encoding="utf-8")
    entry = 'name = "idna"\nversion = "'
    assert committed.count(entry) == 1
    head_version = committed.split(entry, 1)[1].split('"', 1)[0]
    # uv rejects a lock whose artefact filenames disagree with the version.
    changed = committed.replace(entry + head_version, entry + "999.0").replace(f"idna-{head_version}", "idna-999.0")
    (repo / "uv.lock").write_text(changed, encoding="utf-8")
    assert "idna==999.0" in script.read_pins(repo)

    tree = tmp_path / "tree"
    script.extract_head(repo, tree)
    pins = script.read_pins(tree)

    assert f"idna=={head_version}" in pins
    assert "idna==999.0" not in pins
