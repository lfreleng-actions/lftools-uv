# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Collect build archives and logs, and ship them to a Nexus logs repo."""

from __future__ import annotations

import datetime
import errno
import fnmatch
import os
import shutil
import tempfile
from pathlib import Path

from lftools_uv.deploy._build_logs import _capture_build_logs
from lftools_uv.deploy._common import log
from lftools_uv.deploy._late import _copy_archives
from lftools_uv.deploy._util import _compress_text, _format_url, _remove_duplicates_and_sort
from lftools_uv.deploy.nexus import deploy_nexus_zip


def copy_archives(workspace: str, pattern: list[str] | None = None) -> None:
    """Copy files matching PATTERN in a WORKSPACE to the current directory.

    The best way to use this function is to cd into the directory you wish to
    store the files first before calling the function.

    This function provides 2 ways to archive files:

        1) copy $WORKSPACE/archives directory
        2) copy globstar pattern

    :params:

        :arg str pattern: Space-separated list of Unix style glob patterns.
            (default: None)
    """
    archives_dir: str = os.path.join(workspace, "archives")
    dest_dir: str = os.getcwd()

    log.debug("Copying files from %s with pattern '%s' to %s.", workspace, pattern, dest_dir)
    log.debug("archives_dir = %s", archives_dir)

    if os.path.exists(archives_dir):
        if os.path.isfile(archives_dir):
            log.error("Archives %s is a file, not a directory.", archives_dir)
            raise OSError(errno.ENOENT, "Not a directory", archives_dir)
        else:
            log.debug("Archives dir %s does exist.", archives_dir)
            for file_or_dir in os.listdir(archives_dir):
                f: str = os.path.join(archives_dir, file_or_dir)
                try:
                    log.debug("Moving %s", f)
                    _ = shutil.move(f, dest_dir)
                except shutil.Error as e:
                    log.error(e)
                    raise OSError(errno.EPERM, "Could not move to", archives_dir) from e
    else:
        log.error("Archives dir %s does not exist.", archives_dir)
        raise OSError(errno.ENOENT, "Missing directory", archives_dir)

    if pattern is None:
        return

    no_dups_pattern: list[str] = _remove_duplicates_and_sort(pattern)

    paths: list[str] = []

    # Debug: List all files in workspace for troubleshooting
    log.debug("Workspace contents before pattern matching:")
    for root, _dirs, files in os.walk(workspace):
        for file in files:
            rel_path: str = os.path.relpath(os.path.join(root, file), workspace)
            log.debug("  %s", rel_path)

    # Use pathlib for more reliable pattern matching across Python versions
    workspace_path: Path = Path(workspace)

    for p in no_dups_pattern:
        if p == "":  # Skip empty patterns as they are invalid
            continue

        log.debug("Searching for pattern: %s", p)

        # Handle recursive patterns with pathlib.rglob() for better Python 3.8 compatibility
        found_paths: list[Path]
        if p.startswith("**/"):
            # Use rglob for recursive patterns like "**/*.txt"
            pattern_suffix: str = p[3:]  # Remove "**/" prefix
            found_paths = list(workspace_path.rglob(pattern_suffix))
            log.debug("Using rglob for pattern '%s' -> rglob('%s')", p, pattern_suffix)
        elif "**" in p:
            # For other recursive patterns, fall back to manual traversal with fnmatch
            found_paths = []
            for file_path in workspace_path.rglob("*"):
                if file_path.is_file():
                    relative_path: Path = file_path.relative_to(workspace_path)
                    if fnmatch.fnmatch(str(relative_path), p):
                        found_paths.append(file_path)
            log.debug("Using fnmatch for complex pattern '%s'", p)
        else:
            # For simple patterns without **, use glob
            found_paths = list(workspace_path.glob(p))
            log.debug("Using glob for simple pattern '%s'", p)

        # Convert to absolute string paths
        absolute_paths: list[str] = [str(path) for path in found_paths if path.is_file()]
        log.debug("Found files for pattern '%s': %s", p, absolute_paths)
        paths.extend(absolute_paths)

    log.debug("Files found: %s", paths)

    no_dups_paths: list[str] = _remove_duplicates_and_sort(paths)
    for src in no_dups_paths:
        if len(os.path.basename(src)) > 255:
            log.warning("Filename %s is over 255 characters. Skipping...", os.path.basename(src))

        dest: str = os.path.join(dest_dir, src[len(workspace) + 1 :])
        log.debug("%s -> %s", src, dest)

        if os.path.isfile(src):
            try:
                _ = shutil.move(src, dest)
            except OSError as e:  # Switch to FileNotFoundError when Python 2 support is dropped.
                log.debug("Missing path, will create it %s.\n%s", os.path.dirname(dest), e)
                os.makedirs(os.path.dirname(dest))
                _ = shutil.move(src, dest)
        else:
            log.info("Not copying directories: %s.", src)

    if os.environ.get("S3_BUCKET") is not None:
        now: datetime.datetime = datetime.datetime.now()
        p = now.strftime("_%d%m%Y_%H%M%S_")
        for dirpath, _dirnames, files in os.walk(dest_dir):
            if not files:
                fd, _tmp = tempfile.mkstemp(prefix=p, dir=dirpath)
                os.close(fd)
                log.debug("temp file created in dir: %s.", dirpath)


