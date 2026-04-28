# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Script to insert missing values from ldap into a projects INFO.yaml."""

from __future__ import annotations

import datetime
import inspect
import logging
import re
import sys
from typing import Any, cast

import click
import ruamel.yaml
import yaml
from pygerrit2 import GerritRestAPI, HTTPBasicAuth
from ruamel.yaml.comments import CommentedMap

from lftools_uv import config
from lftools_uv.cli.errors import error_handler
from lftools_uv.github_helper import prvotes
from lftools_uv.ldap_cli import helper_yaml4info

log = logging.getLogger(__name__)


@click.group()
@click.pass_context
def infofile(ctx):
    """INFO.yaml TOOLS."""
    pass


@click.command(name="create-info-file")
@click.argument("gerrit_url", required=True)
@click.argument("gerrit_project", required=True)
@click.option("--directory", type=str, required=False, default="r", help="custom gerrit directory, eg not /r/")
@click.option("--empty", is_flag=True, required=False, help="Create info file for uncreated project.")
@click.option(
    "--tsc_approval", type=str, required=False, default="missing", help="optionally provide a tsc approval link"
)
@click.pass_context
@error_handler
def create_info_file(ctx, gerrit_url, gerrit_project, directory, empty, tsc_approval):
    """Create an initial INFO file.

    gerrit_project example: project/full-name
    gerrit_url example: gerrit.umbrella.com
    directory example: /gerrit/ (rather than most projects /r/)
    """
    url = f"https://{gerrit_url}/{directory}"
    projectid_encoded = gerrit_project.replace("/", "%2F")
    # project name with only underscores for info file anchors.
    # project name with only dashes for ldap groups.
    project_underscored = gerrit_project.replace("/", "_")
    project_underscored = project_underscored.replace("-", "_")
    project_dashed = project_underscored.replace("_", "-")

    umbrella = gerrit_url.split(".")[1]
    match = re.search(r"(?<=\.).*", gerrit_url)
    if match is None:
        log.error("Could not parse TLD from gerrit_url: %s", gerrit_url)
        sys.exit(1)
    umbrella_tld = match.group(0)

    if not empty:
        user = config.get_setting("gerrit", "username")
        pass1 = config.get_setting("gerrit", "password")
        auth = HTTPBasicAuth(user, pass1)
        rest = GerritRestAPI(url=url, auth=auth)
        access_str = f"projects/{projectid_encoded}/access"
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        result: dict[str, Any] = cast(dict[str, Any], rest.get(access_str, headers=headers))

        if "inherits_from" in result:
            inherits = result["inherits_from"]["id"]
            if inherits != "All-Projects":
                log.info("    Inherits from: %s", inherits)
                log.warning("Better Check this unconventional inherit")

        try:
            owner = result["local"]["refs/*"]["permissions"]["owner"]["rules"]
        except Exception:
            log.error("ERROR: Check project config, no owner set!")
            owner = {}

        for x in owner:
            match = re.search(r"[^=]+(?=,)", x)
            if match is not None:
                ldap_group = match.group(0)

    if umbrella == "o-ran-sc":
        umbrella = "oran"
    if umbrella == "opendaylight":
        umbrella = "odl"

    date = datetime.datetime.now().strftime("%Y-%m-%d")

    ldap_group = f"{umbrella}-gerrit-{project_dashed}-committers"

    long_string = f"""---
project: '{project_underscored}'
project_creation_date: '{date}'
project_category: ''
lifecycle_state: 'Incubation'
project_lead: &{umbrella}_{project_underscored}_ptl
    name: ''
    email: ''
    id: ''
    company: ''
    timezone: ''
primary_contact: *{umbrella}_{project_underscored}_ptl
issue_tracking:
    type: 'jira'
    url: 'https://jira.{umbrella_tld}/projects/'
    key: '{project_underscored}'
mailing_list:
    type: 'groups.io'
    url: 'technical-discuss@lists.{umbrella_tld}'
    tag: '[]'
realtime_discussion:
    type: 'irc'
    server: 'freenode.net'
    channel: '#{umbrella}'
meetings:
    - type: 'gotomeeting+irc'
      agenda: 'https://wiki.{umbrella_tld}/display/'
      url: ''
      server: 'freenode.net'
      channel: '#{umbrella}'
      repeats: ''
      time: ''"""

    tsc_string = f"""
tsc:
    # yamllint disable rule:line-length
    approval: '{tsc_approval}'
    changes:
        - type: ''
          name: ''
          link: ''
"""
    empty_committer = """    - name: ''
      email: ''
      company: ''
      id: ''
"""
    tsc_string = inspect.cleandoc(tsc_string)
    log.info(long_string)
    log.info("repositories:")
    log.info("    - %s", gerrit_project)
    log.info("committers:")
    log.info("    - <<: *%s_%s_ptl", umbrella, project_underscored)
    if not empty:
        this = helper_yaml4info(ldap_group)
        # This already contains formatted YAML; log without additional formatting
        for line in this.splitlines():
            log.info(line)
    else:
        for line in empty_committer.splitlines():
            log.info(line)
    for line in tsc_string.splitlines():
        log.info(line)


