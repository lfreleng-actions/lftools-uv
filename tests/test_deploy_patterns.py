# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for how the deploy commands collect a build's files.

``copy_archives`` stages the files a ``-p`` pattern matches below the
workspace into the current directory, keeping each file's path relative
to the workspace, and ``deploy s3`` compresses and uploads what it
staged. Every test works on real files under ``tmp_path``; the S3
resource is a fake, so no test reaches AWS, Nexus or the network.
"""

import logging
import os
import zipfile
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import ANY, patch

import pytest

from lftools_uv.deploy.archives import copy_archives, deploy_archives
from lftools_uv.deploy.s3 import deploy_s3

S3_PATH = "logs/silo/host/job/1/"
BUILD_URL = "https://jenkins.example.org/job/job/1/"
INDEX_MARKER = "_tmpfile"

DEFAULT_FILES = {
    "logs/top.txt": "top",
    "logs/sub/deep.txt": "deep",
    "a1.log": "first",
    "b1.log": "second",
    "q/x.log": "x",
}
LOG_FILES = {"a1.log": "first", "b1.log": "second", "q/x.log": "x"}
TXT_FILES = {"logs/top.txt": "top", "logs/sub/deep.txt": "deep"}


def _make_workspace(root: Path, files: dict[str, str] | None = None) -> Path:
    """Create ``root/ws`` with an empty ``archives`` directory and *files*."""
    ws = root / "ws"
    (ws / "archives").mkdir(parents=True)
    for name, text in (DEFAULT_FILES if files is None else files).items():
        path = ws / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
    return ws


def _read_tree(root: Path, exclude: str | None = None) -> dict[str, str]:
    """Return ``{relative path: text}`` for every file below *root*."""
    tree: dict[str, str] = {}
    for path in root.rglob("*"):
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        if exclude is not None and rel.startswith(f"{exclude}/"):
            continue
        tree[rel] = path.read_text()
    return tree


@pytest.fixture(autouse=True)
def _no_s3_bucket(monkeypatch):
    """Keep ``copy_archives`` from adding S3 markers to empty directories."""
    monkeypatch.delenv("S3_BUCKET", raising=False)


@pytest.fixture
def stage(tmp_path, monkeypatch):
    """Make an empty ``tmp_path / "stage"`` the working directory."""
    staging = tmp_path / "stage"
    staging.mkdir()
    monkeypatch.chdir(staging)
    return staging


@pytest.mark.parametrize("pattern", ["logs/**/*.txt", "./logs/**/*.txt"])
def test_globstar_inside_pattern_matches_zero_directories(tmp_path, stage, pattern):
    """``**`` in the middle of a pattern matches files directly below it."""
    ws = _make_workspace(tmp_path)
    copy_archives(str(ws), [pattern])
    assert _read_tree(stage) == TXT_FILES


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("**/*.txt", TXT_FILES),
        ("logs/**", TXT_FILES),
        ("*.log", {"a1.log": "first", "b1.log": "second"}),
        ("q/*.log", {"q/x.log": "x"}),
    ],
)
def test_patterns_stage_matching_files(tmp_path, stage, pattern, expected):
    """Leading ``**/``, trailing ``/**`` and plain patterns keep working."""
    ws = _make_workspace(tmp_path)
    copy_archives(str(ws), [pattern])
    assert _read_tree(stage) == expected


def test_double_star_inside_component_crosses_directories(tmp_path, stage):
    """``**`` inside a component keeps matching any characters, ``/`` included."""
    ws = _make_workspace(tmp_path)
    copy_archives(str(ws), ["logs/**.txt"])
    assert _read_tree(stage) == TXT_FILES


def test_whole_and_embedded_double_stars_combine(tmp_path, stage):
    """A whole ``**`` still matches zero directories beside an embedded one."""
    files = {
        "logs/report1.txt": "1",
        "logs/sub/report2.txt": "2",
        "logs/sub/deeper/report3.txt": "3",
        "logs/other.txt": "other",
    }
    ws = _make_workspace(tmp_path, files)
    copy_archives(str(ws), ["logs/**/report**.txt"])
    assert _read_tree(stage) == {name: text for name, text in files.items() if "report" in name}


