# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2018 The Linux Foundation
"""Small helpers shared by the release-to-Docker-Hub workflow."""

from __future__ import annotations

import logging

import requests

log = logging.getLogger(__name__)


def _remove_http_from_url(url: str) -> str:
    """Remove http[s]:// from url."""
    if url.startswith("https://"):
        return url[len("https://") :]
    if url.startswith("http://"):
        return url[len("http://") :]
    return url


def _format_image_id(id: str) -> str:
    """Remove sha256: from beginning of string."""
    if id.startswith("sha256:"):
        return id[len("sha256:") :]
    else:
        return id


def _request_get(url: str) -> requests.Response:
    """Execute a request get, return the resp."""
    try:
        resp = requests.get(url)
    except requests.exceptions.RequestException as excinfo:
        log.debug(f"in _request_get RequestException. {type(excinfo)}")
        raise requests.HTTPError(f"Issues with URL: {url} - {type(excinfo)}") from excinfo
    return resp


def repo_is_in_file(check_repo: str = "", repo_file_name: str = "") -> bool:
    """Function to verify of a repo name exists in a file name.

    The file contains rows of repo names to be included.
        acumos-portal-fe
        acumos/acumos-axure-client

    Function will return True if a match is found

    """
    with open(f"{repo_file_name}") as f:
        for line in f.readlines():
            row = line.rstrip()
            reponame = row.split(";")[0]
            log.debug(f"Comparing {check_repo} with {reponame} from file")
            if check_repo == reponame:
                log.debug("Found a match")
                return True
    log.debug("NO match found")
    return False


def get_docker_name_from_file(check_repo: str = "", repo_file_name: str = "") -> str:
    """Function to verify of a repo name exists in a file name.

    The file contains rows of repo names to be included.
        acumos-portal-fe
        acumos/acumos-axure-client

    Function will return True if a match is found

    """
    with open(f"{repo_file_name}") as f:
        for line in f.readlines():
            row = line.rstrip()
            reponame = row.split(";")[0]
            dockername = row.split(";")[1]
            log.debug(f"Comparing {check_repo} with {reponame} from file")
            if check_repo == reponame:
                log.debug("Found a match")
                return dockername
    log.debug("NO match found")
    return ""
