# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2018 The Linux Foundation
"""Set of functions to facilitate copying nexus3 release images to docker hub.

Workflow if you do it manually

    sudo docker login       ---> DOCKER Credentials
    sudo docker login nexus3.onap.org:10002 -u <yourLFID>

    TAB1 https://nexus3.onap.org/#browse/search=repository_name%3Ddocker.release
    TAB2 https://hub.docker.com/r/onap

    docker pull nexus3.onap.org:10002/onap/aaf/aaf_hello:2.1.3
    docker images --> imageid --> 991170554e6e
    docker tag 991170554e6e onap/aaf-aaf_hello:2.1.3
    docker push onap/aaf-aaf_hello:2.1.3
    docker image rm --force 991170554e6e

Filter
Find all projects that starts with org and contains repo (if specified).

Set the repo to "" to find all projects that starts with org

Set the repo to a str to find all projects that contains that string
  and starts with org
    repo = "aaf_co"   # onap/aaf/aaf_config,onap/aaf/aaf_core
    repo = "aaf_cm"   # onap/aaf/aaf_cm
    repo = "aa"
    repo = ""         # Find all projects

lftools nexus docker releasedockerhub
"""

from __future__ import annotations

import logging
import multiprocessing
from multiprocessing.dummy import Pool as ThreadPool

import docker
import docker.errors
import docker.models.images
import requests
import tqdm

from lftools_uv.nexus.release_docker_hub import settings
from lftools_uv.nexus.release_docker_hub.project import ProjectClass
from lftools_uv.nexus.release_docker_hub.settings import (
    DEFAULT_REGEXP,
    initialize,
    validate_regexp,
    which_version_regexp_to_use,
)
from lftools_uv.nexus.release_docker_hub.tags import (
    DockerTagClass,
    NexusTagClass,
    TagClass,
)
from lftools_uv.nexus.release_docker_hub.util import (
    _format_image_id,
    _remove_http_from_url,
    _request_get,
    get_docker_name_from_file,
    repo_is_in_file,
)
from lftools_uv.output import echo

log = logging.getLogger(__name__)

NexusCatalog: list[list[str]] = []
projects: list[ProjectClass] = []
project_max_len_chars: int = 0