EMBEDDED_FILES = {
    "real/top.txt": "top",
    "real/sub/deep.txt": "deep",
    "logs/report1.txt": "1",
    "logs/sub/report2.txt": "2",
    ".tox/run.log": "tox",
    "a.log": "a",
}


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("real/**.txt", ["real/top.txt", "real/sub/deep.txt"]),
        ("logs/**/report**.txt", ["logs/report1.txt", "logs/sub/report2.txt"]),
        ("***.log", ["a.log", ".tox/run.log"]),
        ("./logs/**", ["logs/report1.txt", "logs/sub/report2.txt"]),
        ("**/*.log", ["a.log", ".tox/run.log"]),
    ],
)
def test_embedded_double_stars_stage_matching_files(tmp_path, stage, pattern, expected):
    """Embedded ``**`` runs cross directories, hidden ones included, beside whole ``**`` components."""
    ws = _make_workspace(tmp_path, EMBEDDED_FILES)
    copy_archives(str(ws), [pattern])
    assert _read_tree(stage) == {name: EMBEDDED_FILES[name] for name in expected}


def test_embedded_star_runs_walk_the_workspace_once(tmp_path, stage):
    """Many embedded ``**`` runs are matched in one walk, not one glob per combination."""
    files = {"aaaaaaaaaaaa.log": "flat", "a/a/a/a/a/a/a/a/a/a/a/a.log": "deep", "a.log": "short"}
    ws = _make_workspace(tmp_path, files)
    real_glob = Path.glob
    calls: list[str] = []

    def counting_glob(self: Path, pattern: str, *args: object, **kwargs: object) -> Iterator[Path]:
        calls.append(pattern)
        return real_glob(self, pattern, *args, **kwargs)

    with patch.object(Path, "glob", counting_glob):
        copy_archives(str(ws), ["a**" * 12 + ".log"])

    # Path.rglob calls Path.glob once on Python 3.13 and later.
    assert len(calls) <= 1
    assert _read_tree(stage) == {"aaaaaaaaaaaa.log": "flat", "a/a/a/a/a/a/a/a/a/a/a/a.log": "deep"}


@pytest.mark.parametrize("pattern", ["logs/*.txt", "logs/**/*.txt", "logs/**"])
def test_files_below_symlinked_directory_are_not_staged(tmp_path, stage, caplog, pattern):
    """A symlinked directory cannot pull outside files into the archive."""
    outside = tmp_path / "outside"
    (outside / "sub").mkdir(parents=True)
    (outside / "secret.txt").write_text("secret")
    (outside / "sub" / "deep-secret.txt").write_text("deep secret")
    ws = _make_workspace(tmp_path, {})
    os.symlink(outside, ws / "logs", target_is_directory=True)

    with caplog.at_level(logging.WARNING, logger="lftools_uv.deploy"):
        copy_archives(str(ws), [pattern])

    assert _read_tree(stage) == {}
    assert _read_tree(outside) == {"secret.txt": "secret", "sub/deep-secret.txt": "deep secret"}
    assert "symbolic link" in caplog.text
    assert str(ws / "logs") in caplog.text


def test_double_star_inside_brackets_matches_one_name(tmp_path, stage):
    """``[**]`` matches a literal ``*`` and never crosses directories."""
    files = {"logs/*.txt": "star", "logs/[private/secret].txt": "secret", "logs/top.txt": "top"}
    ws = _make_workspace(tmp_path, files)
    copy_archives(str(ws), ["logs/[**].txt"])
    assert _read_tree(stage) == {"logs/*.txt": "star"}
    assert (ws / "logs" / "[private" / "secret].txt").read_text() == "secret"


@pytest.mark.parametrize("pattern", ["logs/*.txt/", "logs/**/", "logs/**/.", "logs/.", "."])
def test_directory_only_pattern_stages_nothing(tmp_path, stage, pattern):
    """A pattern ending in ``/`` or ``/.`` matches only directories, so no file is staged."""
    ws = _make_workspace(tmp_path)
    copy_archives(str(ws), [pattern])
    assert _read_tree(stage) == {}
    assert _read_tree(ws) == DEFAULT_FILES