@click.command(name="get-committers")
@click.argument("file", envvar="FILE_NAME", required=True)
@click.option("--full", is_flag=True, help="Output name email and id for all committers in an infofile")
@click.option("--id", type=str, required=False, help="Full output for a specific LFID")
@click.pass_context
@error_handler
def get_committers(ctx, file, full, id):
    """Extract Committer info from INFO.yaml or LDAP dump."""
    with open(file) as yaml_file:
        project = yaml.safe_load(yaml_file)

    def log_committer_info(committer, full):
        """Log committers."""
        if full:
            log.info("    - name: %s", committer.get("name", ""))
            log.info("      email: %s", committer.get("email", ""))
        log.info("      id: %s", committer.get("id", ""))

    def list_committers(full, id, project):
        """List committers from the INFO.yaml file."""
        lookup = project.get("committers", [])
        for item in lookup:
            if id:
                if item.get("id") == id:
                    log_committer_info(item, full)
                    break
                else:
                    continue
            log_committer_info(item, full)

    list_committers(full, id, project)


@click.command(name="sync-committers")
@click.argument("info_file")
@click.argument("ldap_file")
@click.argument("id")
@click.option("--repo", type=str, required=False, help="repo name")
@click.pass_context
@error_handler
def sync_committers(ctx, id, info_file, ldap_file, repo):
    """Sync committer information from LDAP into INFO.yaml."""
    ryaml = ruamel.yaml.YAML()
    ryaml.preserve_quotes = True
    ryaml.indent(mapping=4, sequence=6, offset=4)
    ryaml.explicit_start = True
    with open(info_file) as stream:
        try:
            yaml.safe_load(stream)
        except yaml.YAMLError as exc:
            log.error(exc)

    with open(info_file) as f:
        info_data = ryaml.load(f)
    with open(ldap_file) as f:
        ldap_data = ryaml.load(f)

    def readfile(data, ldap_data, id):
        committer_info = info_data["committers"]
        repo_info = info_data["repositories"]
        committer_info_ldap = ldap_data["committers"]
        readldap(id, ldap_file, committer_info, committer_info_ldap, repo, repo_info)

    def readldap(id, ldap_file, committer_info, committer_info_ldap, repo, repo_info):
        for idx, _ in enumerate(committer_info):
            committer = info_data["committers"][idx]["id"]
            if committer == id:
                log.info(f"{id} is already in {info_file}")
                sys.exit(0)

        name = email = formatid = company = timezone = None
        for idx, _ in enumerate(committer_info_ldap):
            committer = ldap_data["committers"][idx]["id"]
            if committer == id:
                name = ldap_data["committers"][idx].get("name")
                email = ldap_data["committers"][idx].get("email")
                formatid = ldap_data["committers"][idx].get("id")
                company = ldap_data["committers"][idx].get("company")
                timezone = ldap_data["committers"][idx].get("timezone")
        if name is None:
            log.error(f"{id} does not exist in {ldap_file}")
            sys.exit(1)

        user = CommentedMap(
            (("name", name), ("company", company), ("email", email), ("id", formatid), ("timezone", timezone))
        )

        info_data["repositories"][0] = repo
        committer_info.append(user)

        with open(info_file, "w") as f:
            ryaml.dump(info_data, f)
        log.info(f"Updated {info_file} with committer {id}")

    readfile(info_data, ldap_data, id)


