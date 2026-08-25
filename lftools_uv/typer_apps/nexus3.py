# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer Nexus3 CLI commands."""

import logging
from pprint import pformat

import typer
from tabulate import tabulate

from lftools_uv.api.endpoints import nexus3
from lftools_uv.output import echo

log = logging.getLogger(__name__)

nexus3_app = typer.Typer(help="The Nexus3 API Interface.")

asset_app = typer.Typer(help="Asset primary interface.")
privilege_app = typer.Typer(help="Privilege primary interface.")
repository_app = typer.Typer(help="Repository primary interface.")
role_app = typer.Typer(help="Role primary interface.")
script_app = typer.Typer(help="Script primary interface.")
tag_app = typer.Typer(help="Tag primary interface.")
task_app = typer.Typer(help="Task primary interface.")
user_app = typer.Typer(help="User primary interface.")

# Add sub-apps to main app
nexus3_app.add_typer(asset_app, name="asset")
nexus3_app.add_typer(privilege_app, name="privilege")
nexus3_app.add_typer(repository_app, name="repository")
nexus3_app.add_typer(role_app, name="role")
nexus3_app.add_typer(script_app, name="script")
nexus3_app.add_typer(tag_app, name="tag")
nexus3_app.add_typer(task_app, name="task")
nexus3_app.add_typer(user_app, name="user")


# Global callback for nexus3 app to initialize Nexus3 client
@nexus3_app.callback()
def nexus3_callback(
    ctx: typer.Context,
    fqdn: str = typer.Argument(..., help="Nexus3 server FQDN"),
) -> None:
    """The Nexus3 API Interface."""
    # Check if we're just asking for help - if so, skip initialization
    if ctx.resilient_parsing:
        return

    try:
        nexus3_obj = nexus3.Nexus3(fqdn=fqdn)
        # Preserve existing context; add nexus3 client without overwriting other keys
        if ctx.obj is None:
            ctx.obj = {}
        ctx.obj["nexus3"] = nexus3_obj
        # Also register inside structured AppState if available
        state = ctx.obj.get("state")
        if state:
            state.nexus3 = nexus3_obj
    except Exception:
        # For help requests, don't fail - just continue without initializing client
        if ctx.obj is None:
            ctx.obj = {}


# Asset subcommands
@asset_app.command("list")
def asset_list(ctx: typer.Context, repository: str = typer.Argument(..., help="Repository name")) -> None:
    """List assets."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_assets(repository)
        for item in data:
            echo(pformat(item))
    except Exception:
        log.exception("Failed to list assets")
        raise typer.Exit(1) from None


@asset_app.command("search")
def asset_search(
    ctx: typer.Context,
    query_string: str = typer.Argument(..., help="Query string to search for"),
    repository: str = typer.Argument(..., help="Repository name"),
    details: bool = typer.Option(False, "--details", help="Show detailed results"),
) -> None:
    """Search assets."""
    try:
        r = ctx.obj["nexus3"]
        data = r.search_asset(query_string, repository, details)

        if details:
            echo(data)
        else:
            for item in data:
                echo(item)
    except Exception:
        log.exception("Failed to search assets")
        raise typer.Exit(1) from None


# Privilege subcommands
@privilege_app.command("list")
def list_privileges(ctx: typer.Context) -> None:
    """List privileges."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_privileges()
        echo(tabulate(data, headers=["Type", "Name", "Description", "Read Only"]))
    except Exception:
        log.exception("Failed to list privileges")
        raise typer.Exit(1) from None


# Repository subcommands
@repository_app.command("list")
def list_repositories(ctx: typer.Context) -> None:
    """List repositories."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_repositories()
        echo(pformat(data))
    except Exception:
        log.exception("Failed to list repositories")
        raise typer.Exit(1) from None


# Role subcommands
@role_app.command("list")
def list_roles(ctx: typer.Context) -> None:
    """List roles."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_roles()
        echo(tabulate(data, headers=["Roles"]))
    except Exception:
        log.exception("Failed to list roles")
        raise typer.Exit(1) from None


@role_app.command("create")
def create_role(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Role name"),
    description: str = typer.Argument(..., help="Role description"),
    privileges: str = typer.Argument(..., help="Comma-separated list of privileges"),
    roles: str = typer.Argument(..., help="Comma-separated list of roles"),
) -> None:
    """Create roles."""
    try:
        r = ctx.obj["nexus3"]
        data = r.create_role(name, description, privileges, roles)
        echo(pformat(data))
    except Exception:
        log.exception("Failed to create role")
        raise typer.Exit(1) from None


# Script subcommands
@script_app.command("create")
def create_script(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Script name"),
    filename: str = typer.Argument(..., help="Script filename"),
) -> None:
    """Create a new script."""
    try:
        r = ctx.obj["nexus3"]
        data = r.create_script(name, filename)
        echo(data)
    except Exception:
        log.exception("Failed to create script")
        raise typer.Exit(1) from None