def test_bracket_ranges_keep_adjacent_star_endpoints(tmp_path, stage):
    """``[*-**-z]`` is two ranges, ``*`` to ``*`` and ``*`` to ``z``, as fnmatch reads it."""
    files = {"logs/*.txt": "star", "logs/-.txt": "dash", "logs/x.txt": "x", "logs/top.txt": "top"}
    ws = _make_workspace(tmp_path, files)
    copy_archives(str(ws), ["logs/[*-**-z].txt"])
    assert _read_tree(stage) == {"logs/*.txt": "star", "logs/-.txt": "dash", "logs/x.txt": "x"}
    assert _read_tree(ws) == {"logs/top.txt": "top"}


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("logs/[!**]op.txt", {"logs/top.txt": "top"}),
        ("logs/**/[**].txt", {"logs/*.txt": "star", "logs/sub/*.txt": "deep star"}),
    ],
)
def test_bracket_star_runs_match_by_component(tmp_path, stage, pattern, expected):
    """Bracket patterns keep their meaning, and a whole ``**`` beside them matches zero or more directories."""
    files = {"logs/*.txt": "star", "logs/sub/*.txt": "deep star", "logs/top.txt": "top"}
    ws = _make_workspace(tmp_path, files)
    copy_archives(str(ws), [pattern])
    assert _read_tree(stage) == expected


@pytest.mark.parametrize(
    ("pattern", "expected"),
    [
        ("logs/[!**]/**.txt", {"logs/a/top.txt": "top", "logs/a/sub/deep.txt": "deep"}),
        ("logs/[**]/**.txt", {"logs/*/x.txt": "x"}),
        ("logs/[!**]/*.txt", {"logs/a/top.txt": "top"}),
        ("logs/[!**]/?**.txt", {"logs/a/top.txt": "top", "logs/a/sub/deep.txt": "deep"}),
        ("logs/[!**]/s?b**.txt", {"logs/a/sub/deep.txt": "deep"}),
        ("logs/[!**]/su*/**.txt", {"logs/a/sub/deep.txt": "deep"}),
        ("logs/[!**]/a[!x]sub**.txt", {}),
        ("logs/[!**]/*[s]*.txt", {}),
    ],
)
def test_bracket_star_run_beside_embedded_double_star(tmp_path, stage, pattern, expected):
    """An embedded ``**`` beside a bracket star run still crosses directories, and nothing else does."""
    files = {"logs/a/top.txt": "top", "logs/a/sub/deep.txt": "deep", "logs/*/x.txt": "x", "logs/top.txt": "flat"}
    ws = _make_workspace(tmp_path, files)
    copy_archives(str(ws), [pattern])
    assert _read_tree(stage) == expected


def test_bracket_star_run_with_trailing_double_star_stages_only_descendants(tmp_path, stage):
    """A trailing ``**`` after a bracket star run selects only files below the matching directories."""
    ws = _make_workspace(tmp_path, {"logs/a": "a", "logs/b/run.log": "run"})
    copy_archives(str(ws), ["logs/[!**]/**"])
    assert _read_tree(stage) == {"logs/b/run.log": "run"}
    assert (ws / "logs" / "a").read_text() == "a"


def test_bracket_star_run_below_symlinked_directory_is_not_staged(tmp_path, stage):
    """The component matcher skips files below a symlinked directory too."""
    outside = tmp_path / "outside"
    outside.mkdir()
    (outside / "*.txt").write_text("secret")
    ws = _make_workspace(tmp_path, {})
    os.symlink(outside, ws / "link", target_is_directory=True)
    copy_archives(str(ws), ["link/[**].txt"])
    assert _read_tree(stage) == {}
    assert _read_tree(outside) == {"*.txt": "secret"}


@pytest.mark.parametrize("pattern", ["../neighbor/**/*.log", "../neighbor/*.log", "absolute"])
def test_patterns_outside_workspace_are_refused(tmp_path, stage, pattern):
    """An absolute pattern or one with ``..`` fails before anything moves."""
    ws = _make_workspace(tmp_path, {"archives/report.txt": "report", "a1.log": "first"})
    neighbor = tmp_path / "neighbor"
    neighbor.mkdir()
    (neighbor / "secret.log").write_text("secret")
    if pattern == "absolute":
        pattern = str(neighbor / "secret.log")

    with pytest.raises(ValueError, match="must stay inside the workspace"):
        copy_archives(str(ws), [pattern])

    assert _read_tree(stage) == {}
    assert _read_tree(ws) == {"archives/report.txt": "report", "a1.log": "first"}
    assert _read_tree(neighbor) == {"secret.log": "secret"}


