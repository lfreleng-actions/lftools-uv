# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Library of functions for deploying artifacts to Nexus."""

from __future__ import annotations

import concurrent.futures
import datetime
import errno
import fnmatch
import glob
import gzip
import logging
import math
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path
from typing import NoReturn

import boto3
import requests
from botocore.exceptions import ClientError
from defusedxml.minidom import parseString

log: logging.Logger = logging.getLogger(__name__)
logging.getLogger("botocore").setLevel(logging.CRITICAL)


def _compress_text(dir: str) -> None:
    """Compress all text files in directory."""
    save_dir: str = os.getcwd()
    os.chdir(dir)

    compress_types: list[str] = [
        "**/*.html",
        "**/*.log",
        "**/*.txt",
        "**/*.xml",
    ]
    paths: list[str] = []
    for _type in compress_types:
        search: str = os.path.join(dir, _type)
        paths.extend(glob.glob(search, recursive=True))

    for _file in paths:
        # glob may follow symlink paths that open can't find
        if os.path.exists(_file):
            log.debug("Compressing file %s", _file)
            with open(_file, "rb") as src, gzip.open(f"{_file}.gz", "wb") as dest:  # noqa: PTH123
                shutil.copyfileobj(src, dest)
                os.remove(_file)
        else:
            log.info(f"Could not open path from glob {_file}")

    os.chdir(save_dir)


def _format_url(url: str) -> str:
    """Ensure url starts with http and trim trailing '/'s."""
    start_pattern: re.Pattern[str] = re.compile("^(http|https)://")
    if not start_pattern.match(url):
        url = f"http://{url}"

    if url.endswith("/"):
        url = url.rstrip("/")

    return url


def _log_error_and_exit(*msg_list: object) -> NoReturn:
    """Print error message, and exit."""
    for msg in msg_list:
        log.error(msg)
    sys.exit(1)


def _request_post(url: str, data: str, headers: dict[str, str]) -> requests.Response:
    """Execute a request post, return the resp."""
    resp: requests.Response | None = None
    try:
        resp = requests.post(url, data=data, headers=headers, timeout=30)
    except requests.exceptions.MissingSchema:
        log.debug("in _request_post. MissingSchema")
        _log_error_and_exit(f"Not valid URL: {url}")
    except requests.exceptions.ConnectionError:
        log.debug("in _request_post. ConnectionError")
        _log_error_and_exit(f"Could not connect to URL: {url}")
    except requests.exceptions.InvalidURL:
        log.debug("in _request_post. InvalidURL")
        _log_error_and_exit(f"Invalid URL: {url}")
    assert resp is not None  # noqa: S101
    return resp


def _get_filenames_in_zipfile(_zipfile: str) -> list[str]:
    """Return a list with file names."""
    files: list[zipfile.ZipInfo] = zipfile.ZipFile(_zipfile).infolist()
    return [f.filename for f in files]


def _request_post_file(
    url: str,
    file_to_upload: str,
    parameters: dict[str, tuple[None, str]] | None = None,
) -> requests.Response:
    """Execute a request post, return the resp."""
    resp: requests.Response | None = None
    try:
        upload_file = open(file_to_upload, "rb")  # noqa: PTH123, SIM115
    except FileNotFoundError as err:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_to_upload) from err

    files: dict[str, object] = {"file": upload_file}
    try:
        if parameters:
            resp = requests.post(url, data=parameters, files=files, timeout=30)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        else:
            resp = requests.post(url, data=upload_file.read(), timeout=30)
    except requests.exceptions.MissingSchema as err:
        raise requests.HTTPError(f"Not valid URL: {url}") from err
    except requests.exceptions.ConnectionError as err:
        raise requests.HTTPError(f"Could not connect to URL: {url}") from err
    except requests.exceptions.InvalidURL as err:
        raise requests.HTTPError(f"Invalid URL: {url}") from err

    if resp.status_code == 400:
        raise requests.HTTPError("Repository is read only")
    elif resp.status_code == 404:
        raise requests.HTTPError("Did not find repository.")

    assert resp is not None  # noqa: S101
    if not str(resp.status_code).startswith("20"):
        raise requests.HTTPError(
            f"Failed to upload to Nexus with status code: {resp.status_code}.\n{resp.text}\n{file_to_upload}"
        )

    return resp


