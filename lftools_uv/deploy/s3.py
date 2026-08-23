# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Deploy build archives and logs to an S3 bucket."""

from __future__ import annotations

import glob
import mimetypes
import os
import tempfile
from dataclasses import dataclass
from typing import Any

import boto3

# aislop-ignore-next-line hallucinated-import -- botocore ships with the declared boto3 dependency
from botocore.exceptions import ClientError

from lftools_uv.deploy._build_logs import _capture_build_logs
from lftools_uv.deploy._common import _BANNER_HASHES, _CONTENT_TYPE_TEXT, _CONTENT_TYPE_XML, log
from lftools_uv.deploy._late import _copy_archives
from lftools_uv.deploy._util import _compress_text

# Uploaded to each top level "directory" so that s3, which has no filesystem,
# generates or updates the index.html file there.
_INDEX_MARKER = "_tmpfile"


@dataclass(frozen=True)
class _S3Target:
    """Bucket and the prefixes a build's files are uploaded under."""

    bucket: str
    path: str
    logs_dir: str
    silo_dir: str
    jenkins_node_dir: str

    @classmethod
    def from_path(cls, s3_bucket: str, s3_path: str) -> _S3Target:
        """Split an S3 path into the prefixes that hold an index marker."""
        logs_dir: str = s3_path.split("/")[0] + "/"
        silo_dir: str = s3_path.split("/")[1] + "/"
        jenkins_node_dir: str = logs_dir + silo_dir + s3_path.split("/")[2] + "/"
        return cls(s3_bucket, s3_path, logs_dir, silo_dir, jenkins_node_dir)

    @property
    def index_dirs(self) -> tuple[str, str, str]:
        """Return the prefixes whose index.html the marker file refreshes."""
        return (self.logs_dir, self.silo_dir, self.jenkins_node_dir)


def _extra_args(content_type: str, mime_encoding: str | None) -> dict[str, str]:
    """Build an ExtraArgs dict, omitting ContentEncoding when None.

    boto3's S3 transfer manager rejects ``None`` values for ``ExtraArgs``
    entries with a ``ParamValidationError``; many file types
    (e.g. plain ``.html`` / ``.xml`` without compression) have no
    mime_encoding, so the key must be omitted entirely in that case.
    """
    args: dict[str, str] = {"ContentType": content_type}
    if mime_encoding:
        args["ContentEncoding"] = mime_encoding
    return args


def _upload_args(mime_type: str | None, mime_encoding: str | None) -> tuple[dict[str, str], str]:
    """Return the ExtraArgs and the failure message for a file's mime type."""
    if mime_type is None and mime_encoding is None:
        return {"ContentType": _CONTENT_TYPE_TEXT}, "Failed to upload %s"
    if mime_type is None or mime_type == _CONTENT_TYPE_TEXT:
        return _extra_args(_CONTENT_TYPE_TEXT, mime_encoding), "Failed to upload %s as text/plain"
    if mime_type == "text/html":
        return _extra_args("text/html", mime_encoding), "Failed to upload %s as text/html"
    if mime_type == _CONTENT_TYPE_XML:
        return _extra_args(_CONTENT_TYPE_XML, mime_encoding), "Failed to upload %s as application/xml"
    return {"ContentType": _CONTENT_TYPE_TEXT}, "Failed to upload %s"


def _upload_index_marker(s3: Any, target: _S3Target, file: str) -> bool:
    """Upload the index marker to every top level "directory"."""
    for prefix in target.index_dirs:
        try:
            s3.Bucket(target.bucket).upload_file(file, f"{prefix}{file}")
        except ClientError:
            log.exception("Failed to upload _tmpfile marker to %s", prefix)
            return False
    return True


def _upload_to_s3(s3: Any, target: _S3Target, file: str) -> bool:
    """Upload a single file, returning False when S3 rejected it."""
    mime_type: str | None = mimetypes.guess_type(file)[0]
    mime_encoding: str | None = mimetypes.guess_type(file)[1]

    if file == _INDEX_MARKER:
        return _upload_index_marker(s3, target, file)

    extra_args, failure_message = _upload_args(mime_type, mime_encoding)
    try:
        s3.Bucket(target.bucket).upload_file(file, f"{target.path}{file}", ExtraArgs=extra_args)
    except ClientError:
        log.exception(failure_message, file)
        return False
    return True


def _delete_index_markers(s3: Any, target: _S3Target) -> None:
    """Remove the index marker objects uploaded during the deploy."""
    s3.Object(target.bucket, f"{target.logs_dir}{_INDEX_MARKER}").delete()
    s3.Object(target.bucket, f"{target.silo_dir}{_INDEX_MARKER}").delete()
    s3.Object(target.bucket, f"{target.jenkins_node_dir}{_INDEX_MARKER}").delete()


def _files_in_work_dir() -> list[str]:
    """List the files below the current directory, recursively."""
    file_list: list[str] = []
    files: list[str] = glob.glob("**/*", recursive=True)
    for file in files:
        if os.path.isfile(file):
            file_list.append(file)
    return file_list


def deploy_s3(s3_bucket: str, s3_path: str, build_url: str, workspace: str, pattern: list[str] | None = None) -> None:
    """Add logs and archives to temp directory to be shipped to S3 bucket.

    Fetches logs and system information and pushes them and archives to S3
    for log archiving.

    Requires the s3 bucket to exist.

    Parameters:

        :s3_bucket: Name of S3 bucket. Eg: lf-project-date
        :s3_path: Path on S3 bucket place the logs and archives. Eg:
            $SILO/$JENKINS_HOSTNAME/$JOB_NAME/$BUILD_NUMBER
        :build_url: URL of the Jenkins build. Jenkins typically provides this
                    via the $BUILD_URL environment variable.
        :workspace: Directory in which to search, typically in Jenkins this is
            $WORKSPACE
        :pattern: Space-separated list of Globstar patterns of files to
            archive. (optional)
    """
    previous_dir: str = os.getcwd()
    work_dir: str = tempfile.mkdtemp(prefix="lftools-dl.")
    os.chdir(work_dir)
    s3_bucket = s3_bucket.lower()
    s3: Any = boto3.resource("s3")
    target: _S3Target = _S3Target.from_path(s3_bucket, s3_path)

    log.debug("work_dir: %s", work_dir)

    # Copy archive files to tmp dir
    _copy_archives(workspace, pattern)

    _capture_build_logs(build_url)

    open(_INDEX_MARKER, "a").close()  # noqa: PTH123, SIM115

    # Compress tmp directory
    _compress_text(work_dir)

    file_list: list[str] = _files_in_work_dir()

    log.info(_BANNER_HASHES)
    log.info("Deploying files from %s to %s/%s", work_dir, s3_bucket, s3_path)

    # Perform s3 upload
    for file in file_list:
        log.info("Attempting to upload file %s", file)
        if _upload_to_s3(s3, target, file):
            log.info("Successfully uploaded %s", file)
        else:
            log.error("FAILURE: Uploading %s failed", file)

    log.info("Finished deploying from %s to %s/%s", work_dir, s3_bucket, s3_path)
    log.info(_BANNER_HASHES)

    _delete_index_markers(s3, target)
    os.chdir(previous_dir)
    # shutil.rmtree(work_dir)
