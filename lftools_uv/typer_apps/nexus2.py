# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer Nexus2 CLI commands."""

import logging

import typer
from tabulate import tabulate

from lftools_uv.api.endpoints import nexus2
from lftools_uv.output import echo

log = logging.getLogger(__name__)

nexus2_app = typer.Typer(help="The Nexus2 API Interface.")

privilege_app = typer.Typer(help="Privilege primary interface.")
repo_app = typer.Typer(help="Repository primary interface.")
role_app = typer.Typer(help="Role primary interface.")
user_app = typer.Typer(help="User primary interface.")

# Add sub-apps to main app
nexus2_app.add_typer(privilege_app, name="privilege")
nexus2_app.add_typer(repo_app, name="repo")
nexus2_app.add_typer(role_app, name="role")
nexus2_app.add_typer(user_app, name="user")


# Global callback for nexus2 app to initialize Nexus2 client
@nexus2_app.callback()
def nexus2_callback(
    ctx: typer.Context,
    fqdn: str = typer.Argument(..., help="Nexus2 server FQDN"),
) -> None:
    """The Nexus2 API Interface."""
    # Check if we're just asking for help - if so, skip initialization
    if ctx.resilient_parsing:
        return

    try:
        nexus2_obj = nexus2.Nexus2(fqdn=fqdn)
        if ctx.obj is None:
            ctx.obj = {}
        # Store client in raw context (legacy) and structured AppState if available
        ctx.obj["nexus2"] = nexus2_obj
        state = ctx.obj.get("state")
        if state:
            state.nexus2 = nexus2_obj
    except Exception:
        # For help requests, don't fail - just continue without initializing client
        if ctx.obj is None:
            ctx.obj = {}


# Privilege subcommands
@privilege_app.command("list")
def privilege_list(ctx: typer.Context) -> None:
    """List privileges."""
    try:
        r = ctx.obj["nexus2"]
        data = r.privilege_list()
        echo(tabulate(data, headers=["Name", "ID"]))
    except Exception:
        log.exception("Failed to list privileges")
        raise typer.Exit(1) from None


@privilege_app.command("create")
def privilege_create(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Privilege name"),
    description: str = typer.Argument(..., help="Privilege description"),
    repo: str = typer.Argument(..., help="Repository name"),
) -> None:
    """Create a new privilege."""
    try:
        r = ctx.obj["nexus2"]
        data = r.privilege_create(name, description, repo)
        echo(data)
    except Exception:
        log.exception("Failed to create privilege")
        raise typer.Exit(1) from None


@privilege_app.command("delete")
def privilege_delete(
    ctx: typer.Context,
    privilege_id: str = typer.Argument(..., help="Privilege ID to delete"),
) -> None:
    """Delete a privilege."""
    try:
        r = ctx.obj["nexus2"]
        data = r.privilege_delete(privilege_id)
        echo(data)
    except Exception:
        log.exception("Failed to delete privilege")
        raise typer.Exit(1) from None


# Repository subcommands
@repo_app.command("list")
def repo_list(ctx: typer.Context) -> None:
    """List repositories."""
    try:
        r = ctx.obj["nexus2"]
        data = r.repo_list()
        echo(tabulate(data, headers=["Name", "Type", "Provider", "ID"]))
    except Exception:
        log.exception("Failed to list repositories")
        raise typer.Exit(1) from None


@repo_app.command("create")
def repo_create(
    ctx: typer.Context,
    repo_type: str = typer.Argument(..., help="Repository type"),
    repo_id: str = typer.Argument(..., help="Repository ID"),
    repo_name: str = typer.Argument(..., help="Repository name"),
    repo_provider: str = typer.Argument(..., help="Repository provider"),
    repo_policy: str = typer.Argument(..., help="Repository policy"),
    repo_upstream_url: str | None = typer.Option(None, "--upstream-repo", "-u", help="Upstream repository URL"),
) -> None:
    """Create a new repository."""
    try:
        r = ctx.obj["nexus2"]
        data = r.repo_create(repo_type, repo_id, repo_name, repo_provider, repo_policy, repo_upstream_url)
        echo(data)
    except Exception:
        log.exception("Failed to create repository")
        raise typer.Exit(1) from None


@repo_app.command("delete")
def repo_delete(
    ctx: typer.Context,
    repo_id: str = typer.Argument(..., help="Repository ID to delete"),
) -> None:
    """Permanently delete a repo."""
    try:
        r = ctx.obj["nexus2"]
        data = r.repo_delete(repo_id)
        echo(data)
    except Exception:
        log.exception("Failed to delete repository")
        raise typer.Exit(1) from None


# Role subcommands
@role_app.command("list")
def role_list(ctx: typer.Context) -> None:
    """List roles."""
    try:
        r = ctx.obj["nexus2"]
        data = r.role_list()
        echo(tabulate(data, headers=["ID", "Name", "Roles", "Privileges"], tablefmt="grid"))
    except Exception:
        log.exception("Failed to list roles")
        raise typer.Exit(1) from None


@role_app.command("create")
def role_create(
    ctx: typer.Context,
    role_id: str = typer.Argument(..., help="Role ID"),
    role_name: str = typer.Argument(..., help="Role name"),
    role_description: str | None = typer.Option(None, "--description", "-d", help="Role description"),
    roles_list: str | None = typer.Option(None, "--roles", "-r", help="Comma-separated list of roles"),
    privileges_list: str | None = typer.Option(None, "--privileges", "-p", help="Comma-separated list of privileges"),
) -> None:
    """Create a new role."""
    try:
        r = ctx.obj["nexus2"]
        data = r.role_create(role_id, role_name, role_description, roles_list, privileges_list)
        echo(data)
    except Exception:
        log.exception("Failed to create role")
        raise typer.Exit(1) from None


@role_app.command("delete")
def role_delete(
    ctx: typer.Context,
    role_id: str = typer.Argument(..., help="Role ID to delete"),
) -> None:
    """Delete a role."""
    try:
        r = ctx.obj["nexus2"]
        data = r.role_delete(role_id)
        echo(data)
    except Exception:
        log.exception("Failed to delete role")
        raise typer.Exit(1) from None


# User subcommands
@user_app.command("list")
def user_list(ctx: typer.Context) -> None:
    """List users."""
    try:
        r = ctx.obj["nexus2"]
        data = r.user_list()
        echo(tabulate(data, headers=["ID", "First Name", "Last Name", "Status", "Roles"]))
    except Exception:
        log.exception("Failed to list users")
        raise typer.Exit(1) from None


@user_app.command("add")
def user_create(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Username"),
    firstname: str = typer.Argument(..., help="First name"),
    lastname: str = typer.Argument(..., help="Last name"),
    email: str = typer.Argument(..., help="Email address"),
    roles: str = typer.Argument(..., help="Comma-separated list of roles"),
    password: str | None = typer.Argument(None, help="Password (will be generated if not provided)"),
) -> None:
    """Add a new user."""
    try:
        r = ctx.obj["nexus2"]
        data = r.user_create(username, firstname, lastname, email, roles, password)
        echo(data)
    except Exception:
        log.exception("Failed to create user")
        raise typer.Exit(1) from None


@user_app.command("delete")
def user_delete(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Username to delete"),
) -> None:
    """Delete a user."""
    try:
        r = ctx.obj["nexus2"]
        data = r.user_delete(username)
        echo(data)
    except Exception:
        log.exception("Failed to delete user")
        raise typer.Exit(1) from None
