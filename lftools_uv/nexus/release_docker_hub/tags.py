# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2018 The Linux Foundation
"""Tag collections for a repository on Nexus3 and on Docker Hub."""

from __future__ import annotations

import json
import logging
import re
import time

import requests

from lftools_uv.nexus.release_docker_hub import settings
from lftools_uv.nexus.release_docker_hub.util import _request_get

log = logging.getLogger(__name__)


class TagClass:
    """Base class for Nexus3 and Docker Hub tag class.

    This class contains the actual valid and invalid tags for a repository,
    as well as an indication if the repository exist or not.

    A valid tag has the following format #.#.# (1.2.3, or 1.22.333)

    Parameter:
        org_name  : The organization part of the repository. (onap)
        repo_name : The Nexus3 repository name (aaf/aaf_service)
        repo_from_file : Repository name was taken from input file.
    """

    def __init__(self, org_name: str, repo_name: str, repo_from_file: bool) -> None:
        """Initialize this class."""
        self.valid: list[str] = []
        self.invalid: list[str] = []
        self.repository_exist: bool = True
        self.org: str = org_name
        self.repo: str = repo_name
        self.repofromfile: bool = repo_from_file

    def _validate_tag(self, check_tag: str) -> re.Match[str] | None:
        r"""Local helper function to simplify validity check of version number.

        Returns true or false, depending if the version pattern is a valid one.
        Valid pattern is #.#.#, or in computer term "^\d+.\d+.\d+$"

        Future pattern : x.y.z-KEYWORD-yyyymmddThhmmssZ
          where keyword = STAGING or SNAPSHOT
          '^\d+.\d+.\d+-(STAGING|SNAPSHOT)-(20\d{2})(\d{2})(\d{2})T([01]\d|2[0-3])([0-5]\d)([0-5]\d)Z$'
        """
        pattern = re.compile(rf"{settings.version_regexp}")
        log.debug(f"validate tag {check_tag} in {self.repo} --> {pattern.match(check_tag)}")
        return pattern.match(check_tag)

    def add_tag(self, new_tag: str) -> None:
        """Add tag to a list.

        This function will take a tag, and add it to the correct list
        (valid or invalid), depending on validate_tag result.
        """
        if self._validate_tag(new_tag):
            self.valid.append(new_tag)
        else:
            self.invalid.append(new_tag)


class NexusTagClass(TagClass):
    """Nexus Tag class.

    This class fetches and stores all Nexus3 tags for a repository.

    Doing this manually from command line, you will give this command:
        curl -s https://nexus3.onap.org:10002/v2/onap/aaf/aaf_service/tags/list
    which gives you the following output:
        {"name":"onap/aaf/aaf_service","tags":["2.1.1","2.1.3","2.1.4","2.1.5","2.1.6","2.1.7","2.1.8"]}
    # https://nexus3.edgexfoundry.org/repository/docker.staging/v2/docker-device-rest-go/tags/list
    # https://nexus3.edgexfoundry.org:10002/v2/docker-device-rest-go/tags/list

    When we fetch the tags from the Nexus3 repository url, they are returned like
        {"name":"onap/aaf/aaf_service","tags":["2.1.1","2.1.3","2.1.4","2.1.5"]}
    Hence, we need to extract all the tags, and add them to our list of valid or
    invalid tags.
    If we fail to collect the tags, we set the repository_exist flag to false.

    Parameter:
        org_name  : The organization part of the repository. (onap)
        repo_name : The Nexus3 repository name (aaf/aaf_service)
        repo_from_file : The reponame came from an input file.

    Result:
        Will fetch all tags from the Nexus3 repository URL, and store each tag
        in self.valid or self.invalid as a list.
        If no repository is found, self.repository_exist will be set to False.
    """

    repository_exist: bool

    def __init__(self, org_name: str, repo_name: str, repo_from_file: bool) -> None:
        """Initialize this class."""
        TagClass.__init__(self, org_name, repo_name, repo_from_file)
        retries = 0
        # Default to <org>/<repo>
        org_repo_name = f"{org_name}/{repo_name}"
        if repo_from_file:
            org_repo_name = f"{repo_name}"
        log.debug(f"Fetching nexus3 tags for {org_repo_name}")
        r = None
        while retries < 20:
            try:
                r = _request_get(settings.nexus3_base + "/v2/" + org_repo_name + "/tags/list")
                break
            except requests.HTTPError as excinfo:
                log.debug(f"Fetching Nexus3 tags. {excinfo}")
                retries = retries + 1
                if retries > 19:
                    self.repository_exist = False
                    return

        if r is None:
            self.repository_exist = False
            return

        log.debug(f"r.status_code = {r.status_code}, ok={r.status_code == requests.codes.ok}")
        if r.status_code == requests.codes.ok:
            raw_tags = r.text
            raw_tags = raw_tags.replace('"', "")
            raw_tags = raw_tags.replace("}", "")
            raw_tags = raw_tags.replace("]", "")
            raw_tags = raw_tags.replace(" ", "")
            split_tags = raw_tags.split("[")
            TmpSplittedTags = split_tags[1].split(",")
            if len(TmpSplittedTags) > 0:
                for tag_2_add in TmpSplittedTags:
                    self.add_tag(tag_2_add)
                    log.debug(f"Nexus {org_repo_name} has tag {tag_2_add}")
        else:
            self.repository_exist = False