@script_app.command("delete")
def delete_script(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Script name to delete"),
) -> None:
    """Delete a script."""
    try:
        r = ctx.obj["nexus3"]
        data = r.delete_script(name)
        echo(data)
    except Exception:
        log.exception("Failed to delete script")
        raise typer.Exit(1) from None


@script_app.command("list")
def list_scripts(ctx: typer.Context) -> None:
    """List all scripts."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_scripts()
        echo(data)
    except Exception:
        log.exception("Failed to list scripts")
        raise typer.Exit(1) from None


@script_app.command("read")
def read_script(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Script name to read"),
) -> None:
    """Get script contents."""
    try:
        r = ctx.obj["nexus3"]
        data = r.read_script(name)
        echo(data)
    except Exception:
        log.exception("Failed to read script")
        raise typer.Exit(1) from None


@script_app.command("run")
def run_script(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Script name to run"),
) -> None:
    """Run a script."""
    try:
        r = ctx.obj["nexus3"]
        data = r.run_script(name)
        echo(data)
    except Exception:
        log.exception("Failed to run script")
        raise typer.Exit(1) from None


@script_app.command("update")
def update_script(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Script name to update"),
    content: str = typer.Argument(..., help="New script content"),
) -> None:
    """Update script contents."""
    try:
        r = ctx.obj["nexus3"]
        data = r.update_script(name, content)
        echo(data)
    except Exception:
        log.exception("Failed to update script")
        raise typer.Exit(1) from None


# Tag subcommands
@tag_app.command("add")
def add_tag(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Tag name"),
    attributes: str | None = typer.Argument(None, help="Tag attributes"),
) -> None:
    """Add a tag."""
    try:
        r = ctx.obj["nexus3"]
        data = r.create_tag(name, attributes)
        echo(pformat(data))
    except Exception:
        log.exception("Failed to add tag")
        raise typer.Exit(1) from None


@tag_app.command("delete")
def delete_tag(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Tag name to delete"),
) -> None:
    """Delete a tag."""
    try:
        r = ctx.obj["nexus3"]
        data = r.delete_tag(name)
        echo(pformat(data))
    except Exception:
        log.exception("Failed to delete tag")
        raise typer.Exit(1) from None


@tag_app.command("list")
def list_tags(ctx: typer.Context) -> None:
    """List tags."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_tags()
        echo(pformat(data))
    except Exception:
        log.exception("Failed to list tags")
        raise typer.Exit(1) from None


@tag_app.command("show")
def show_tag(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Tag name to show"),
) -> None:
    """Show tags."""
    try:
        r = ctx.obj["nexus3"]
        data = r.show_tag(name)
        echo(pformat(data))
    except Exception:
        log.exception("Failed to show tag")
        raise typer.Exit(1) from None


# Task subcommands
@task_app.command("list")
def list_tasks(ctx: typer.Context) -> None:
    """List tasks."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_tasks()
        echo(
            tabulate(
                data,
                headers=["Name", "Message", "Current State", "Last Run Result"],
            )
        )
    except Exception:
        log.exception("Failed to list tasks")
        raise typer.Exit(1) from None


# User subcommands
@user_app.command("search")
def search_user(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Username to search for"),
) -> None:
    """Search users."""
    try:
        r = ctx.obj["nexus3"]
        data = r.list_user(username)
        echo(
            tabulate(
                data,
                headers=[
                    "User ID",
                    "First Name",
                    "Last Name",
                    "Email Address",
                    "Status",
                    "Roles",
                ],
            )
        )
    except Exception:
        log.exception("Failed to search user")
        raise typer.Exit(1) from None


@user_app.command("create")
def user_create(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Username"),
    first_name: str = typer.Argument(..., help="First name"),
    last_name: str = typer.Argument(..., help="Last name"),
    email_address: str = typer.Argument(..., help="Email address"),
    roles: str = typer.Argument(..., help="Comma-separated list of roles"),
    password: str | None = typer.Argument(None, help="Password (will be generated if not provided)"),
) -> None:
    """Create a new user account."""
    try:
        r = ctx.obj["nexus3"]
        data = r.create_user(username, first_name, last_name, email_address, roles, password)
        echo(data)
    except Exception:
        log.exception("Failed to create user")
        raise typer.Exit(1) from None


@user_app.command("delete")
def user_delete(
    ctx: typer.Context,
    username: str = typer.Argument(..., help="Username to delete"),
) -> None:
    """Delete a user account."""
    try:
        r = ctx.obj["nexus3"]
        data = r.delete_user(username)
        echo(data)
    except Exception:
        log.exception("Failed to delete user")
        raise typer.Exit(1) from None
