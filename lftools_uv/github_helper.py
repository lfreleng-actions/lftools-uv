# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Github stub."""

from __future__ import annotations

import logging
import sys
from typing import TYPE_CHECKING

# aislop-ignore-file hallucinated-import -- the declared PyGithub dependency provides the `github` import package
from github import Github, GithubException
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Team import Team

from lftools_uv import config
from lftools_uv.output import echo

if TYPE_CHECKING:
    from github.PaginatedList import PaginatedList

_YAML_LIST_ITEM_FMT = "  - '%s'"


log: logging.Logger = logging.getLogger(__name__)


def _get_org(g: Github, organization: str) -> Organization:
    """Get a GitHub organization, exiting on failure."""
    try:
        return g.get_organization(organization)
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)


def _get_token(organization: str) -> str:
    """Retrieve the GitHub token for an organization."""
    if config.has_section("github"):
        return config.get_setting("github", "token")
    section: str = f"github.{organization}"
    return config.get_setting(section, "token")


# aislop-ignore-next-line too-many-params -- mirrors the option set of the `github` commands
def helper_list(  # noqa: C901, PLR0912
    _ctx: object,
    organization: str,
    repos: bool,
    audit: bool,
    full: bool,
    teams: bool,
    team: str | None,
    repofeatures: bool,
) -> list[str] | None:
    """List options for github org repos."""
    token: str = _get_token(organization)
    g: Github = Github(token)
    org: Organization = _get_org(g, organization)

    # Extend this to check if a repo exists
    if repos:
        echo(f"All repos for organization:  {organization}")
        all_repos = org.get_repos()
        for repo in all_repos:
            echo(repo.name)

    if audit:
        echo(f"{organization} members without 2fa:")
        try:
            members: PaginatedList[NamedUser] = org.get_members(filter_="2fa_disabled")
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)
        for member in members:
            echo(member.login)
        echo(f"{organization} outside collaborators without 2fa:")
        try:
            collaborators: PaginatedList[NamedUser] = org.get_outside_collaborators(filter_="2fa_disabled")
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)
        for collaborator in collaborators:
            echo(collaborator.login)

    if repofeatures:
        feat_repos = org.get_repos()
        for repo in feat_repos:
            echo(f"{repo.name} wiki:{repo.has_wiki} issues:{repo.has_issues}")
            issues = repo.get_issues
            for issue in issues():
                echo(issue)

    if full:
        echo("---")
        echo(f"#  All owners for {organization}:")
        echo(f"{organization}-owners:")

        try:
            admin_members: PaginatedList[NamedUser] = org.get_members(role="admin")
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)
        for member in admin_members:
            echo(_YAML_LIST_ITEM_FMT % member.login)
        echo(f"#  All members for {organization}")
        echo(f"{organization}-members:")

        try:
            all_members: PaginatedList[NamedUser] = org.get_members()
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)
        for member in all_members:
            echo(_YAML_LIST_ITEM_FMT % member.login)
        echo(f"#  All members and all teams for {organization}")

        try:
            get_teams_fn = org.get_teams
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)
        for org_team in get_teams_fn():
            echo(f"{org_team.name}:")
            for user in org_team.get_members():
                echo(_YAML_LIST_ITEM_FMT % user.login)
            echo()

    if teams:
        try:
            get_teams_fn2 = org.get_teams
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)
        for org_team in get_teams_fn2():
            echo(org_team.name)

    if team:
        try:
            get_teams_fn3 = org.get_teams
        except GithubException as ghe:
            log.error(ghe)
            sys.exit(1)

        team_members: list[str] = []

        for t in get_teams_fn3():
            if t.name == team:
                echo(t.name)
                for user in t.get_members():
                    team_members.append(user.login)
                    echo(_YAML_LIST_ITEM_FMT % user.login)

        return team_members

    return None


def prvotes(organization: str, repo: str, pr: int) -> list[str]:
    """Get votes on a github pr."""
    token: str = config.get_setting("github", "token")
    g: Github = Github(token)
    org: Organization = _get_org(g, organization)

    gh_repo = org.get_repo(repo)
    approval_list: list[str] = []
    author: str = gh_repo.get_pull(pr).user.login
    approval_list.append(author)

    pr_mergable = gh_repo.get_pull(pr).mergeable
    echo(f"MERGEABLE: {pr_mergable}")

    approvals = gh_repo.get_pull(pr).get_reviews()
    for approve in approvals:
        if approve.state == "APPROVED":
            approval_list.append(approve.user.login)
    return approval_list


# aislop-ignore-next-line too-many-params -- mirrors the option set of the `github` commands
def helper_user_github(  # noqa: C901, PLR0912
    _ctx: object,
    organization: str,
    user: str,
    team: str,
    delete: bool,
    admin: bool,
) -> None:
    """Add and Remove users from an org team.

    Removal covers accepted memberships only. A user holding an unaccepted
    invitation is reported but left in place, because revoking a pending
    invitation is not implemented.
    """
    token: str = config.get_setting("github", "token")
    g: Github = Github(token)
    org: Organization = _get_org(g, organization)

    try:
        user_raw = g.get_user(user)
        # Avoid logging user object which may contain PII
        log.debug("User object retrieved successfully")
    except GithubException as ghe:
        log.error(ghe)
        echo("User not found")
        sys.exit(1)

    if not isinstance(user_raw, NamedUser):
        log.error("Expected NamedUser but got AuthenticatedUser")
        sys.exit(1)
    user_object: NamedUser = user_raw

    # check if user is a member
    is_member: bool = False
    try:
        is_member = org.has_in_members(user_object)
        echo(f"User membership status: {is_member}")
    except GithubException as ghe:
        log.error(ghe)

    try:
        get_teams_fn = org.get_teams
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)

    # set team to proper object
    my_teams: list[str] = [team]
    this_team: list[Team] = [t for t in get_teams_fn() if t.name in my_teams]
    team_id: int = 0
    for t in this_team:
        team_id = t.id
    team_obj: Team = org.get_team(team_id)
    team_list: list[Team] = [team_obj]

    if delete:
        if is_member:
            try:
                team_obj.remove_membership(user_object)
            except GithubException as ghe:
                log.error(ghe)
            echo("Removing user from team")
        else:
            echo("User is not a member of org, cannot delete")
            log.info("Code does not handle revoking invitations.")

    if user and not delete:
        if admin and is_member:
            try:
                team_obj.add_membership(member=user_object, role="maintainer")
            except GithubException as ghe:
                log.error(ghe)
        if admin and not is_member:
            try:
                org.invite_user(
                    user=user_object,
                    role="admin",
                    teams=team_list,
                )
            except GithubException as ghe:
                log.error(ghe)
            echo("Sending Admin invite to user for team")

        if not admin and is_member:
            try:
                team_obj.add_membership(member=user_object, role="member")
            except GithubException as ghe:
                log.error(ghe)

        if not admin and not is_member:
            try:
                org.invite_user(
                    user=user_object,
                    teams=team_list,
                )
            except GithubException as ghe:
                log.error(ghe)
            echo("Sending invite to user for team")