def test_absolute_workspace_keeps_paths(tmp_path, stage):
    """An absolute workspace keeps every file's path and contents."""
    ws = _make_workspace(tmp_path)
    copy_archives(str(ws), ["**/*.log"])
    assert _read_tree(stage) == LOG_FILES


def test_workspace_with_trailing_slash_keeps_paths(tmp_path, stage):
    """A trailing slash on the workspace does not change staged paths."""
    ws = _make_workspace(tmp_path)
    copy_archives(f"{ws}/", ["**/*.log"])
    assert _read_tree(stage) == LOG_FILES


@pytest.mark.parametrize("workspace", ["./ws", "./ws/"])
def test_relative_workspace_keeps_paths(tmp_path, monkeypatch, workspace):
    """A relative workspace stages files at their own relative paths."""
    _make_workspace(tmp_path)
    monkeypatch.chdir(tmp_path)
    copy_archives(workspace, ["**/*.log"])
    assert _read_tree(tmp_path, exclude="ws") == LOG_FILES


def test_dot_workspace_keeps_paths(tmp_path, monkeypatch):
    """Workspace ``.`` leaves each file at its own path."""
    ws = _make_workspace(tmp_path)
    monkeypatch.chdir(ws)
    copy_archives(".", ["**/*.log"])
    tree = _read_tree(ws)
    assert {name: tree.get(name) for name in LOG_FILES} == LOG_FILES
    assert ".log" not in tree


RELATIVE_WORKSPACES = [("./ws", "."), ("ws/", "."), (".", "ws")]
RELATIVE_FILES = {"archives/report.txt": "report", **LOG_FILES}
RELATIVE_STAGED = {"report.txt.gz", "a1.log.gz", "b1.log.gz", "q/x.log.gz"}


@pytest.mark.parametrize(("workspace", "cwd"), RELATIVE_WORKSPACES)
def test_deploy_archives_resolves_relative_workspace(tmp_path, monkeypatch, workspace, cwd):
    """``deploy archives`` reads a relative workspace from the caller's directory."""
    ws = _make_workspace(tmp_path, RELATIVE_FILES)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(tmp_path / cwd)
    with (
        patch("lftools_uv.deploy.archives.tempfile.mkdtemp", return_value=str(work_dir)),
        patch("lftools_uv.deploy.archives.deploy_nexus_zip") as upload,
    ):
        deploy_archives("https://nexus.example.org", "silo/job/1", workspace, ["**/*.log"])

    upload.assert_called_once_with(ANY, "logs", "silo/job/1", str(ws / "archives.zip"))
    with zipfile.ZipFile(ws / "archives.zip") as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
    assert names == RELATIVE_STAGED
    assert Path.cwd() == tmp_path / cwd


# A WORKSPACE with ".." after a symlinked directory, given relative to the
# caller's directory and as an absolute path.
SYMLINK_PARENT_FORMS = pytest.mark.parametrize(
    "absolute",
    [
        pytest.param(
            False,
            id="relative",
        ),
        pytest.param(True, id="absolute"),
    ],
)


def _make_symlinked_parent(root: Path) -> tuple[Path, Path]:
    """Create ``ws``, and a decoy workspace whose ``link`` points to ``ws/child``.

    ``decoy/ws/link/..`` names ``ws``: the kernel follows ``link`` before
    applying ``..``. Removing both as text would name the decoy instead.
    """
    ws = _make_workspace(root, RELATIVE_FILES)
    (ws / "child").mkdir()
    decoy = _make_workspace(root / "decoy", {"archives/decoy.txt": "decoy", "decoy.log": "decoy"})
    (decoy / "link").symlink_to(ws / "child", target_is_directory=True)
    return ws, decoy


@SYMLINK_PARENT_FORMS
def test_deploy_archives_follows_symlink_before_parent(tmp_path, monkeypatch, absolute):
    """``deploy archives`` deploys the workspace that ``link/..`` names, not the decoy."""
    ws, decoy = _make_symlinked_parent(tmp_path)
    workspace = str(decoy / "link" / "..") if absolute else "decoy/ws/link/.."
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    with (
        patch("lftools_uv.deploy.archives.tempfile.mkdtemp", return_value=str(work_dir)),
        patch("lftools_uv.deploy.archives.deploy_nexus_zip"),
    ):
        deploy_archives("https://nexus.example.org", "silo/job/1", workspace, ["**/*.log"])

    with zipfile.ZipFile(ws / "archives.zip") as archive:
        names = {name for name in archive.namelist() if not name.endswith("/")}
    assert names == RELATIVE_STAGED
    assert _read_tree(decoy) == {"archives/decoy.txt": "decoy", "decoy.log": "decoy"}