def deploy_archives(nexus_url: str, nexus_path: str, workspace: str, pattern: list[str] | None = None) -> None:
    """Archive files to a Nexus site repository named logs.

    Provides 2 ways to archive files:
        1) $WORKSPACE/archives directory provided by the user.
        2) globstar pattern provided by the user.

    Requirements:

    To use this API a Nexus server must have a site repository configured
    with the name "logs" as this is a hardcoded path.

    Parameters:

        :nexus_url: URL of Nexus server. Eg: https://nexus.opendaylight.org
        :nexus_path: Path on nexus logs repo to place the logs. Eg:
            $SILO/$JENKINS_HOSTNAME/$JOB_NAME/$BUILD_NUMBER
        :workspace: Directory in which to search, typically in Jenkins this is
            $WORKSPACE
        :pattern: Space-separated list of Globstar patterns of files to
            archive. (optional)
    """
    nexus_url = _format_url(nexus_url)
    previous_dir: str = os.getcwd()
    work_dir: str = tempfile.mkdtemp(prefix="lftools-da.")
    os.chdir(work_dir)
    log.debug("workspace: %s, work_dir: %s", workspace, work_dir)

    _copy_archives(workspace, pattern)
    _compress_text(work_dir)

    archives_zip: str = shutil.make_archive(f"{workspace}/archives", "zip")
    log.debug("archives zip: %s", archives_zip)
    deploy_nexus_zip(nexus_url, "logs", nexus_path, archives_zip)

    os.chdir(previous_dir)
    shutil.rmtree(work_dir)


def deploy_logs(nexus_url: str, nexus_path: str, build_url: str) -> None:
    """Deploy logs to a Nexus site repository named logs.

    Fetches logs and system information and pushes them to Nexus
    for log archiving.
    Requirements:

    To use this API a Nexus server must have a site repository configured
    with the name "logs" as this is a hardcoded path.

    Parameters:

        :nexus_url: URL of Nexus server. Eg: https://nexus.opendaylight.org
        :nexus_path: Path on nexus logs repo to place the logs. Eg:
            $SILO/$JENKINS_HOSTNAME/$JOB_NAME/$BUILD_NUMBER
        :build_url: URL of the Jenkins build. Jenkins typically provides this
                    via the $BUILD_URL environment variable.
    """
    nexus_url = _format_url(nexus_url)
    previous_dir: str = os.getcwd()
    work_dir: str = tempfile.mkdtemp(prefix="lftools-dl.")
    os.chdir(work_dir)
    log.debug("work_dir: %s", work_dir)

    _capture_build_logs(build_url)

    _compress_text(work_dir)

    console_zip = tempfile.NamedTemporaryFile(prefix="lftools-dl", delete=True)  # noqa: SIM115
    log.debug("console-zip: %s", console_zip.name)
    _ = shutil.make_archive(console_zip.name, "zip", work_dir)
    deploy_nexus_zip(nexus_url, "logs", nexus_path, f"{console_zip.name}.zip")
    console_zip.close()

    os.chdir(previous_dir)
    shutil.rmtree(work_dir)