class DockerTagClass(TagClass):
    """Docker tag class.

    This class fetches and stores all docker tags for a repository.

    Doing this manually from command line, you will give this command:
        curl -s https://registry.hub.docker.com:443/v2/namespaces/onap/repositories/base_sdc-sanity/tags
    which gives you a json output. Just looking for the tag names we do this
        curl -s https://registry.hub.docker.com:443/v2/namespaces/onap/repositories/base_sdc-sanity/tags | \
                jq -r ".results[].name"
            latest
            1.7.0
            1.6.0
            1.4.1
            1.4.0
            1.3.1
            1.3.0
            v1.0.0

    Hence, we need to extract all the tags, and add them to our list of valid or
    invalid tags.
    If we fail to collect the tags, we set the repository_exist flag to false.

    Parameter:
        org_name  : The organization part of the repository. (onap)
        repo_name : The Docker Hub repository name (aaf-aaf_service)
        repo_from_file : The reponame came from an input file.

    Result:
        Will fetch all tags from the Docker Repository URL, and store each tag
        in self.valid or self.invalid as a list.
        If no repository is found, self.repository_exist will be set to False.
    """

    _docker_base_start: str = "https://registry.hub.docker.com/v2/namespaces/"
    repository_exist: bool

    def __init__(self, org_name: str, repo_name: str, repo_from_file: bool) -> None:
        """Initialize this class."""
        TagClass.__init__(self, org_name, repo_name, repo_from_file)
        if repo_from_file:
            combined_repo_name = repo_name
        else:
            combined_repo_name = f"{org_name}/{repo_name}"
        log.debug(f"Fetching docker tags for {combined_repo_name}")
        _docker_base = self._docker_base_start + f"{org_name}/repositories"
        still_more = True
        docker_tag_url = _docker_base + "/" + repo_name + "/tags"
        while still_more:
            raw_json = None
            retries = 0
            r = None
            while retries < 20:
                try:
                    log.debug(f"URL={docker_tag_url}")
                    r = _request_get(docker_tag_url)
                    if r.status_code == 429:
                        # Docker returns 429 if we access it too fast too many times.
                        # If it happens, delay 60 seconds, and try again, up to 19 times.
                        log.debug(f"Too many docker gets too fast, wait 1 min: {retries}, repo {combined_repo_name}")
                        time.sleep(60)
                        retries = retries + 1
                    else:
                        break
                except requests.HTTPError as excinfo:
                    log.debug(f"Fetching Docker Hub tags. {excinfo}")
                    retries = retries + 1
                    if retries > 19:
                        self.repository_exist = False
                        return

            if r is None:
                self.repository_exist = False
                return

            log.debug(f"r.status_code = {r.status_code}, ok={r.status_code == requests.codes.ok}")
            if r.status_code == 429:
                # Speed throttling in effect. Cancel program
                raise requests.HTTPError(f"Dockerhub throttling at tag fetching.\n {r.text}")
            if r.status_code == requests.codes.ok:
                raw_json = json.loads(r.text)

                try:
                    for result in raw_json["results"]:
                        tag_name = result["name"]
                        self.add_tag(tag_name)
                        log.debug(f"Docker {combined_repo_name} has tag {tag_name}")

                    if raw_json["next"]:
                        docker_tag_url = raw_json["next"]
                        still_more = True
                    else:
                        still_more = False
                except Exception as exc:
                    # Leaving still_more and docker_tag_url unchanged here would
                    # re-fetch the same page forever, re-adding tags each time.
                    log.error("Malformed tag response for %s: %s", combined_repo_name, exc)
                    raise requests.HTTPError(
                        f"Malformed tag response from Docker Hub for {combined_repo_name}"
                    ) from exc
            else:
                self.repository_exist = False
                return