def _request_put_file(
    url: str,
    file_to_upload: str,
    parameters: dict[str, object] | None = None,
) -> bool:
    """Execute a request put, return the resp."""
    resp: requests.Response | None = None
    try:
        upload_file = open(file_to_upload, "rb")  # noqa: PTH123, SIM115
    except FileNotFoundError as err:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_to_upload) from err

    files: dict[str, object] = {"file": upload_file}
    try:
        if parameters:
            resp = requests.put(url, data=parameters, files=files, timeout=30)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        else:
            resp = requests.put(url, data=upload_file, timeout=30)
    except requests.exceptions.MissingSchema as err:
        raise requests.HTTPError(f"Not valid URL format. Check for https:// etc..: {url}") from err
    except requests.exceptions.ConnectTimeout as err:
        raise requests.HTTPError(f"Timed out connecting to {url}") from err
    except requests.exceptions.ReadTimeout as err:
        raise requests.HTTPError(f"Timed out waiting for the server to reply ({url})") from err
    except requests.exceptions.ConnectionError as err:
        raise requests.HTTPError(f"A connection error occurred ({url})") from err
    except requests.exceptions.InvalidURL as err:
        raise requests.HTTPError(f"Invalid URL format: {url}") from err
    except requests.RequestException as err:
        log.error(err)
        raise requests.HTTPError(f"Request error during PUT to {url}") from err

    assert resp is not None  # noqa: S101
    if resp.status_code == 201:
        return True
    if resp.status_code == 400:
        raise requests.HTTPError("Repository is read only")
    if resp.status_code == 401:
        raise requests.HTTPError("Invalid repository credentials")
    if resp.status_code == 404:
        raise requests.HTTPError("Did not find repository.")

    if not str(resp.status_code).startswith("20"):
        raise requests.HTTPError(
            f"Failed to upload to Nexus with status code: {resp.status_code}.\n{resp.text}\n{file_to_upload}"
        )
    return True


def _get_node_from_xml(xml_data: str, tag_name: str) -> str:
    """Extract tag data from xml data."""
    log.debug("xml=%s", xml_data)

    try:
        dom1 = parseString(xml_data)
        childnode = dom1.getElementsByTagName(tag_name)[0]
    except Exception:
        _log_error_and_exit(f"Received bad XML, can not find tag {tag_name}", xml_data)
    first_child = childnode.firstChild
    if first_child is None:
        _log_error_and_exit(f"Tag {tag_name} has no text content", xml_data)
    return str(first_child.nodeValue)


