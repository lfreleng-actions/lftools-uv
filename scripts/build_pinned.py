# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Build the sdist and wheel with a ``pinned`` extra from uv.lock.

The extra pins every runtime dependency to the version uv.lock records, so
``lftools-uv[pinned]`` installs the set this release was tested with. It
exists only in built artefacts: in pyproject.toml its pins would stop
``uv lock`` from moving any version. The build therefore runs on a copy of
the committed tree with the extra added, at the version the real tree has.

Run it as ``tox -e build``; arguments pass through to ``python -m build``,
except a source directory, which must name this repository: the archived
tree is the build's only source. The artefacts are checked in a fresh
directory before they reach the output directory, ``dist/`` unless
``--outdir`` names another.
"""

import argparse
import contextlib
import importlib
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile

ROOT = pathlib.Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
TABLE = "[project.optional-dependencies]\n"
EXTRA = "pinned"


def run(*cmd: str, cwd: pathlib.Path = ROOT) -> str:
    """Run a command in ``cwd``, the repository by default, and return what it prints."""
    return subprocess.run(cmd, cwd=cwd, check=True, capture_output=True, text=True).stdout


def extract_head(root: pathlib.Path, dest: pathlib.Path) -> None:
    """Extract the tree of ``root``'s HEAD commit into ``dest``."""
    tree = subprocess.run(["git", "archive", "--format=tar", "HEAD"], cwd=root, check=True, capture_output=True).stdout
    with tarfile.open(fileobj=io.BytesIO(tree)) as tar:
        tar.extractall(dest, filter="data")


