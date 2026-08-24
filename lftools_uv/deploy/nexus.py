# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Deploy artifacts to Nexus repositories and staging repositories."""

from __future__ import annotations

import concurrent.futures
import glob
import math
import os
import re

import requests

from lftools_uv.deploy._common import _BANNER_HASHES, _CONTENT_TYPE_XML, log
from lftools_uv.deploy._http import _request_post, _request_post_file, _request_put_file
from lftools_uv.deploy._late import _fail
from lftools_uv.deploy._util import _format_url, _get_filenames_in_zipfile, _get_node_from_xml


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

    headers: dict[str, str] = {"Content-Type": _CONTENT_TYPE_XML}
    resp: requests.Response = _request_post(nexus_url, xml, headers)

    log.debug("resp.status_code = %s", resp.status_code)
    log.debug("resp.text = %s", resp.text)

    if re.search("nexus-error", resp.text):
        error_msg: str = _get_node_from_xml(resp.text, "msg")
        if re.search(".*profile with id:.*does not exist.", error_msg):
            _fail(f"Staging profile id {staging_profile_id} not found.")
        _fail(error_msg)

    if resp.status_code == 405:
        _fail("HTTP method POST is not supported by this URL", nexus_url)
    if resp.status_code == 404:
        _fail(f"Did not find nexus site: {nexus_url}")
    if not resp.status_code == 201:
        _fail(f"Failed with status code {resp.status_code}", resp.text)

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

    headers: dict[str, str] = {"Content-Type": _CONTENT_TYPE_XML}
    resp: requests.Response = _request_post(nexus_url, xml, headers)

    log.debug("resp.status_code = %s", resp.status_code)
    log.debug("resp.text = %s", resp.text)

    error_msg: str
    if re.search("nexus-error", resp.text):
        error_msg = _get_node_from_xml(resp.text, "msg")
    else:
        error_msg = resp.text

    if resp.status_code == 404:
        _fail(f"Did not find nexus site: {nexus_url}")

    if re.search("invalid state: closed", error_msg):
        _fail("Staging repository is already closed.")
    if re.search("Missing staging repository:", error_msg):
        _fail("Staging repository do not exist.")

    if not resp.status_code == 201:
        _fail(f"Failed with status code {resp.status_code}", resp.text)


# aislop-ignore-next-line too-many-params -- these are the Maven GAV coordinates plus the Nexus target
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

    def _deploy_nexus_upload(file: str) -> None:
        # Fix file path, and call _request_put_file.
        nexus_url_with_file: str = f"{_format_url(nexus_repo_url)}/{file}"
        log.info("Attempting to upload %s (%s)", file, _get_filesize(file))
        _request_put_file(nexus_url_with_file, file)

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

    log.info(_BANNER_HASHES)
    log.info("Deploying directory %s to %s", deploy_dir, nexus_repo_url)

    failed_uploads: list[tuple[str, str]] = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        # this creates a dict where the key is the Future object, and the value is the file name
        # see concurrent.futures.Future for more info
        futures: dict[concurrent.futures.Future[None], str] = {
            executor.submit(_deploy_nexus_upload, file_name): file_name for file_name in file_list
        }
        for future in concurrent.futures.as_completed(futures):
            filename: str = futures[future]
            try:
                future.result()
            except Exception as e:
                log.error("FAILURE: Uploading %s failed: %s", filename, e)
                failed_uploads.append((filename, str(e)))
            else:
                log.info("Successfully uploaded %s", filename)

    if failed_uploads:
        log.error(
            "Completed deploying %s to %s with %d failure(s)",
            deploy_dir,
            nexus_repo_url,
            len(failed_uploads),
        )
    else:
        log.info("Finished deploying %s to %s", deploy_dir, nexus_repo_url)
    log.info(_BANNER_HASHES)

    os.chdir(previous_dir)

    if failed_uploads:
        # Surface a single aggregated failure to callers (CLI front-ends rely
        # on a raised exception to exit non-zero). Per-file errors are
        # already logged above.
        summary: str = "; ".join(f"{name}: {err}" for name, err in failed_uploads)
        raise requests.HTTPError(
            f"Failed to upload {len(failed_uploads)} of {len(file_list)} file(s) to {nexus_repo_url}: {summary}"
        )


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
