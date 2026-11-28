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
from configparser import NoOptionError, NoSectionError
from typing import TYPE_CHECKING

# aislop-ignore-file hallucinated-import -- the declared PyGithub dependency provides the `github` import package
from github import Github, GithubException, UnknownObjectException
from github.NamedUser import NamedUser
from github.Organization import Organization
from github.Repository import Repository
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


def get_token(organization: str) -> str:
    """Return the GitHub token for an organization, exiting when none is set.

    The ``token`` of ``[github.<organization>]`` wins; the ``token`` of
    ``[github]`` is the fallback. Every ``github`` command, in both
    front-ends, looks its token up here.
    """
    sections: tuple[str, str] = (f"github.{organization}", "github")
    for section in sections:
        try:
            token: str = config.get_setting(section, "token")
        except (NoSectionError, NoOptionError):
            continue
        if token:
            return token
    log.error(
        "No GitHub token: set token in [%s] or [%s] in %s",
        sections[0],
        sections[1],
        config.LFTOOLS_CONFIG_FILE,
    )
    sys.exit(1)


def connect(organization: str, client: type[Github]) -> Organization:
    """Return a GitHub organization through ``client``, exiting on failure.

    Each front-end passes the ``Github`` class it imported.
    """
    return _get_org(client(get_token(organization)), organization)


def _find_team(org: Organization, team: str) -> Team | None:
    """Return the organization's team with ``team`` as its name or slug.

    Returns None only when no team has that name and the slug lookup
    answers 404; any other API error exits 1.
    """
    try:
        for org_team in org.get_teams():
            if org_team.name == team:
                return org_team
        try:
            return org.get_team_by_slug(team)
        except UnknownObjectException:
            return None
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)


def resolve_repo_teams(
    org: Organization, add_team: str | None, remove_team: str | None
) -> tuple[Team | None, Team | None]:
    """Return the teams to add and to remove, each named by name or slug.

    Changes nothing; exits 1 when either team is unknown, so a caller
    resolves the teams before it edits the repository.
    """
    add = _find_team(org, add_team) if add_team else None
    remove = _find_team(org, remove_team) if remove_team else None
    unmatched = sorted(name for name, team in ((add_team, add), (remove_team, remove)) if name and team is None)
    if unmatched:
        log.error("team not found: %s", ", ".join(unmatched))
        sys.exit(1)
    return add, remove


def apply_repo_teams(repo: Repository, add: Team | None, remove: Team | None) -> None:
    """Add a team to a repository with ``push``, and remove one from it."""
    try:
        if add is not None:
            log.info("Adding team %s", add.id)
            add.add_to_repos(repo)
            add.update_team_repository(repo, "push")
        if remove is not None:
            log.info("Removing team %s", remove.id)
            remove.remove_from_repos(repo)
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)


# aislop-ignore-next-line too-many-params -- mirrors the option set of the `create-repo` commands
def create_repo(
    org: Organization,
    repository: str,
    description: str,
    has_issues: bool,
    has_projects: bool,
    has_wiki: bool,
) -> None:
    """Create a public, empty repository, exiting 1 when it already exists."""
    log.info("Creating repo under organization: %s", org.login)
    try:
        if any(repo.name == repository for repo in org.get_repos()):
            log.error("repo already exists")
            sys.exit(1)
        org.create_repo(
            repository,
            allow_rebase_merge=False,
            auto_init=False,
            description=description,
            has_issues=has_issues,
            has_projects=has_projects,
            has_wiki=has_wiki,
            private=False,
        )
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)


def create_team(org: Organization, name: str, privacy: str, repo: str | None) -> None:
    """Create a team, optionally with a repository.

    Exits 1 when a team of that name exists or ``repo`` names no
    repository.
    """
    log.info("Creating team %s for repo %s under organization %s", name, repo, org.login)
    try:
        repos = [r for r in org.get_repos() if r.name == repo] if repo else []
        if repo and not repos:
            log.error("repo not found")
            sys.exit(1)
        if any(team.name == name for team in org.get_teams()):
            log.error("team %s already exists", name)
            sys.exit(1)
        if repos:
            org.create_team(name=name, repo_names=repos, privacy=privacy)
        else:
            org.create_team(name=name, privacy=privacy)
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)


def submit_pr(org: Organization, repo: str, pr: int) -> None:
    """Merge a pull request if it is mergeable, exiting 1 otherwise."""
    try:
        pull = org.get_repo(repo).get_pull(pr)
        if not pull.mergeable:
            log.error("PR NOT MERGEABLE %s", pull.mergeable)
            sys.exit(1)
        echo(pull.mergeable)
        pull.merge(commit_message="Vote Completed, merging INFO file")
    except GithubException as ghe:
        log.error(ghe)
        sys.exit(1)


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
    token: str = get_token(organization)
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
    """Get votes on a github pr.

    Shared by ``github votes`` and ``infofile check-votes``, so the
    mergeability observation stays on the diagnostic stream: the two
    commands disagree about what their result is, and only the caller
    knows which stream a line belongs on.
    """
    token: str = get_token(organization)
    g: Github = Github(token)
    org: Organization = _get_org(g, organization)

    gh_repo = org.get_repo(repo)
    approval_list: list[str] = []
    author: str = gh_repo.get_pull(pr).user.login
    approval_list.append(author)

    pr_mergable = gh_repo.get_pull(pr).mergeable
    log.info("MERGEABLE: %s", pr_mergable)

    approvals = gh_repo.get_pull(pr).get_reviews()
    for approve in approvals:
        if approve.state == "APPROVED":
            approval_list.append(approve.user.login)
    return approval_list


def _is_org_member(org: Organization, user: NamedUser) -> bool:
    """Report whether a user is a member of an organization, exiting on error.

    ``Organization.has_in_members`` reads every status but 204 as "not a
    member", so a 403 from a token lacking scope would pass for one.
    """
    status, headers, _ = org.requester.requestJson("GET", f"{org.url}/members/{user.login}")
    if status == 302:
        status, headers, _ = org.requester.requestJson("GET", headers["location"])
    if status == 204:
        return True
    if status == 404:
        return False
    log.error("Organization membership check failed with status %s", status)
    sys.exit(1)


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
    token: str = get_token(organization)
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
    is_member: bool = _is_org_member(org, user_object)
    echo(f"User membership status: {is_member}")

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
                sys.exit(1)
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
                sys.exit(1)
        if admin and not is_member:
            try:
                org.invite_user(
                    user=user_object,
                    role="admin",
                    teams=team_list,
                )
            except GithubException as ghe:
                log.error(ghe)
                sys.exit(1)
            echo("Sending Admin invite to user for team")

        if not admin and is_member:
            try:
                team_obj.add_membership(member=user_object, role="member")
            except GithubException as ghe:
                log.error(ghe)
                sys.exit(1)

        if not admin and not is_member:
            try:
                org.invite_user(
                    user=user_object,
                    teams=team_list,
                )
            except GithubException as ghe:
                log.error(ghe)
                sys.exit(1)
            echo("Sending invite to user for team")