def get_nexus3_catalog(
    org_name: str = "", find_pattern: str = "", exact_match: bool = False, repo_is_filename: bool = False
) -> bool:
    """Main function to collect all Nexus3 repositories.

    This function will collect the Nexus catalog for all projects starting with
    'org_name' as well as containing a pattern if specified.
    If exact_match is specified, it will use the pattern as a unique repo name within the org_name.

    If you do it manually, you give the following command.
        curl -s https://nexus3.onap.org:10002/v2/_catalog

    which gives you the following output.
        {"repositories":["dcae_dmaapbc","onap/aaf/aaf-base-openssl_1.1.0",
        "onap/aaf/aaf-base-xenial","onap/aaf/aaf_agent","onap/aaf/aaf_cass",
        "onap/aaf/aaf_cm","onap/aaf/aaf_config","onap/aaf/aaf_core"]}

    Nexus3 catalog starts with <org_name>/<repo name>

    Parameters:
        org_name        : Organizational name, for instance 'onap'
        find_pattern    : A pattern, that if specified, needs to be part of the
                          repository name.
                          for instance,
                           ''     : this pattern finds all repositories.
                           'eleo' : this pattern finds all repositories with 'eleo'
                                    in its name. --> chameleon
        exact_match     : If specified, find_pattern is a unique repo name
        repo_is_filename: If specified, find_pattern is a filename, which contains a repo name per row
                            org_name is irrelevant in this case

    """
    global NexusCatalog
    global project_max_len_chars

    project_max_len_chars = 0
    containing_str = ""
    if len(find_pattern) > 0:
        containing_str = f', and containing "{find_pattern}"'
    if exact_match:
        containing_str = f', and reponame = "{find_pattern}"'
    if repo_is_filename:
        containing_str = f', and repos are found in "{find_pattern}"'
    info_str = f"Collecting information from Nexus from projects with org = {org_name}"
    log.info(f"{info_str}{containing_str}.")

    try:
        r = _request_get(settings.nexus3_catalog)
    except requests.HTTPError as excinfo:
        log.info(f"Fetching Nexus3 catalog. {excinfo}")
        return False

    log.debug(f"r.status_code = {r.status_code}, ok={r.status_code == requests.codes.ok}")
    if r.status_code == requests.codes.ok:
        raw_catalog = r.text
        raw_catalog = raw_catalog.replace('"', "")
        raw_catalog = raw_catalog.replace(" ", "")
        raw_catalog = raw_catalog.replace("}", "")
        raw_catalog = raw_catalog.replace("[", "")
        raw_catalog = raw_catalog.replace("]", "")
        split_catalog = raw_catalog.split(":")
        TmpCatalog = split_catalog[1].split(",")
        for word in TmpCatalog:
            use_this_repo = False
            project: list[str] = []
            if repo_is_filename and repo_is_in_file(word, find_pattern):
                use_this_repo = True
                project = [org_name, word, get_docker_name_from_file(word, find_pattern)]
            else:
                if word.startswith(org_name):
                    # Remove org_name/ from word, so we only get repository left
                    project = [org_name, word[len(org_name) + 1 :], ""]
                    # If a specific search string has been specified, search for it
                    # Empty string will match all words
                    if word.find(find_pattern) >= 0 and not exact_match:
                        use_this_repo = True
                    if exact_match and project[1] == find_pattern:
                        use_this_repo = True
            if use_this_repo:
                NexusCatalog.append(project)
                log.debug(f"Added project {project[1]} to my list")
                if len(project[1]) > project_max_len_chars:
                    project_max_len_chars = len(project[1])
        log.debug(
            f"# TmpCatalog {len(TmpCatalog)}, NexusCatalog {len(NexusCatalog)}, DIFF = {len(TmpCatalog) - len(NexusCatalog)}"
        )
    return True


def fetch_all_tags(progbar: bool = False, docker_client: docker.DockerClient | None = None) -> None:
    """Fetch all tags function.

    This function will use multi-threading to fetch all tags for all projects in
    Nexus3 Catalog.
    """
    NbrProjects = len(NexusCatalog)
    log.info(
        f"Fetching tags from Nexus3 and Docker Hub for {NbrProjects} projects with version regexp >>{settings.version_regexp}<<"
    )
    pbar = None
    if progbar:
        pbar = tqdm.tqdm(total=NbrProjects, bar_format="{l_bar}{bar}|{n_fmt}/{total_fmt} [{elapsed}]")

    def _fetch_all_tags(proj: list[str]) -> None:
        """Helper function for multi-threading.

        This function, will create an instance of ProjectClass (which triggers
        the project class fetching all Nexus3/Docker Hub tags)
        Then adding this instance to the project list.

            Parameters:
                proj : Tuple with 'org' and 'repo'
                    ('onap', 'aaf/aaf_service')
        """
        new_proj = ProjectClass(proj, docker_client)
        projects.append(new_proj)
        if pbar is not None:
            pbar.update(1)

    pool = ThreadPool(multiprocessing.cpu_count())
    pool.map(_fetch_all_tags, NexusCatalog)
    pool.close()
    pool.join()

    if pbar is not None:
        pbar.close()
    projects.sort()


