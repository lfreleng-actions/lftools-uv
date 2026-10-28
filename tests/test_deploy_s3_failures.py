# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``deploy s3`` when an upload fails.

A failed upload, whether boto3 raises ``S3UploadFailedError`` or botocore
raises ``ClientError``, must not stop the remaining uploads or leave the
``_tmpfile`` index markers in the bucket, and the deploy must then fail
naming every file that did not upload.

The S3 resource is a fake: no test reaches AWS or the network.
"""

from collections.abc import Callable, Iterator
from pathlib import Path
from unittest.mock import patch

import pytest
import requests
from boto3.exceptions import S3UploadFailedError

# aislop-ignore-next-line hallucinated-import -- botocore ships with the declared boto3 dependency
from botocore.exceptions import ClientError
from click.testing import CliRunner as ClickRunner
from typer.testing import CliRunner as TyperRunner

from lftools_uv.cli import cli
from lftools_uv.deploy.s3 import deploy_s3
from lftools_uv.typer_apps.deploy import deploy_app

BUCKET = "logs-bucket"
S3_PATH = "logs/silo/node/job/1/"
BUILD_URL = "https://jenkins.example.org/job/job/1/"
LOG_FILES = ("console.log", "sysinfo.log", "packages.log")
MARKER_KEYS = {"logs/_tmpfile", "silo/_tmpfile", "logs/silo/node/_tmpfile"}

ErrorFactory = Callable[[], Exception]
Installer = Callable[[dict[str, ErrorFactory]], "FakeS3"]


def _client_error() -> Exception:
    return ClientError({"Error": {"Code": "500", "Message": "Internal error"}}, "PutObject")


def _upload_failed() -> Exception:
    return S3UploadFailedError("Failed to upload console.log")


class FakeS3:
    """Record uploads and deletions, raising for the chosen files."""

    def __init__(self, failures: dict[str, ErrorFactory]) -> None:
        self.failures = failures
        self.delete_error: ErrorFactory | None = None
        self.uploaded: list[str] = []
        self.attempted: list[str] = []
        self.deleted: set[str] = set()

    def Bucket(self, _name: str) -> "FakeS3":  # noqa: N802 - mirrors the boto3 resource API
        return self

    def Object(self, _bucket: str, key: str) -> "FakeObject":  # noqa: N802 - mirrors the boto3 resource API
        return FakeObject(self, key)

    def upload_file(self, file: str, key: str, **_kwargs: object) -> None:
        self.attempted.append(file)
        if file in self.failures:
            raise self.failures[file]()
        self.uploaded.append(key)


class FakeObject:
    """Record the deletion of one key."""

    def __init__(self, s3: FakeS3, key: str) -> None:
        self.s3 = s3
        self.key = key

    def delete(self) -> None:
        if self.s3.delete_error is not None:
            raise self.s3.delete_error()
        self.s3.deleted.add(self.key)


def _write_logs(_build_url: str) -> None:
    for name in LOG_FILES:
        Path(name).write_text(f"{name}\n")


@pytest.fixture
def fake_s3(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[Installer]:
    """Patch the S3 resource and the build-log helpers around ``deploy_s3``."""
    monkeypatch.chdir(tmp_path)
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    holder: dict[str, FakeS3] = {}

    def install(failures: dict[str, ErrorFactory]) -> FakeS3:
        holder["s3"] = FakeS3(failures)
        return holder["s3"]

    with (
        patch("lftools_uv.deploy.s3.boto3.resource", side_effect=lambda _name: holder["s3"]),
        patch("lftools_uv.deploy.s3.tempfile.mkdtemp", return_value=str(work_dir)),
        patch("lftools_uv.deploy.s3._capture_build_logs", side_effect=_write_logs),
        patch("lftools_uv.deploy.s3._copy_archives"),
        patch("lftools_uv.deploy.s3._compress_text"),
    ):
        yield install


@pytest.mark.parametrize("error", [_upload_failed, _client_error], ids=["upload-failed", "client-error"])
def test_failed_upload_reports_and_cleans_up(fake_s3: Installer, tmp_path: Path, error: ErrorFactory) -> None:
    """Every file is still attempted, markers go, and the failure is named."""
    s3 = fake_s3({"console.log": error})
    with pytest.raises(requests.HTTPError, match="console.log"):
        deploy_s3(BUCKET, S3_PATH, BUILD_URL, str(tmp_path))
    assert set(LOG_FILES) <= set(s3.attempted)
    assert s3.deleted == MARKER_KEYS
    assert Path.cwd() == tmp_path


def test_successful_deploy_deletes_markers(fake_s3: Installer, tmp_path: Path) -> None:
    """A deploy where every upload succeeds returns and deletes the markers."""
    s3 = fake_s3({})
    deploy_s3(BUCKET, S3_PATH, BUILD_URL, str(tmp_path))
    assert {f"{S3_PATH}{name}" for name in LOG_FILES} <= set(s3.uploaded)
    assert s3.deleted == MARKER_KEYS
    assert Path.cwd() == tmp_path


def _access_denied() -> Exception:
    return ClientError({"Error": {"Code": "AccessDenied", "Message": "Access Denied"}}, "DeleteObject")


@pytest.mark.parametrize("failures", [{}, {"console.log": _upload_failed}], ids=["uploads-ok", "upload-failed"])
def test_failed_marker_delete_restores_cwd(
    fake_s3: Installer, tmp_path: Path, failures: dict[str, ErrorFactory]
) -> None:
    """A marker deletion that fails still returns to the previous directory."""
    s3 = fake_s3(failures)
    s3.delete_error = _access_denied
    with pytest.raises(ClientError, match="AccessDenied"):
        deploy_s3(BUCKET, S3_PATH, BUILD_URL, str(tmp_path))
    assert Path.cwd() == tmp_path


def test_failed_marker_delete_keeps_upload_failures(fake_s3: Installer, tmp_path: Path) -> None:
    """A failed marker deletion carries the upload failure as its context."""
    s3 = fake_s3({"console.log": _upload_failed})
    s3.delete_error = _access_denied
    with pytest.raises(ClientError, match="AccessDenied") as excinfo:
        deploy_s3(BUCKET, S3_PATH, BUILD_URL, str(tmp_path))
    context = excinfo.value.__context__
    assert isinstance(context, requests.HTTPError)
    assert "console.log" in str(context)


def test_typer_deploy_s3_exits_one(fake_s3: Installer, tmp_path: Path) -> None:
    """Typer ``deploy s3`` exits 1 when an upload fails."""
    fake_s3({"console.log": _client_error})
    result = TyperRunner().invoke(deploy_app, ["s3", BUCKET, S3_PATH, BUILD_URL, str(tmp_path)])
    assert result.exit_code == 1


def test_click_deploy_s3_exits_one(fake_s3: Installer, tmp_path: Path) -> None:
    """Click ``deploy s3`` exits 1 when an upload fails."""
    fake_s3({"console.log": _client_error})
    result = ClickRunner().invoke(cli, ["deploy", "s3", BUCKET, S3_PATH, BUILD_URL, str(tmp_path)], obj={})
    assert result.exit_code == 1
