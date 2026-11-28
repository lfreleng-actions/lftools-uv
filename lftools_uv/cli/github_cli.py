# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Github tools."""

from __future__ import annotations

import logging
import sys

import click
from github import Github

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

log = logging.getLogger(__name__)


@click.group()
@click.pass_context
def github_cli(ctx):
    """GITHUB TOOLS."""
    pass


@click.command(name="submit-pr")
@click.argument("organization")
@click.argument("repo")
@click.argument("pr", type=int)
@click.pass_context
def submit_pr(ctx, organization, repo, pr):
    """Submit a pr if mergeable."""
    helper_submit_pr(connect(organization, Github), repo, pr)


@click.command(name="votes")
@click.argument("organization")
@click.argument("repo")
@click.argument("pr", type=int)
@click.pass_context
def votes(ctx, organization, repo, pr):
    """Helper for votes."""
    approval_list = prvotes(organization, repo, pr)
    echo(f"Approvals: {approval_list}")


@click.command(name="list")
@click.argument("organization")
@click.option("--audit", is_flag=True, required=False, help="List members without 2fa")
@click.option("--repos", is_flag=True, required=False, help="List all repos")
@click.option("--full", is_flag=True, required=False, help="All members and their respective teams")
@click.option("--teams", is_flag=True, required=False, help="List available teams")
@click.option("--team", type=str, required=False, help="List members of a team")
@click.option("--repofeatures", is_flag=True, required=False, help="List enabled features for repos in an org")
@click.pass_context
# aislop-ignore-next-line too-many-params -- Click binds one parameter per CLI option
def list(ctx, organization, repos, audit, full, teams, team, repofeatures):
    """List options for github org repos."""
    helper_list(ctx, organization, repos, audit, full, teams, team, repofeatures)


@click.command(name="create-repo")
@click.argument("organization")
@click.argument("repository")
@click.argument("description")
@click.option("--has_issues", is_flag=True, required=False, help="Repo should have issues")
@click.option("--has_projects", is_flag=True, required=False, help="Repo should have projects")
@click.option("--has_wiki", is_flag=True, required=False, help="Repo should have wiki")
@click.pass_context
# aislop-ignore-next-line too-many-params -- Click binds one parameter per CLI option
def createrepo(ctx, organization, repository, description, has_issues, has_projects, has_wiki):
    """Create a Github repo within an Organization.

    By default has_issues has_wiki and has_projects is set to false.
    See --help to create a repo with these enabled.
    """
    org = connect(organization, Github)
    helper_create_repo(org, repository, description, has_issues, has_projects, has_wiki)


@click.command(name="update-repo")
@click.argument("organization")
@click.argument("repository")
@click.option("--has_issues", is_flag=True, required=False, help="Repo should have issues")
@click.option("--has_projects", is_flag=True, required=False, help="Repo should have projects")
@click.option("--has_wiki", is_flag=True, required=False, help="Repo should have wiki")
@click.option("--add_team", type=str, required=False, help="Add team to repo")
@click.option("--remove_team", type=str, required=False, help="remove team from repo")
@click.pass_context
# aislop-ignore-next-line too-many-params -- Click binds one parameter per CLI option
def updaterepo(ctx, organization, repository, has_issues, has_projects, has_wiki, add_team, remove_team):
    """Update a Github repo within an Organization.

    By default has_issues has_wiki and has_projects is set to false.
    See --help to use this command to enable these options.
    """
    org = connect(organization, Github)

    has_issues = has_issues or False
    has_wiki = has_wiki or False
    has_projects = has_projects or False

    repo = next((repo for repo in org.get_repos() if repo.name == repository), None)
    if repo is None:
        log.error("repo not found")
        sys.exit(1)

    add, remove = resolve_repo_teams(org, add_team, remove_team)

    if has_wiki or has_issues or has_projects:
        repo.edit(has_issues=has_issues, has_wiki=has_wiki, has_projects=has_projects)

    apply_repo_teams(repo, add, remove)


@click.command(name="create-team")
@click.argument("organization")
@click.argument("name")
@click.argument("privacy")
@click.option("--repo", type=str, required=False, help="Assign team to repo")
@click.pass_context
def createteam(ctx, organization, name, repo, privacy):
    """Create a Github team within an Organization.

    Privacy should be set to closed
    This allows us to control group membership.
    """
    helper_create_team(connect(organization, Github), name, privacy, repo)


@click.command(name="user")
@click.argument("organization")
@click.argument("user")
@click.argument("team")
@click.option("--delete", is_flag=True, required=False, help="Remove user from org")
@click.option("--admin", is_flag=True, required=False, help="User is admin for org, or a maintainer of a team")
@click.pass_context
def user(ctx, organization, user, team, delete, admin):
    """Add and Remove users from an org team."""
    helper_user_github(ctx, organization, user, team, delete, admin)


github_cli.add_command(submit_pr)
github_cli.add_command(votes)
github_cli.add_command(list)
github_cli.add_command(createteam)
github_cli.add_command(createrepo)
github_cli.add_command(updaterepo)
github_cli.add_command(user)