@SYMLINK_PARENT_FORMS
def test_s3_follows_symlink_before_parent(tmp_path, monkeypatch, absolute):
    """``deploy s3`` uploads the workspace that ``link/..`` names, not the decoy."""
    _ws, decoy = _make_symlinked_parent(tmp_path)
    workspace = str(decoy / "link" / "..") if absolute else "decoy/ws/link/.."
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    s3 = FakeS3()
    with (
        patch("lftools_uv.deploy.s3.boto3.resource", return_value=s3),
        patch("lftools_uv.deploy.s3.tempfile.mkdtemp", return_value=str(work_dir)),
        patch("lftools_uv.deploy.s3._capture_build_logs"),
    ):
        deploy_s3("bucket", S3_PATH, BUILD_URL, workspace, ["**/*.log"])

    uploaded = {
        key.removeprefix(S3_PATH) for key in s3.uploaded if key.startswith(S3_PATH) and not key.endswith(INDEX_MARKER)
    }
    assert uploaded == RELATIVE_STAGED
    assert _read_tree(decoy) == {"archives/decoy.txt": "decoy", "decoy.log": "decoy"}


class FakeS3:
    """Record the keys of uploaded files."""

    def __init__(self) -> None:
        self.uploaded: list[str] = []

    def Bucket(self, _name: str) -> "FakeS3":  # noqa: N802 - mirrors the boto3 resource API
        return self

    def Object(self, _bucket: str, _key: str) -> "FakeS3":  # noqa: N802 - mirrors the boto3 resource API
        return self

    def upload_file(self, _file: str, key: str, **_kwargs: object) -> None:
        self.uploaded.append(key)

    def delete(self) -> None:
        """Accept the deletion of an index marker."""


@pytest.mark.xfail(strict=True, reason="#982: hidden files are not uploaded")
def test_s3_uploads_hidden_files(tmp_path, monkeypatch):
    """``deploy s3`` compresses and uploads files under dot-directories."""
    ws = _make_workspace(
        tmp_path,
        {
            "archives/report.html": "report",
            "archives/.hidden/inner.log": "inner",
            ".tox/py3/log/tox-run.log": "tox",
            "build/out.log": "out",
        },
    )
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(tmp_path)
    s3 = FakeS3()
    with (
        patch("lftools_uv.deploy.s3.boto3.resource", return_value=s3),
        patch("lftools_uv.deploy.s3.tempfile.mkdtemp", return_value=str(work_dir)),
        patch("lftools_uv.deploy.s3._capture_build_logs"),
    ):
        deploy_s3("bucket", S3_PATH, BUILD_URL, str(ws), ["**/*.log"])

    uploaded = {
        key.removeprefix(S3_PATH) for key in s3.uploaded if key.startswith(S3_PATH) and not key.endswith(INDEX_MARKER)
    }
    assert uploaded == {
        ".hidden/inner.log.gz",
        ".tox/py3/log/tox-run.log.gz",
        "build/out.log.gz",
        "report.html.gz",
    }
    assert Path.cwd() == tmp_path


@pytest.mark.parametrize(("workspace", "cwd"), RELATIVE_WORKSPACES)
def test_s3_resolves_relative_workspace(tmp_path, monkeypatch, workspace, cwd):
    """``deploy s3`` reads a relative workspace from the caller's directory."""
    _make_workspace(tmp_path, RELATIVE_FILES)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(tmp_path / cwd)
    s3 = FakeS3()
    with (
        patch("lftools_uv.deploy.s3.boto3.resource", return_value=s3),
        patch("lftools_uv.deploy.s3.tempfile.mkdtemp", return_value=str(work_dir)),
        patch("lftools_uv.deploy.s3._capture_build_logs"),
    ):
        deploy_s3("bucket", S3_PATH, BUILD_URL, workspace, ["**/*.log"])

    uploaded = {
        key.removeprefix(S3_PATH) for key in s3.uploaded if key.startswith(S3_PATH) and not key.endswith(INDEX_MARKER)
    }
    assert uploaded == RELATIVE_STAGED
    assert Path.cwd() == tmp_path / cwd
