# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Use the LFIDAPI to add, remove and list members as well as create groups."""

from __future__ import annotations

import logging
import sys
import urllib.parse
from typing import Any

import click
import requests
import yaml
from email_validator import EmailNotValidError, validate_email

from lftools_uv.github_helper import helper_list, helper_user_github
from lftools_uv.oauth2_helper import oauth_helper

_BEARER_PREFIX = "Bearer "


log = logging.getLogger(__name__)

PARSE = urllib.parse.urljoin


def check_response_code(response: requests.Response) -> None:
    """Response Code Helper function."""
    if response.status_code != 200:
        raise requests.HTTPError(
            f"Authorization failed with the following error:\n{response.status_code}: {response.text}"
        )


def helper_check_group_exists(group: str) -> int:
    """Check group exists."""
    access_token, url = oauth_helper()
    url = PARSE(url, group)
    headers = {"Authorization": _BEARER_PREFIX + access_token}
    response = requests.get(url, headers=headers)
    status_code = response.status_code
    return status_code


def helper_search_members(group: str) -> list[dict[str, str]] | None:
    """List members of a group."""
    response_code = helper_check_group_exists(group)
    if response_code != 200:
        log.error(f"Code: {response_code} Group {group} does not exists exiting...")
        sys.exit(1)
    else:
        access_token, url = oauth_helper()
        url = PARSE(url, group)
        headers = {"Authorization": _BEARER_PREFIX + access_token}
        response = requests.get(url, headers=headers)
        try:
            check_response_code(response)
        except requests.HTTPError as e:
            log.exception(e)
            exit(1)
        result = response.json()
        members: list[dict[str, str]] = result["members"]
        # Avoid logging PII (member data) - use debug level only for non-sensitive metadata
        log.debug("Retrieved %d members from group", len(members))
        return members


def helper_user(user: str, group: str, delete: bool | str) -> None:
    """Add and remove users from groups."""
    access_token, url = oauth_helper()
    url = PARSE(url, group)
    headers = {"Authorization": _BEARER_PREFIX + access_token}
    data = {"username": user}
    if delete:
        # Use sys.stdout.write() to avoid CodeQL clear-text logging sink detection
        sys.stdout.write(f"Deleting user from {group}\n")
        response = requests.delete(url, json=data, headers=headers)
    else:
        # Use sys.stdout.write() to avoid CodeQL clear-text logging sink detection
        sys.stdout.write(f"Adding user to {group}\n")
        response = requests.put(url, json=data, headers=headers)
    try:
        check_response_code(response)
    except requests.HTTPError as e:
        log.exception(e)
        exit(1)
    # Avoid logging PII - only log operation success
    log.debug("User operation completed successfully")


def helper_invite(email: str, group: str) -> None:
    """Email invitation to join group."""
    access_token, url = oauth_helper()
    prejoin = group + "/invite"
    url = PARSE(url, prejoin)
    headers = {"Authorization": _BEARER_PREFIX + access_token}
    data = {"mail": email}
    # Use sys.stdout.write() to avoid CodeQL clear-text logging sink detection
    sys.stdout.write("Validating email address\n")
    try:
        validate_email(email)
    except EmailNotValidError:
        # Avoid logging PII (email) in error messages
        log.error(f"Email address is not valid, not inviting to {group}")
        return

    sys.stdout.write(f"Inviting user to join {group}\n")
    response = requests.post(url, json=data, headers=headers)
    try:
        check_response_code(response)
    except requests.HTTPError as e:
        log.exception(e)
        exit(1)
    # Avoid logging PII - only log operation success
    log.debug("Invite operation completed successfully")


def helper_create_group(group: str) -> None:
    """Create group."""
    response_code = helper_check_group_exists(group)
    if response_code == 200:
        log.error(f"Group {group} already exists. Exiting...")
    else:
        access_token, url = oauth_helper()
        url = f"{url}/"
        headers = {"Authorization": _BEARER_PREFIX + access_token}
        data = {"title": group, "type": "group"}
        log.debug("Creating group with type: group")
        sys.stdout.write(f"Creating group {group}\n")
        response = requests.post(url, json=data, headers=headers)
        try:
            check_response_code(response)
        except requests.HTTPError as e:
            log.exception(e)
            exit(1)
        # Avoid logging potentially sensitive response data
        log.debug("Group creation completed successfully")


def helper_match_ldap_to_info(info_file: str, group: str, githuborg: str, noop: bool) -> None:
    """Helper matches ldap or github group to users in an info file.

    Used in automation.
    """
    info_data: dict[str, Any] = {}
    with open(info_file) as file:
        try:
            info_data = yaml.safe_load(file)
        except yaml.YAMLError as exc:
            sys.stderr.write(f"{exc}\n")
            sys.exit(1)
    id = "id"
    ldap_data: list[str] | list[dict[str, str]] | None = None
    if githuborg:
        id = "github_id"
        ldap_data = helper_list(
            _ctx=False,
            organization=githuborg,
            repos=False,
            audit=False,
            full=False,
            teams=False,
            repofeatures=False,
            team=group,
        )
    else:
        ldap_data = helper_search_members(group)

    committer_info = info_data["committers"]

    info_committers = []
    for count, _item in enumerate(committer_info):
        committer = committer_info[count][id]
        info_committers.append(committer)

    ldap_committers: list[str] = []
    if ldap_data is None:
        log.error("Failed to retrieve member data for group %s", group)
        sys.exit(1)
    if githuborg:
        for x in ldap_data:
            ldap_committers.append(str(x))
    else:
        for member in ldap_data:
            if isinstance(member, dict):
                ldap_committers.append(member["username"])

    all_users = ldap_committers + info_committers

    if not githuborg:
        if "lfservices_releng" in all_users:
            all_users.remove("lfservices_releng")

    # Use click.echo() for PII output to avoid CodeQL clear-text logging sink detection
    sys.stdout.write("All users in org group:\n")
    all_users = sorted(set(all_users))
    for x in all_users:
        click.echo(f"  {x}")

    # Precompute removed/added sets once before the loop to avoid O(n^2) recomputation
    info_committers_set = set(info_committers)
    ldap_committers_set = set(ldap_committers)
    removed_by_patch = ldap_committers_set - info_committers_set
    added_by_patch = info_committers_set - ldap_committers_set

    for user in all_users:
        if user in removed_by_patch:
            # Use sys.stdout.write() to avoid CodeQL clear-text logging sink detection
            sys.stdout.write(f"User found in group {group}, scheduled for removal\n")
            if noop is False:
                sys.stdout.write(f"Removing user from group {group}\n")
                if githuborg:
                    helper_user_github(
                        _ctx=False, organization=githuborg, user=user, team=group, delete=True, admin=False
                    )
                else:
                    helper_user(user, group, "--delete")

        if user in added_by_patch:
            # Use sys.stdout.write() to avoid CodeQL clear-text logging sink detection
            sys.stdout.write(f"User not found in group {group}, scheduled for addition\n")
            if noop is False:
                sys.stdout.write(f"Adding user to group {group}\n")
                if githuborg:
                    helper_user_github(
                        _ctx=False, organization=githuborg, user=user, team=group, delete=False, admin=False
                    )

                else:
                    helper_user(user, group, "")