def read_pins(tree: pathlib.Path) -> list[str]:
    """Return the runtime requirements the uv.lock in ``tree`` records, one per line."""
    export = run(
        "uv",
        "export",
        "--frozen",
        "--no-dev",
        "--no-emit-project",
        "--no-hashes",
        "--no-header",
        "--no-annotate",
        cwd=tree,
    )
    return [line.strip() for line in export.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def add_extra(pyproject: pathlib.Path, pins: list[str]) -> None:
    """Add the ``pinned`` extra to a copy of pyproject.toml."""
    text = pyproject.read_text(encoding="utf-8")
    if text.count(TABLE) != 1:
        sys.exit("pyproject.toml: expected one [project.optional-dependencies] table")
    # JSON string escapes are valid TOML basic-string escapes.
    extra = f"{EXTRA} = [\n" + "".join(f"    {json.dumps(pin)},\n" for pin in pins) + "]\n"
    pyproject.write_text(text.replace(TABLE, TABLE + extra), encoding="utf-8")


def count_pinned(metadata: str) -> int:
    """Count the requirements core metadata declares for the ``pinned`` extra."""
    marker = f'extra == "{EXTRA}"'
    return sum(
        1 for line in metadata.splitlines() if line.startswith("Requires-Dist:") and marker in line.replace("'", '"')
    )


def wheel_metadata(wheel: pathlib.Path, version: str) -> str:
    """Return the METADATA file of a built wheel."""
    with zipfile.ZipFile(wheel) as archive:
        return archive.read(f"lftools_uv-{version}.dist-info/METADATA").decode()


def sdist_metadata(sdist: pathlib.Path, version: str) -> str:
    """Return the PKG-INFO file of a built sdist."""
    with tarfile.open(sdist) as tar:
        member = tar.extractfile(f"lftools_uv-{version}/PKG-INFO")
        if member is None:
            sys.exit(f"{sdist.name}: no PKG-INFO")
        return member.read().decode()


def build_parser() -> argparse.ArgumentParser:
    """Return the argument parser of ``python -m build``."""
    # Imported here: tox's build env provides build, the project's venv does not.
    parser: argparse.ArgumentParser = importlib.import_module("build.__main__").main_parser()
    return parser


def _parse(parser: argparse.ArgumentParser, args: list[str]) -> argparse.Namespace | None:
    """Parse ``args`` quietly; None when they do not parse."""
    with contextlib.redirect_stderr(io.StringIO()):
        try:
            return parser.parse_args(args)
        except SystemExit:
            return None


def split_args(parser: argparse.ArgumentParser, args: list[str], root: pathlib.Path) -> tuple[pathlib.Path, list[str]]:
    """Return the output directory ``args`` name, ``dist/`` by default, and the arguments to forward.

    ``args`` are parsed as ``python -m build`` parses them, so grouped short
    options such as ``-wo`` count. The archived tree is the build's only
    source, so a source directory in ``args`` must name ``root``, and is
    dropped from the arguments forwarded.
    """
    parser.set_defaults(srcdir=None)
    options = parser.parse_args(args)
    outdir = pathlib.Path(options.outdir).resolve() if options.outdir else DIST
    forward = list(args)
    if options.srcdir is not None and pathlib.Path(options.srcdir).resolve() != root.resolve():
        sys.exit(f"{options.srcdir}: the build packages {root} and takes no other source")
    if "--" in forward:
        separator = forward.index("--")
        forward, tail = forward[:separator], forward[separator + 1 :]
        if tail:
            # Only the source directory can follow the separator.
            return outdir, forward
    if options.srcdir is None:
        return outdir, forward
    # The source directory is the token whose removal leaves every option as it was.
    expected = vars(options) | {"srcdir": None}
    for index in reversed(range(len(forward))):
        rest = forward[:index] + forward[index + 1 :]
        if forward[index] == options.srcdir and (parsed := _parse(parser, rest)) and vars(parsed) == expected:
            return outdir, rest
    sys.exit(f"{options.srcdir}: cannot tell the source directory from the other arguments")


def check(outdir: pathlib.Path, version: str, pins: list[str]) -> None:
    """Fail unless each artefact in ``outdir`` declares one pinned requirement per pin."""
    artefacts = [
        (path, reader)
        for path, reader in (
            (next(outdir.glob(f"lftools_uv-{version}-*.whl"), None), wheel_metadata),
            (outdir / f"lftools_uv-{version}.tar.gz", sdist_metadata),
        )
        if path is not None and path.is_file()
    ]
    if not artefacts:
        sys.exit(f"{outdir}: no sdist or wheel for version {version}")
    for path, reader in artefacts:
        built = count_pinned(reader(path, version))
        if built != len(pins):
            sys.exit(f"{path.name}: {built} {EXTRA} requirements, uv.lock gives {len(pins)}")
        print(f"{path.name}: {EXTRA} extra with {built} requirements")


def publish(build_dir: pathlib.Path, outdir: pathlib.Path, version: str, pins: list[str]) -> None:
    """Check the artefacts in ``build_dir``, then copy them to ``outdir``; copy nothing if the check fails."""
    check(build_dir, version, pins)
    outdir.mkdir(parents=True, exist_ok=True)
    for artefact in build_dir.iterdir():
        shutil.copy2(artefact, outdir / artefact.name)


def main() -> None:
    """Build, check the artefacts carry the pins, and copy them to the output directory."""
    outdir, args = split_args(build_parser(), sys.argv[1:], ROOT)
    version = run(sys.executable, "-m", "hatchling", "version").strip()
    with tempfile.TemporaryDirectory() as tmp:
        tree_dir = pathlib.Path(tmp, "tree")
        # A fresh directory, so no earlier build's files are checked or published.
        build_dir = pathlib.Path(tmp, "dist")
        extract_head(ROOT, tree_dir)
        # From the archived uv.lock, so the pins match the source the build packages.
        pins = read_pins(tree_dir)
        add_extra(tree_dir / "pyproject.toml", pins)
        # The copy has no git history for hatch-vcs to read the version from.
        env = dict(os.environ, SETUPTOOLS_SCM_PRETEND_VERSION=version)
        # The last --outdir wins, so any the arguments carry cannot bypass the check.
        subprocess.run(
            [sys.executable, "-m", "build", *args, "--outdir", str(build_dir), str(tree_dir)], check=True, env=env
        )
        publish(build_dir, outdir, version, pins)


if __name__ == "__main__":
    main()
