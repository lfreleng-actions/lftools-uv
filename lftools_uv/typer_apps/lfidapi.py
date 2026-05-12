# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of LFIDAPI commands."""

import logging

import typer

from lftools_uv.lfidapi import (
    helper_create_group,
    helper_invite,
    helper_match_ldap_to_info,
    helper_search_members,
    helper_user,
)

log = logging.getLogger(__name__)

# Create the lfidapi subcommand group
lfidapi_app = typer.Typer(
    name="lfidapi",
    help="LFID API tools for managing groups and members",
    add_completion=False,
)


@lfidapi_app.callback()
def lfidapi_callback() -> None:
    """LFID API TOOLS."""
    pass


@lfidapi_app.command("search-members")
def search_members(
    group: str = typer.Argument(..., help="Group name to search for members"),
) -> None:
    """List members of a group.

    Args:
        group: The name of the group to search

    Examples:
        lftools-uv lfidapi search-members "example-group"
    """
    try:
        members = helper_search_members(group)
        if members is None:
            log.error(f"No members found or failed to search group {group}")
            typer.echo(f"Error: No members found for group {group}", err=True)
            raise typer.Exit(1)
        for member in members:
            typer.echo(f"{member['username']} <{member['mail']}>")
    except Exception as e:
        log.exception(f"Failed to search members for group {group}: {e}")
        typer.echo(f"Error: Failed to search members for group {group}: {e}", err=True)
        raise typer.Exit(1) from None


@lfidapi_app.command("user")
def user_command(
    user: str = typer.Argument(..., help="Username to add or remove"),
    group: str = typer.Argument(..., help="Group name"),
    delete: bool = typer.Option(False, "--delete", help="Remove user from group instead of adding"),
) -> None:
    """Add and remove users from groups.

    Args:
        user: The username to add or remove
        group: The group name
        delete: If True, remove user from group instead of adding

    Examples:
        lftools-uv lfidapi user "john.doe" "example-group"
        lftools-uv lfidapi user "john.doe" "example-group" --delete
    """
    try:
        helper_user(user, group, delete)
        action = "removed from" if delete else "added to"
        typer.echo(f"✅ User {user} {action} group {group}")
    except Exception as e:
        log.exception(f"Failed to manage user {user} in group {group}: {e}")
        typer.echo(f"Error: Failed to manage user {user} in group {group}: {e}", err=True)
        raise typer.Exit(1) from None


@lfidapi_app.command("invite")
def invite_command(
    email: str = typer.Argument(..., help="Email address to invite"),
    group: str = typer.Argument(..., help="Group name to invite to"),
) -> None:
    """Email invitation to join group.

    Args:
        email: The email address to send invitation to
        group: The group name to invite to

    Examples:
        lftools-uv lfidapi invite "user@example.com" "example-group"
    """
    try:
        helper_invite(email, group)
        typer.echo(f"✅ Invitation sent to {email} for group {group}")
    except Exception as e:
        log.exception(f"Failed to send invitation to {email} for group {group}: {e}")
        typer.echo(f"Error: Failed to send invitation to {email} for group {group}: {e}", err=True)
        raise typer.Exit(1) from None


@lfidapi_app.command("create-group")
def create_group_command(
    group: str = typer.Argument(..., help="Group name to create"),
) -> None:
    """Create group.

    Args:
        group: The name of the group to create

    Examples:
        lftools-uv lfidapi create-group "new-group"
    """
    try:
        helper_create_group(group)
        typer.echo(f"✅ Group {group} created successfully")
    except Exception as e:
        log.exception(f"Failed to create group {group}: {e}")
        typer.echo(f"Error: Failed to create group {group}: {e}", err=True)
        raise typer.Exit(1) from None


@lfidapi_app.command("match-ldap-info")
def match_ldap_info(
    info_file: str = typer.Argument(..., help="Path to INFO.yaml file"),
    group: str = typer.Argument(..., help="LDAP group name"),
    githuborg: str = typer.Option("", help="GitHub organization (leave empty for LDAP)"),
    noop: bool = typer.Option(False, "--noop", help="Dry run mode"),
) -> None:
    """Match LDAP information to INFO files."""
    try:
        helper_match_ldap_to_info(info_file, group, githuborg, noop)
        typer.echo("✅ LDAP to INFO matching completed")
    except Exception as e:
        log.exception(f"Failed to match LDAP to INFO: {e}")
        typer.echo(f"Error: Failed to match LDAP to INFO: {e}", err=True)
        raise typer.Exit(1) from None


def get_lfidapi_app() -> typer.Typer:
    """Get the lfidapi Typer app instance.

    This function is used by other modules to register the lfidapi commands.
    """
    return lfidapi_app
