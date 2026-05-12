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
from github import Github, GithubException

from lftools_uv import config
from lftools_uv.github_helper import helper_list, helper_user_github, prvotes

log = logging.getLogger(__name__)

github_app = typer.Typer(name="github", help="GitHub tools.")


@github_app.callback()
def github_callback() -> None:
    """GitHub tools callback."""
    pass


@github_app.command(name="submit-pr")
def submit_pr(
    organization: str = typer.Argument(..., help="GitHub organization name"),
    repo: str = typer.Argument(..., help="GitHub repository name"),
    pr: int = typer.Argument(..., help="Pull request number"),
) -> None:
    """Submit a pr if mergeable."""
    if config.get_setting("github." + organization, "token"):
        token = config.get_setting("github." + organization, "token")
    else:
        token = config.get_setting("github", "token")

    g = Github(token)
    try:
        org = g.get_organization(organization)
        repo_obj = org.get_repo(repo)
        pr_mergeable = repo_obj.get_pull(pr).mergeable

        if pr_mergeable:
            log.info("PR is mergeable: %s", pr_mergeable)
            repo_obj.get_pull(pr).merge(commit_message="Vote Completed, merging INFO file")
            log.info("PR merged successfully")
        else:
            log.error("PR NOT MERGEABLE %s", pr_mergeable)
            raise typer.Exit(1)
    except GithubException as e:
        log.exception("GitHub API error: %s", e)
        raise typer.Exit(1) from None


@github_app.command(name="votes")
def votes(
    organization: str = typer.Argument(..., help="GitHub organization name"),
    repo: str = typer.Argument(..., help="GitHub repository name"),
    pr: int = typer.Argument(..., help="Pull request number"),
) -> None:
    """Helper for votes."""
    approval_list = prvotes(organization, repo, pr)
    log.info("Approvals: %s", approval_list)


@github_app.command(name="list")
def list_github(
    organization: str = typer.Argument(..., help="GitHub organization name"),
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
    organization: str = typer.Argument(..., help="GitHub organization name"),
    repository: str = typer.Argument(..., help="Repository name to create"),
    description: str = typer.Argument(..., help="Repository description"),
    has_issues: bool = typer.Option(False, "--has-issues", help="Repo should have issues"),
    has_projects: bool = typer.Option(False, "--has-projects", help="Repo should have projects"),
    has_wiki: bool = typer.Option(False, "--has-wiki", help="Repo should have wiki"),
) -> None:
    """Create a Github repo within an Organization.

    Requires an admin token.
    """
    token = config.get_setting("github", "token")
    g = Github(token)

    try:
        org = g.get_organization(organization)
        org.create_repo(
            name=repository,
            description=description,
            has_issues=has_issues,
            has_projects=has_projects,
            has_wiki=has_wiki,
        )
        log.info("Repository '%s' created successfully in organization '%s'", repository, organization)
    except GithubException as e:
        log.exception("Failed to create repository: %s", e)
        raise typer.Exit(1) from None


@github_app.command(name="update-repo")
def update_repo(
    organization: str = typer.Argument(..., help="GitHub organization name"),
    repository: str = typer.Argument(..., help="Repository name to update"),
    has_issues: bool = typer.Option(False, "--has-issues", help="Repo should have issues"),
    has_projects: bool = typer.Option(False, "--has-projects", help="Repo should have projects"),
    has_wiki: bool = typer.Option(False, "--has-wiki", help="Repo should have wiki"),
    add_team: str | None = typer.Option(None, "--add-team", help="Add team to repo"),
    remove_team: str | None = typer.Option(None, "--remove-team", help="Remove team from repo"),
) -> None:
    """Update a Github repo within an Organization.

    Requires an admin token.
    """
    token = config.get_setting("github", "token")
    g = Github(token)

    try:
        org = g.get_organization(organization)
        repo_obj = org.get_repo(repository)

        # Update repository settings
        repo_obj.edit(has_issues=has_issues, has_projects=has_projects, has_wiki=has_wiki)

        # Handle team operations
        if add_team:
            team_obj = org.get_team_by_slug(add_team)
            team_obj.add_to_repos(repo_obj)

        if remove_team:
            team_obj = org.get_team_by_slug(remove_team)
            team_obj.remove_from_repos(repo_obj)

        log.info("Repository '%s' updated successfully", repository)
    except GithubException as e:
        log.exception("Failed to update repository: %s", e)
        raise typer.Exit(1) from None


@github_app.command(name="create-team")
def create_team(
    organization: str = typer.Argument(..., help="GitHub organization name"),
    name: str = typer.Argument(..., help="Team name to create"),
    privacy: str = typer.Argument(..., help="Team privacy setting (closed/secret)"),
    repo: str | None = typer.Option(None, "--repo", help="Assign team to repo"),
) -> None:
    """Create a Github team within an Organization.

    Privacy should be set to closed
    This allows us to control group membership.

    If you have two factor auth enabled and you get a 401
    error, then you need to create a personal access token
    and add it to your ~/.netrc file.

    Requires an admin token.
    """
    token = config.get_setting("github", "token")
    g = Github(token)

    try:
        org = g.get_organization(organization)
        team_obj = org.create_team(name=name, privacy=privacy)

        if repo:
            repo_obj = org.get_repo(repo)
            team_obj.add_to_repos(repo_obj)

        log.info("Team '%s' created successfully in organization '%s'", name, organization)
    except GithubException as e:
        log.exception("Failed to create team: %s", e)
        raise typer.Exit(1) from None


@github_app.command(name="user")
def user(
    organization: str = typer.Argument(..., help="GitHub organization name"),
    user: str = typer.Argument(..., help="GitHub username"),
    team: str = typer.Argument(..., help="Team name"),
    delete: bool = typer.Option(False, "--delete", help="Remove user from org"),
    admin: bool = typer.Option(False, "--admin", help="User is admin for org, or a maintainer of a team"),
) -> None:
    """Add and Remove users from an org team."""
    try:
        helper_user_github(None, organization, user, team, delete, admin)
        action = "removed from" if delete else "added to"
        log.info("User '%s' %s team '%s' successfully", user, action, team)
    except Exception as e:
        log.exception("Failed to modify user team membership: %s", e)
        raise typer.Exit(1) from None