def copy_from_nexus_to_docker(progbar: bool = False) -> None:
    """Copy all missing tags.

    This function will use multi-threading to copy all missing tags in the project list.
    """
    _tot_tags = 0
    for proj in projects:
        _tot_tags = _tot_tags + len(proj.tags_2_copy.valid)
    log.info(f"About to start copying from Nexus3 to Docker Hub for {_tot_tags} missing tags")
    pbar = None
    if progbar:
        pbar = tqdm.tqdm(total=_tot_tags, bar_format="{l_bar}{bar}|{n_fmt}/{total_fmt} [{elapsed}]")

    def _docker_pull_tag_push(proj: ProjectClass) -> None:
        """Helper function for multi-threading.

        This function, will call the ProjectClass proj's docker_pull_tag_push.

            Parameters:
                proj : Tuple with 'org' and 'repo'
                    ('onap', 'aaf/aaf_service')
        """
        proj.docker_pull_tag_push(progbar)
        if pbar is not None:
            pbar.update(len(proj.tags_2_copy.valid))

    pool = ThreadPool(multiprocessing.cpu_count())
    pool.map(_docker_pull_tag_push, projects)
    pool.close()
    pool.join()
    if pbar is not None:
        pbar.close()


def print_nexus_docker_proj_names() -> None:
    """Print Nexus3 - Docker Hub repositories."""
    fmt_str = "{:<" + str(project_max_len_chars) + "} : "
    echo()
    log_str = fmt_str.format(settings.nexus3_proj_name_header)
    log_str = f"{log_str}{settings.docker_proj_name_header}"
    echo(log_str)
    echo("-" * project_max_len_chars * 2)
    docker_i = 0
    for proj in projects:
        log_str = fmt_str.format(proj.nexus_repo_name)
        log_str = f"{log_str}{proj.docker_repo_name}"
        echo(log_str)
        docker_i = docker_i + 1
    echo()


def print_tags_header(header_str: str, col_1_str: str) -> None:
    """Print simple header."""
    fmt_str = "{:<" + str(project_max_len_chars) + "} : "
    echo(header_str)
    log_str = fmt_str.format(col_1_str)
    log_str = "{}{}".format(log_str, "Tags")
    echo(log_str)
    echo("-" * project_max_len_chars * 2)


def print_tags_data(proj_name: str, tags: list[str]) -> None:
    """Print tag data."""
    fmt_str = "{:<" + str(project_max_len_chars) + "} : "
    if len(tags) > 0:
        log_str = fmt_str.format(proj_name)
        tag_i = 0
        for tag in tags:
            if tag_i > 0:
                log_str = f"{log_str}, "
            log_str = f"{log_str}{tag}"
            tag_i = tag_i + 1
        echo(log_str)


def print_nexus_valid_tags() -> None:
    """Print Nexus valid tags."""
    print_tags_header("Nexus Valid Tags", settings.nexus3_proj_name_header)
    for proj in projects:
        print_tags_data(proj.nexus_repo_name, proj.nexus_tags.valid)
    echo()


def print_nexus_invalid_tags() -> None:
    """Print Nexus invalid tags."""
    print_tags_header("Nexus InValid Tags", settings.nexus3_proj_name_header)
    for proj in projects:
        print_tags_data(proj.nexus_repo_name, proj.nexus_tags.invalid)
    echo()


def print_docker_valid_tags() -> None:
    """Print Docker valid tags."""
    print_tags_header("Docker Valid Tags", settings.docker_proj_name_header)
    for proj in projects:
        print_tags_data(proj.docker_repo_name, proj.docker_tags.valid)
    echo()


def print_docker_invalid_tags() -> None:
    """Print Docker invalid tags."""
    print_tags_header("Docker InValid Tags", settings.docker_proj_name_header)
    for proj in projects:
        print_tags_data(proj.docker_repo_name, proj.docker_tags.invalid)
    echo()


def print_stats() -> None:
    """Print simple repo/tag statistics."""
    print_tags_header("Tag statistics (V=Valid, I=InValid)", settings.nexus3_proj_name_header)
    fmt_str = "{:<" + str(project_max_len_chars) + "} : "
    for proj in projects:
        echo(
            f"{fmt_str.format(proj.nexus_repo_name)}Nexus V:{len(proj.nexus_tags.valid)} I:{len(proj.nexus_tags.invalid)} -- Docker V:{len(proj.docker_tags.valid)} I:{len(proj.docker_tags.invalid)}"
        )
    echo()


