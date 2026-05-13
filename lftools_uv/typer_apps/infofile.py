# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of infofile commands."""

import logging

import typer

_HELP_INFO_YAML_PATH = "Path to INFO.yaml file"
_MSG_REQUIRES_LEGACY_CLI = "Note: This command requires the original lftools CLI implementation."


# Import functions that we'll wrap - these are Click-based functions
# We'll create simplified wrappers for now

log = logging.getLogger(__name__)

# Create the infofile subcommand group
infofile_app = typer.Typer(
    name="infofile",
    help="INFO.yaml file management tools",
    add_completion=False,
)


@infofile_app.callback()
def infofile_callback() -> None:
    """INFO.yaml TOOLS."""
    pass


@infofile_app.command("create-info-file")
def create_info_file(
    gerrit_url: str = typer.Argument(..., help="Gerrit URL (e.g., gerrit.example.com)"),
    gerrit_project: str = typer.Argument(..., help="Gerrit project path (e.g., project/full-name)"),
    directory: str = typer.Option("r", "--directory", help="Custom gerrit directory, e.g. not /r/"),
    empty: bool = typer.Option(False, "--empty", help="Create info file for uncreated project"),
    tsc_approval: str = typer.Option("missing", "--tsc-approval", help="Optionally provide a TSC approval link"),
) -> None:
    """Create an initial INFO file.

    Args:
        gerrit_url: Gerrit URL (e.g., gerrit.umbrella.com)
        gerrit_project: Gerrit project path (e.g., project/full-name)
        directory: Custom gerrit directory (e.g., /gerrit/ rather than /r/)
        empty: Create info file for uncreated project
        tsc_approval: TSC approval link

    Examples:
        lftools-uv infofile create-info-file gerrit.example.com project/name
        lftools-uv infofile create-info-file gerrit.example.com project/name --empty
    """
    try:
        # For now, provide guidance on using the original command
        typer.echo(f"Creating INFO file for project: {gerrit_project}")
        typer.echo(f"Gerrit URL: {gerrit_url}")
        typer.echo(_MSG_REQUIRES_LEGACY_CLI)
        typer.echo("Use: lftools infofile create-info-file for full functionality.")
    except Exception as e:
        log.exception("Failed to create info file")
        typer.echo(f"Error: Failed to create info file: {e}", err=True)
        raise typer.Exit(1) from None


@infofile_app.command("get-committers")
def get_committers(
    gerrit_url: str = typer.Argument(..., help="Gerrit URL"),
    gerrit_project: str = typer.Argument(..., help="Gerrit project path"),
    ldap_group: str = typer.Argument(..., help="LDAP group name"),
    info_file: str = typer.Argument(..., help=_HELP_INFO_YAML_PATH),
    directory: str = typer.Option("r", "--directory", help="Custom gerrit directory"),
) -> None:
    """Get committers from LDAP and update INFO file.

    Args:
        gerrit_url: Gerrit URL
        gerrit_project: Gerrit project path
        ldap_group: LDAP group name
        info_file: Path to INFO.yaml file
        directory: Custom gerrit directory

    Examples:
        lftools-uv infofile get-committers gerrit.example.com project/name ldap-group INFO.yaml
    """
    try:
        typer.echo(f"Getting committers for project: {gerrit_project}")
        typer.echo(f"LDAP group: {ldap_group}")
        typer.echo(f"INFO file: {info_file}")
        typer.echo(_MSG_REQUIRES_LEGACY_CLI)
        typer.echo("Use: lftools infofile get-committers for full functionality.")
    except Exception as e:
        log.exception("Failed to get committers")
        typer.echo(f"Error: Failed to get committers: {e}", err=True)
        raise typer.Exit(1) from None


@infofile_app.command("validate-info-file")
def validate_info_file(
    info_file: str = typer.Argument(..., help="Path to INFO.yaml file to validate"),
) -> None:
    """Validate INFO.yaml file format and content.

    Args:
        info_file: Path to INFO.yaml file to validate

    Examples:
        lftools-uv infofile validate-info-file INFO.yaml
    """
    try:
        typer.echo(f"Validating INFO file: {info_file}")
        typer.echo(_MSG_REQUIRES_LEGACY_CLI)
        typer.echo("Use: lftools infofile validate-info-file for full functionality.")
    except Exception as e:
        log.exception("INFO file validation failed")
        typer.echo(f"Error: INFO file validation failed: {e}", err=True)
        raise typer.Exit(1) from None


@infofile_app.command("check-committers")
def check_committers(
    info_file: str = typer.Argument(..., help=_HELP_INFO_YAML_PATH),
) -> None:
    """Check committers in INFO file against LDAP.

    Args:
        info_file: Path to INFO.yaml file

    Examples:
        lftools-uv infofile check-committers INFO.yaml
    """
    try:
        typer.echo(f"Checking committers in INFO file: {info_file}")
        typer.echo(_MSG_REQUIRES_LEGACY_CLI)
        typer.echo("Use: lftools infofile check-committers for full functionality.")
    except Exception as e:
        log.exception("Committers check failed")
        typer.echo(f"Error: Committers check failed: {e}", err=True)
        raise typer.Exit(1) from None


@infofile_app.command("match-ldap")
def match_ldap(
    info_file: str = typer.Argument(..., help=_HELP_INFO_YAML_PATH),
) -> None:
    """Match LDAP information to INFO file.

    Args:
        info_file: Path to INFO.yaml file

    Examples:
        lftools-uv infofile match-ldap INFO.yaml
    """
    try:
        typer.echo(f"Matching LDAP information for INFO file: {info_file}")
        typer.echo(_MSG_REQUIRES_LEGACY_CLI)
        typer.echo("Use: lftools infofile match-ldap for full functionality.")
    except Exception as e:
        log.exception("LDAP matching failed")
        typer.echo(f"Error: LDAP matching failed: {e}", err=True)
        raise typer.Exit(1) from None


def get_infofile_app() -> typer.Typer:
    """Get the infofile Typer app instance.

    This function is used by other modules to register the infofile commands.
    """
    return infofile_app
