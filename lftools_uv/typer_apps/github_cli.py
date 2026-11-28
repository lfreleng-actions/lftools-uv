# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer CLI interface for GitHub tools."""

__author__ = "DW Talton"

import logging

import typer

# aislop-ignore-next-line hallucinated-import -- the declared PyGithub dependency provides the `github` package
from github import Github, GithubException
from github.GithubObject import NotSet

from lftools_uv.github_helper import (
    apply_repo_teams,
    connect,
    helper_list,
    helper_user_github,
    prvotes,
    resolve_repo_teams,
)
from lftools_uv.github_helper import create_repo as helper_create_repo
from lftools_uv.github_helper import create_team as helper_create_team
from lftools_uv.github_helper import submit_pr as helper_submit_pr
from lftools_uv.output import echo

_HELP_GITHUB_ORG = "GitHub organization name"


log = logging.getLogger(__name__)

github_app = typer.Typer(name="github", help="GitHub tools.")


@github_app.callback()
def github_callback() -> None:
    """GitHub tools callback."""
    pass


@github_app.command(name="submit-pr")
def submit_pr(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    repo: str = typer.Argument(..., help="GitHub repository name"),
    pr: int = typer.Argument(..., help="Pull request number"),
) -> None:
    """Submit a pr if mergeable."""
    helper_submit_pr(connect(organization, Github), repo, pr)


@github_app.command(name="votes")
def votes(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    repo: str = typer.Argument(..., help="GitHub repository name"),
    pr: int = typer.Argument(..., help="Pull request number"),
) -> None:
    """Helper for votes."""
    approval_list = prvotes(organization, repo, pr)
    echo(f"Approvals: {approval_list}")


@github_app.command(name="list")
def list_github(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    audit: bool = typer.Option(False, "--audit", help="List members without 2fa"),
    repos: bool = typer.Option(False, "--repos", help="List all repos"),
    full: bool = typer.Option(False, "--full", help="All members and their respective teams"),
    teams: bool = typer.Option(False, "--teams", help="List available teams"),
    team: str | None = typer.Option(None, "--team", help="List members of a team"),
    repofeatures: bool = typer.Option(False, "--repofeatures", help="List enabled features for repos in an org"),
) -> None:
    """List options for github org repos."""
    helper_list(None, organization, repos, audit, full, teams, team, repofeatures)


@github_app.command(name="create-repo")
def create_repo(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    repository: str = typer.Argument(..., help="Repository name to create"),
    description: str = typer.Argument(..., help="Repository description"),
    has_issues: bool = typer.Option(False, "--has-issues", "--has_issues", help="Repo should have issues"),
    has_projects: bool = typer.Option(False, "--has-projects", "--has_projects", help="Repo should have projects"),
    has_wiki: bool = typer.Option(False, "--has-wiki", "--has_wiki", help="Repo should have wiki"),
) -> None:
    """Create a Github repo within an Organization.

    Requires an admin token.
    """
    org = connect(organization, Github)
    helper_create_repo(org, repository, description, has_issues, has_projects, has_wiki)


@github_app.command(name="update-repo")
def update_repo(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    repository: str = typer.Argument(..., help="Repository name to update"),
    has_issues: bool | None = typer.Option(
        None, "--has-issues/--no-has-issues", "--has_issues", help="Turn issues on or off; unchanged if omitted"
    ),
    has_projects: bool | None = typer.Option(
        None, "--has-projects/--no-has-projects", "--has_projects", help="Turn projects on or off; unchanged if omitted"
    ),
    has_wiki: bool | None = typer.Option(
        None, "--has-wiki/--no-has-wiki", "--has_wiki", help="Turn the wiki on or off; unchanged if omitted"
    ),
    add_team: str | None = typer.Option(None, "--add-team", "--add_team", help="Add team to repo"),
    remove_team: str | None = typer.Option(None, "--remove-team", "--remove_team", help="Remove team from repo"),
) -> None:
    """Update a Github repo within an Organization.

    Only the features named on the command line change; the others keep
    their current setting.

    Requires an admin token.
    """
    features = (has_issues, has_projects, has_wiki)
    if all(feature is None for feature in features) and not add_team and not remove_team:
        log.warning("Nothing to update for repository '%s'", repository)
        return

    org = connect(organization, Github)
    add, remove = resolve_repo_teams(org, add_team, remove_team)

    try:
        repo_obj = org.get_repo(repository)

        if any(feature is not None for feature in features):
            repo_obj.edit(
                has_issues=NotSet if has_issues is None else has_issues,
                has_projects=NotSet if has_projects is None else has_projects,
                has_wiki=NotSet if has_wiki is None else has_wiki,
            )
    except GithubException:
        log.exception("Failed to update repository")
        raise typer.Exit(1) from None

    apply_repo_teams(repo_obj, add, remove)

    log.info("Repository '%s' updated successfully", repository)


@github_app.command(name="create-team")
def create_team(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    name: str = typer.Argument(..., help="Team name to create"),
    privacy: str = typer.Argument(..., help="Team privacy setting (closed/secret)"),
    repo: str | None = typer.Option(None, "--repo", help="Assign team to repo"),
) -> None:
    """Create a Github team within an Organization.

    Privacy should be set to closed
    This allows us to control group membership.

    Requires an admin token.
    """
    helper_create_team(connect(organization, Github), name, privacy, repo)


@github_app.command(name="user")
def user(
    organization: str = typer.Argument(..., help=_HELP_GITHUB_ORG),
    user: str = typer.Argument(..., help="GitHub username"),
    team: str = typer.Argument(..., help="Team name"),
    delete: bool = typer.Option(False, "--delete", help="Remove user from org"),
    admin: bool = typer.Option(False, "--admin", help="User is admin for org, or a maintainer of a team"),
) -> None:
    """Add and Remove users from an org team."""
    try:
        helper_user_github(None, organization, user, team, delete, admin)
    except Exception:
        log.exception("Failed to modify user team membership")
        raise typer.Exit(1) from None