@click.command(name="check-votes")
@click.argument("info_file")
@click.argument("endpoint", type=str)
@click.argument("change_number", type=int)
@click.option("--tsc", type=str, required=False, help="path to TSC INFO file")
@click.option("--github_repo", type=str, required=False, help="Provide github repo to Check against a Github Change")
@click.pass_context
@error_handler
def check_votes(ctx, info_file, endpoint, change_number, tsc, github_repo):
    """Check votes on an INFO.yaml change.

    Check for Majority of votes on a gerrit or github patchset
    which changes an INFO.yaml file.

    For Gerrit endpoint is the gerrit url
    For Github the endpoint is the organization name

    Examples:
    lftools infofile check-votes /tmp/test/INFO.yaml lfit-sandbox 18 --github_repo test

    lftools infofile check-votes ~/lf/allrepos/onosfw/INFO.yaml https://gerrit.opnfv.org/gerrit/ 67302

    """

    def main(ctx, info_file, endpoint, change_number, tsc, github_repo, majority_of_committers):
        """Function so we can iterate into TSC members after committer vote has happened."""
        info_data: dict[str, Any] = {}
        with open(info_file) as file:
            try:
                info_data = yaml.safe_load(file)
            except yaml.YAMLError as exc:
                log.error(exc)
                sys.exit(1)

        committer_info = info_data["committers"]
        info_committers = []

        info_change = []

        if github_repo:
            id = "github_id"
            githubvotes = prvotes(endpoint, github_repo, change_number)
            for vote in githubvotes:
                info_change.append(vote)

        else:
            id = "id"
            rest = GerritRestAPI(url=endpoint)
            changes: list[dict[str, Any]] = cast(list[dict[str, Any]], rest.get(f"changes/{change_number}/reviewers"))
            for change in changes:
                line = (change["username"], change["approvals"]["Code-Review"])
                if "+1" in line[1] or "+2" in line[1]:
                    info_change.append(change["username"])

        for count, _ in enumerate(committer_info):
            committer = committer_info[count][id]
            info_committers.append(committer)

        have_not_voted = [item for item in info_committers if item not in info_change]
        have_not_voted_length = len(have_not_voted)
        have_voted = [item for item in info_committers if item in info_change]
        have_voted_length = len(have_voted)
        log.info("Number of Committers: %d", len(info_committers))
        committer_length = len(info_committers)
        log.info("Committers that have voted: %s (%d)", have_voted, have_voted_length)
        log.info("Committers that have not voted: %s (%d)", have_not_voted, have_not_voted_length)

        if have_voted_length == 0:
            log.warning("No one has voted.")
            sys.exit(1)

        majority = have_voted_length / committer_length if committer_length else 0
        if majority >= 0.5:
            log.info("Majority committer vote reached")
            if tsc:
                log.info("Need majority of TSC")
                info_file = tsc
                majority_of_committers += 1
                if majority_of_committers == 2:
                    log.info("TSC majority reached - auto merging commit")
                else:
                    main(ctx, info_file, endpoint, change_number, tsc, github_repo, majority_of_committers)
        else:
            log.info("Majority not yet reached")
            sys.exit(1)

    majority_of_committers = 0
    main(ctx, info_file, endpoint, change_number, tsc, github_repo, majority_of_committers)


infofile.add_command(get_committers)
infofile.add_command(sync_committers)
infofile.add_command(check_votes)
infofile.add_command(create_info_file)