def print_missing_docker_proj() -> None:
    """Print missing docker repos."""
    echo("Missing corresponding Docker Project")
    fmt_str = "{:<" + str(project_max_len_chars) + "} : "
    log_str = fmt_str.format(settings.nexus3_proj_name_header)
    log_str = f"{log_str}{settings.docker_proj_name_header}"
    echo(log_str)
    echo("-" * project_max_len_chars * 2)
    all_docker_repos_found = True
    for proj in projects:
        if not proj.docker_tags.repository_exist:
            log_str = fmt_str.format(proj.nexus_repo_name)
            log_str = f"{log_str}{proj.docker_repo_name}"
            echo(log_str)
            all_docker_repos_found = False
    if all_docker_repos_found:
        echo("All Docker Hub repos found.")
    echo()


def print_nexus_tags_to_copy() -> None:
    """Print tags that needs to be copied."""
    echo("Nexus project tags to copy to docker")
    fmt_str = "{:<" + str(project_max_len_chars) + "} : "
    log_str = fmt_str.format(settings.nexus3_proj_name_header)
    log_str = "{}{}".format(log_str, "Tags to copy")
    echo(log_str)
    echo("-" * project_max_len_chars * 2)
    for proj in projects:
        if len(proj.tags_2_copy.valid) > 0:
            log_str = ""
            tag_i = 0
            log_str = fmt_str.format(proj.nexus_repo_name)
            for tag in proj.tags_2_copy.valid:
                if tag_i > 0:
                    log_str = f"{log_str}, "
                log_str = f"{log_str}{tag}"
                tag_i = tag_i + 1
            echo(log_str)
    echo()


def print_nbr_tags_to_copy() -> None:
    """Print how many tags that needs to be copied."""
    _tot_tags = 0
    for proj in projects:
        _tot_tags = _tot_tags + len(proj.tags_2_copy.valid)
    echo(f"Summary: {_tot_tags} tags that should be copied from Nexus3 to Docker Hub.")


def start_point(
    org_name: str,
    find_pattern: str = "",
    exact_match: bool = False,
    summary: bool = False,
    verbose: bool = False,
    copy: bool = False,
    progbar: bool = False,
    repofile: bool = False,
    version_regexp: str = "",
    docker_client: docker.DockerClient | None = None,
) -> None:
    """Main function."""
    # Verify find_pattern and specified_repo are not both used.
    if len(find_pattern) == 0 and exact_match:
        log.error("You need to provide a Pattern to go with the --exact flag")
        return
    initialize(org_name, version_regexp)
    if not validate_regexp():
        log.error(f"Found issues with the provided regexp >>{settings.version_regexp}<< ")
        return
    if not get_nexus3_catalog(org_name, find_pattern, exact_match, repofile):
        log.info(f"Could not get any catalog from Nexus3 with org = {org_name}")
        return

    fetch_all_tags(progbar, docker_client)
    if verbose:
        print_nexus_docker_proj_names()
        print_nexus_valid_tags()
        print_nexus_invalid_tags()
        print_docker_valid_tags()
        print_docker_invalid_tags()
        print_stats()
    if summary or verbose:
        print_missing_docker_proj()
        print_nexus_tags_to_copy()
    if copy:
        copy_from_nexus_to_docker(progbar)
    else:
        print_nbr_tags_to_copy()


__all__ = [
    "DEFAULT_REGEXP",
    "DockerTagClass",
    "NexusTagClass",
    "ProjectClass",
    "TagClass",
    "_format_image_id",
    "_remove_http_from_url",
    "_request_get",
    "copy_from_nexus_to_docker",
    "fetch_all_tags",
    "get_docker_name_from_file",
    "get_nexus3_catalog",
    "initialize",
    "repo_is_in_file",
    "settings",
    "start_point",
    "validate_regexp",
    "which_version_regexp_to_use",
]