def _remove_duplicates_and_sort(lst: list[str]) -> list[str]:
    """Remove duplicates from list, and sort it."""
    no_dups_lst: list[str] = list(dict.fromkeys(lst))
    no_dups_lst.sort()

    duplicated_list: list[str] = []
    for i in range(len(no_dups_lst)):
        if lst.count(no_dups_lst[i]) > 1:
            duplicated_list.append(no_dups_lst[i])
    log.debug("duplicates  : %s", duplicated_list)

    return no_dups_lst


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

    # Create a temp file to handle empty dirs in AWS S3 buckets.
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

    copy_archives(workspace, pattern)
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

    build_details = open("_build-details.log", "w+")  # noqa: PTH123, SIM115
    _ = build_details.write(f"build-url: {build_url}")

    with open("_sys-info.log", "w+") as sysinfo_log:  # noqa: PTH123
        sys_cmds: list[list[str]] = []

        log.debug("Platform: %s", sys.platform)
        if sys.platform == "linux" or sys.platform == "linux2":
            sys_cmds = [
                ["uname", "-a"],
                ["lscpu"],
                ["nproc"],
                ["df", "-h"],
                ["free", "-m"],
                ["ip", "addr"],
                ["sar", "-b", "-r", "-n", "DEV"],
                ["sar", "-P", "ALL"],
            ]

        for c in sys_cmds:
            try:
                output: str = subprocess.check_output(c).decode("utf-8")  # noqa: S603
            except FileNotFoundError:
                log.debug("Command not found: %s", c)
                continue

            output = "---> {}:\n{}\n".format(" ".join(c), output)
            _ = sysinfo_log.write(output)
            log.info(output)

    build_details.close()

    # Magic string used to trim console logs at the appropriate level during wget
    MAGIC_STRING: str = "-----END_OF_BUILD-----"
    log.info(MAGIC_STRING)

    resp: requests.Response = requests.get(f"{_format_url(build_url)}/consoleText", timeout=30)
    with open("console.log", "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(str(resp.content.decode("utf-8").split(MAGIC_STRING)[0]))

    resp = requests.get(f"{_format_url(build_url)}/timestamps?time=HH:mm:ss&appendLog", timeout=30)
    with open("console-timestamp.log", "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(str(resp.content.decode("utf-8").split(MAGIC_STRING)[0]))

    _compress_text(work_dir)

    console_zip = tempfile.NamedTemporaryFile(prefix="lftools-dl", delete=True)  # noqa: SIM115
    log.debug("console-zip: %s", console_zip.name)
    _ = shutil.make_archive(console_zip.name, "zip", work_dir)
    deploy_nexus_zip(nexus_url, "logs", nexus_path, f"{console_zip.name}.zip")
    console_zip.close()

    os.chdir(previous_dir)
    shutil.rmtree(work_dir)


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

    def _upload_to_s3(file: str) -> bool:
        mime_type: str | None = mimetypes.guess_type(file)[0]
        mime_encoding: str | None = mimetypes.guess_type(file)[1]
        extra_args: dict[str, str | None] = {"ContentType": "text/plain"}
        text_html_extra_args: dict[str, str | None] = {"ContentType": "text/html", "ContentEncoding": mime_encoding}
        text_plain_extra_args: dict[str, str | None] = {"ContentType": "text/plain", "ContentEncoding": mime_encoding}
        app_xml_extra_args: dict[str, str | None] = {"ContentType": "application/xml", "ContentEncoding": mime_encoding}
        if file == "_tmpfile":
            for dir in (logs_dir, silo_dir, jenkins_node_dir):
                try:
                    s3.Bucket(s3_bucket).upload_file(file, f"{dir}{file}")
                except ClientError as e:
                    log.error(e)
                    return False
                return True
        if mime_type is None and mime_encoding is None:
            try:
                s3.Bucket(s3_bucket).upload_file(file, f"{s3_path}{file}", ExtraArgs=extra_args)
            except ClientError as e:
                log.error(e)
                return False
            return True
        elif mime_type is None or mime_type in "text/plain":
            extra_args = text_plain_extra_args
            try:
                s3.Bucket(s3_bucket).upload_file(file, f"{s3_path}{file}", ExtraArgs=extra_args)
            except ClientError as e:
                log.error(e)
                return False
            return True
        elif mime_type in "text/html":
            extra_args = text_html_extra_args
            try:
                s3.Bucket(s3_bucket).upload_file(file, f"{s3_path}{file}", ExtraArgs=extra_args)
            except ClientError as e:
                log.error(e)
                return False
            return True
        elif mime_type in "application/xml":
            extra_args = app_xml_extra_args
            try:
                s3.Bucket(s3_bucket).upload_file(file, f"{s3_path}{file}", ExtraArgs=extra_args)
            except ClientError as e:
                log.error(e)
                return False
            return True
        else:
            try:
                s3.Bucket(s3_bucket).upload_file(file, f"{s3_path}{file}", ExtraArgs=extra_args)
            except ClientError as e:
                log.error(e)
                return False
            return True

    previous_dir: str = os.getcwd()
    work_dir: str = tempfile.mkdtemp(prefix="lftools-dl.")
    os.chdir(work_dir)
    s3_bucket = s3_bucket.lower()
    s3 = boto3.resource("s3")
    logs_dir: str = s3_path.split("/")[0] + "/"
    silo_dir: str = s3_path.split("/")[1] + "/"
    jenkins_node_dir: str = logs_dir + silo_dir + s3_path.split("/")[2] + "/"

    log.debug("work_dir: %s", work_dir)

    # Copy archive files to tmp dir
    copy_archives(workspace, pattern)

    # Create build logs
    build_details = open("_build-details.log", "w+")  # noqa: PTH123, SIM115
    _ = build_details.write(f"build-url: {build_url}")

    with open("_sys-info.log", "w+") as sysinfo_log:  # noqa: PTH123
        sys_cmds: list[list[str]] = []

        log.debug("Platform: %s", sys.platform)
        if sys.platform == "linux" or sys.platform == "linux2":
            sys_cmds = [
                ["uname", "-a"],
                ["lscpu"],
                ["nproc"],
                ["df", "-h"],
                ["free", "-m"],
                ["ip", "addr"],
                ["sar", "-b", "-r", "-n", "DEV"],
                ["sar", "-P", "ALL"],
            ]

        for c in sys_cmds:
            try:
                output: str = subprocess.check_output(c).decode("utf-8")  # noqa: S603
            except FileNotFoundError:
                log.debug("Command not found: %s", c)
                continue

            output = "---> {}:\n{}\n".format(" ".join(c), output)
            _ = sysinfo_log.write(output)
            log.info(output)

    build_details.close()

    # Magic string used to trim console logs at the appropriate level during wget
    MAGIC_STRING: str = "-----END_OF_BUILD-----"
    log.info(MAGIC_STRING)

    resp: requests.Response = requests.get(f"{_format_url(build_url)}/consoleText", timeout=30)
    with open("console.log", "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(str(resp.content.decode("utf-8").split(MAGIC_STRING)[0]))

    resp = requests.get(f"{_format_url(build_url)}/timestamps?time=HH:mm:ss&appendLog", timeout=30)
    with open("console-timestamp.log", "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(str(resp.content.decode("utf-8").split(MAGIC_STRING)[0]))

    # Create _tmpfile
    """ Because s3 does not have a filesystem, this file is uploaded to generate/update the
        index.html file in the top level "directories". """
    open("_tmpfile", "a").close()  # noqa: PTH123, SIM115

    # Compress tmp directory
    _compress_text(work_dir)

    # Create file list to upload
    file_list: list[str] = []
    files: list[str] = glob.glob("**/*", recursive=True)
    for file in files:
        if os.path.isfile(file):
            file_list.append(file)

    log.info("#######################################################")
    log.info("Deploying files from %s to %s/%s", work_dir, s3_bucket, s3_path)

    # Perform s3 upload
    for file in file_list:
        log.info("Attempting to upload file %s", file)
        if _upload_to_s3(file):
            log.info("Successfully uploaded %s", file)
        else:
            log.error("FAILURE: Uploading %s failed", file)

    log.info("Finished deploying from %s to %s/%s", work_dir, s3_bucket, s3_path)
    log.info("#######################################################")

    # Cleanup
    s3.Object(s3_bucket, "{}{}".format(logs_dir, "_tmpfile")).delete()
    s3.Object(s3_bucket, "{}{}".format(silo_dir, "_tmpfile")).delete()
    s3.Object(s3_bucket, "{}{}".format(jenkins_node_dir, "_tmpfile")).delete()
    os.chdir(previous_dir)
    # shutil.rmtree(work_dir)


def deploy_nexus_zip(nexus_url: str, nexus_repo: str, nexus_path: str, zip_file: str) -> None:
    """"Deploy zip file containing artifacts to Nexus using requests.

    This function simply takes a zip file preformatted in the correct
    directory for Nexus and uploads to a specified Nexus repo using the
    content-compressed URL.

    Requires the Nexus Unpack plugin and permission assigned to the upload user.

    Parameters:

        nexus_url:    URL to Nexus server. (Ex: https://nexus.opendaylight.org)
        nexus_repo:   The repository to push to. (Ex: site)
        nexus_path:   The path to upload the artifacts to. Typically the
                      project group_id depending on if a Maven or Site repo
                      is being pushed.
                      Maven Ex: org/opendaylight/odlparent
                      Site Ex: org.opendaylight.odlparent
        zip_file:     The zip to deploy. (Ex: /tmp/artifacts.zip)

    Sample:
    lftools deploy nexus-zip \
        192.168.1.26:8081/nexus \
        snapshots \
        tst_path \
        tests/fixtures/deploy/zip-test-files/test.zip
    """
    url: str = f"{_format_url(nexus_url)}/service/local/repositories/{nexus_repo}/content-compressed/{nexus_path}"
    log.debug("Uploading %s to %s", zip_file, url)

    try:
        resp: requests.Response = _request_post_file(url, zip_file)
    except requests.HTTPError as e:
        files_in_zip: list[str] = _get_filenames_in_zipfile(zip_file)
        log.info("Uploading %s failed. It contained the following files", zip_file)
        for f in files_in_zip:
            log.info("   %s", f)
        raise requests.HTTPError(e) from e
    log.debug("%s: %s", resp.status_code, resp.text)


def nexus_stage_repo_create(nexus_url: str, staging_profile_id: str) -> str:
    """Create a Nexus staging repo.

    Parameters:
    nexus_url:           URL to Nexus server. (Ex: https://nexus.example.org)
    staging_profile_id:  The staging profile id as defined in Nexus for the
                         staging repo.

    Returns:             staging_repo_id

    Sample:
    lftools deploy nexus-stage-repo-create 192.168.1.26:8081/nexus/ 93fb68073c18
    """
    nexus_url = f"{_format_url(nexus_url)}/service/local/staging/profiles/{staging_profile_id}/start"

    log.debug("Nexus URL           = %s", nexus_url)

    xml: str = """
        <promoteRequest>
            <data>
                <description>Create staging repository.</description>
            </data>
        </promoteRequest>
    """

    headers: dict[str, str] = {"Content-Type": "application/xml"}
    resp: requests.Response = _request_post(nexus_url, xml, headers)

    log.debug("resp.status_code = %s", resp.status_code)
    log.debug("resp.text = %s", resp.text)

    if re.search("nexus-error", resp.text):
        error_msg: str = _get_node_from_xml(resp.text, "msg")
        if re.search(".*profile with id:.*does not exist.", error_msg):
            _log_error_and_exit(f"Staging profile id {staging_profile_id} not found.")
        _log_error_and_exit(error_msg)

    if resp.status_code == 405:
        _log_error_and_exit("HTTP method POST is not supported by this URL", nexus_url)
    if resp.status_code == 404:
        _log_error_and_exit(f"Did not find nexus site: {nexus_url}")
    if not resp.status_code == 201:
        _log_error_and_exit(f"Failed with status code {resp.status_code}", resp.text)

    staging_repo_id: str = _get_node_from_xml(resp.text, "stagedRepositoryId")
    log.debug("staging_repo_id = %s", staging_repo_id)

    return staging_repo_id


def nexus_stage_repo_close(nexus_url: str, staging_profile_id: str, staging_repo_id: str) -> None:
    """Close a Nexus staging repo.

    Parameters:
    nexus_url:          URL to Nexus server. (Ex: https://nexus.example.org)
    staging_profile_id: The staging profile id as defined in Nexus for the
                        staging repo.
    staging_repo_id:    The ID of the repo to close.

    Sample:
    lftools deploy nexus-stage-repo-close 192.168.1.26:8081/nexsus/ 93fb68073c18 test1-1031
    """
    nexus_url = f"{_format_url(nexus_url)}/service/local/staging/profiles/{staging_profile_id}/finish"

    log.debug("Nexus URL           = %s", nexus_url)
    log.debug("staging_repo_id     = %s", staging_repo_id)

    xml: str = f"""
        <promoteRequest>
            <data>
                <stagedRepositoryId>{staging_repo_id}</stagedRepositoryId>
                <description>Close staging repository.</description>
            </data>
        </promoteRequest>
    """

    headers: dict[str, str] = {"Content-Type": "application/xml"}
    resp: requests.Response = _request_post(nexus_url, xml, headers)

    log.debug("resp.status_code = %s", resp.status_code)
    log.debug("resp.text = %s", resp.text)

    error_msg: str
    if re.search("nexus-error", resp.text):
        error_msg = _get_node_from_xml(resp.text, "msg")
    else:
        error_msg = resp.text

    if resp.status_code == 404:
        _log_error_and_exit(f"Did not find nexus site: {nexus_url}")

    if re.search("invalid state: closed", error_msg):
        _log_error_and_exit("Staging repository is already closed.")
    if re.search("Missing staging repository:", error_msg):
        _log_error_and_exit("Staging repository do not exist.")

    if not resp.status_code == 201:
        _log_error_and_exit(f"Failed with status code {resp.status_code}", resp.text)


def upload_maven_file_to_nexus(
    nexus_url: str,
    nexus_repo_id: str,
    group_id: str,
    artifact_id: str,
    version: str,
    packaging: str,
    file: str,
    classifier: str | None = None,
) -> None:
    """Upload file to Nexus as a Maven artifact.

    This function will upload an artifact to Nexus while providing all of
    the usual Maven pom.xml information so that it conforms to Maven 2 repo
    specs.

    Parameters:
         nexus_url:     The URL to the Nexus repo.
                        (Ex:  https://nexus.example.org)
         nexus_repo_id: Repo ID of repo to push artifact to.
         group_id:      Maven style Group ID to upload artifact as.
         artifact_id:   Maven style Artifact ID to upload artifact as.
         version:       Maven style Version to upload artifact as.
         packaging:     Packaging type to upload as (Eg. tar.xz)
         file:          File to upload.
         classifier:    Maven classifier. (optional)

    Sample:
        lftools deploy nexus \
            http://192.168.1.26:8081/nexus/content/repositories/releases \
            tests/fixtures/deploy/zip-test-files
    """
    url: str = f"{_format_url(nexus_url)}/service/local/artifact/maven/content"

    log.info("Uploading URL: %s", url)
    params: dict[str, tuple[None, str]] = {}
    params.update({"r": (None, f"{nexus_repo_id}")})
    params.update({"g": (None, f"{group_id}")})
    params.update({"a": (None, f"{artifact_id}")})
    params.update({"v": (None, f"{version}")})
    params.update({"p": (None, f"{packaging}")})
    if classifier:
        params.update({"c": (None, f"{classifier}")})

    log.debug("Maven Parameters: %s", params)

    resp: requests.Response = _request_post_file(url, file, params)

    if re.search("nexus-error", resp.text):
        nexus_error_msg: str = _get_node_from_xml(resp.text, "msg")
        raise requests.HTTPError(f"Nexus Error: {nexus_error_msg}") from None


def deploy_nexus(nexus_repo_url: str, deploy_dir: str, snapshot: bool = False, workers: int = 2) -> None:
    """Deploy a local directory of files to a Nexus repository.

    One purpose of this is so that we can get around the problematic
    deploy-at-end configuration with upstream Maven.
    https://issues.apache.org/jira/browse/MDEPLOY-193

    This function ignores these files:

        - _remote.repositories
        - resolver-status.properties
        - maven-metadata.xml*  (if not a snapshot repo)

    Parameters:
        nexus_repo_url: URL to Nexus repository to upload to.
                        (Ex: https://nexus.example.org/content/repositories/releases)
        deploy_dir:     The directory to deploy. (Ex: /tmp/m2repo)

    Sample:
        lftools deploy nexus \
            http://192.168.1.26:8081/nexus/content/repositories/releases \
            tests/fixtures/deploy/zip-test-files
    """

    def _get_filesize(file: str) -> str:
        bytesize: int = os.path.getsize(file)
        if bytesize == 0:
            return "0B"
        suffix: tuple[str, ...] = ("b", "kb", "mb", "gb")
        i: int = int(math.floor(math.log(bytesize, 1024)))
        p: float = math.pow(1024, i)
        s: float = round(bytesize / p, 2)
        return f"{s} {suffix[i]}"

    def _deploy_nexus_upload(file: str) -> bool:
        # Fix file path, and call _request_put_file.
        nexus_url_with_file: str = f"{_format_url(nexus_repo_url)}/{file}"
        log.info("Attempting to upload %s (%s)", file, _get_filesize(file))
        if _request_put_file(nexus_url_with_file, file):
            return True
        else:
            return False

    file_list: list[str] = []
    previous_dir: str = os.getcwd()
    os.chdir(deploy_dir)
    files: list[str] = glob.glob("**/*", recursive=True)
    for file in files:
        if os.path.isfile(file):
            base_name: str = os.path.basename(file)

            # Skip blacklisted files
            if base_name == "_remote.repositories" or base_name == "resolver-status.properties":
                continue

            if not snapshot:
                if base_name.startswith("maven-metadata.xml"):
                    continue

            file_list.append(file)

    log.info("#######################################################")
    log.info("Deploying directory %s to %s", deploy_dir, nexus_repo_url)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        # this creates a dict where the key is the Future object, and the value is the file name
        # see concurrent.futures.Future for more info
        futures: dict[concurrent.futures.Future[bool], str] = {
            executor.submit(_deploy_nexus_upload, file_name): file_name for file_name in file_list
        }
        for future in concurrent.futures.as_completed(futures):
            filename: str = futures[future]
            try:
                _ = future.result()
            except Exception as e:
                log.error("Uploading %s: %s", filename, e)

        # wait until all threads complete (successfully or not)
        # then log the results of the upload threads
        _ = concurrent.futures.wait(futures)
        for k, v in futures.items():
            if k.result():
                log.info("Successfully uploaded %s", v)
            else:
                log.error("FAILURE: Uploading %s failed", v)

    log.info("Finished deploying %s to %s", deploy_dir, nexus_repo_url)
    log.info("#######################################################")

    os.chdir(previous_dir)


def deploy_nexus_stage(nexus_url: str, staging_profile_id: str, deploy_dir: str) -> None:
    """Deploy Maven artifacts to Nexus staging repo.

    Parameters:
    nexus_url:          URL to Nexus server. (Ex: https://nexus.example.org)
    staging_profile_id: The staging profile id as defined in Nexus for the
                        staging repo.
    deploy_dir:         The directory to deploy. (Ex: /tmp/m2repo)

    # Sample:
        lftools deploy nexus-stage http://192.168.1.26:8081/nexus 4e6f95cd2344 /tmp/slask
            Deploying Maven artifacts to staging repo...
            Staging repository aaf-1005 created.
            /tmp/slask ~/LF/work/lftools-dev/lftools/shell
            Uploading fstab
            Uploading passwd
            ~/LF/work/lftools-dev/lftools/shell
            Completed uploading files to aaf-1005.
    """
    staging_repo_id: str = nexus_stage_repo_create(nexus_url, staging_profile_id)
    log.info("Staging repository %s created.", staging_repo_id)

    deploy_nexus_url: str = f"{_format_url(nexus_url)}/service/local/staging/deployByRepositoryId/{staging_repo_id}"

    sz_m2repo: int = sum(os.path.getsize(f) for f in os.listdir(deploy_dir) if os.path.isfile(f))
    log.debug("Staging repository upload size: %s bytes", sz_m2repo)

    log.debug("Nexus Staging URL: %s", _format_url(deploy_nexus_url))
    deploy_nexus(deploy_nexus_url, deploy_dir)

    nexus_stage_repo_close(nexus_url, staging_profile_id, staging_repo_id)
    log.info("Completed uploading files to %s.", staging_repo_id)
