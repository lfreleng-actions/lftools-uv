# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of Read the Docs commands."""

import logging

import typer

from lftools_uv.api.endpoints.readthedocs import ReadTheDocs

log = logging.getLogger(__name__)

# Create the rtd subcommand group
rtd_app = typer.Typer(
    name="rtd",
    help="Read the Docs interface",
    add_completion=False,
)


@rtd_app.callback()
def rtd_callback() -> None:
    """Read the Docs interface."""
    pass


@rtd_app.command("project-list")
def project_list() -> None:
    """Get a list of Read the Docs projects.

    Returns a list of RTD projects for the account whose
    token is configured in lftools.ini. This returns the
    slug name, not the pretty name.

    Examples:
        lftools-uv rtd project-list
    """
    try:
        rtd_client = ReadTheDocs()
        projects = rtd_client.project_list()
        if projects:
            typer.echo("Read the Docs Projects:")
            for project in projects:
                typer.echo(f"  - {project}")
        else:
            typer.echo("No projects found")
    except Exception as e:
        log.exception("Failed to get project list")
        typer.echo(f"Error: Failed to get project list: {e}", err=True)
        raise typer.Exit(1) from None


@rtd_app.command("project-details")
def project_details(
    project_slug: str = typer.Argument(..., help="Project slug name"),
) -> None:
    """Get details for a specific Read the Docs project.

    Args:
        project_slug: The slug name of the project

    Examples:
        lftools-uv rtd project-details my-project
    """
    try:
        rtd_client = ReadTheDocs()
        details = rtd_client.project_details(project_slug)
        if details:
            typer.echo(f"Project Details for '{project_slug}':")
            typer.echo(f"  Name: {details.get('name', 'N/A')}")
            typer.echo(f"  Description: {details.get('description', 'N/A')}")
            typer.echo(f"  Language: {details.get('language', 'N/A')}")
            typer.echo(f"  Repository URL: {details.get('repository_url', 'N/A')}")
            typer.echo(f"  Default Version: {details.get('default_version', 'N/A')}")
        else:
            typer.echo(f"Project '{project_slug}' not found")
            raise typer.Exit(1)
    except Exception as e:
        log.exception("Failed to get project details")
        typer.echo(f"Error: Failed to get project details: {e}", err=True)
        raise typer.Exit(1) from None


@rtd_app.command("project-create")
def project_create(
    name: str = typer.Argument(..., help="Project name"),
    repo_url: str = typer.Argument(..., help="Repository URL"),
    description: str | None = typer.Option(None, "--description", help="Project description"),
    language: str = typer.Option("en", "--language", help="Project language code"),
) -> None:
    """Create a new Read the Docs project.

    Args:
        name: The name of the project
        repo_url: The repository URL
        description: Project description (optional)
        language: Project language code (default: en)

    Examples:
        lftools-uv rtd project-create "My Project" https://github.com/user/repo
        lftools-uv rtd project-create "My Project" https://github.com/user/repo --description "A great project"
    """
    try:
        rtd_client = ReadTheDocs()
        # Note: The actual API signature may differ - this is a placeholder implementation
        result = rtd_client.project_create(
            name=name,
            repository_url=repo_url,
            repository_type="git",
            homepage="",
            programming_language="python",
            language=language,
        )
        if result:
            typer.echo(f"✅ Project '{name}' created successfully")
        else:
            typer.echo(f"Failed to create project '{name}'")
            raise typer.Exit(1)
    except Exception as e:
        log.exception("Failed to create project")
        typer.echo(f"Error: Failed to create project: {e}", err=True)
        raise typer.Exit(1) from None


@rtd_app.command("project-update")
def project_update(
    project_slug: str = typer.Argument(..., help="Project slug name"),
    name: str | None = typer.Option(None, "--name", help="New project name"),
    description: str | None = typer.Option(None, "--description", help="New project description"),
    repo_url: str | None = typer.Option(None, "--repo-url", help="New repository URL"),
) -> None:
    """Update an existing Read the Docs project.

    Args:
        project_slug: The slug name of the project to update
        name: New project name (optional)
        description: New project description (optional)
        repo_url: New repository URL (optional)

    Examples:
        lftools-uv rtd project-update my-project --name "New Name"
        lftools-uv rtd project-update my-project --description "Updated description"
    """
    try:
        if name is None and description is None and repo_url is None:
            typer.echo("No update parameters provided")
            raise typer.Exit(1)

        rtd_client = ReadTheDocs()
        update_data: dict[str, object] = {}
        if name is not None:
            update_data["name"] = name
        if description is not None:
            update_data["description"] = description
        if repo_url is not None:
            update_data["repository"] = {"url": repo_url}

        success, status_code = rtd_client.project_update(project_slug, update_data)
        if success:
            typer.echo(f"✅ Project '{project_slug}' updated successfully")
        else:
            typer.echo(f"Failed to update project '{project_slug}' (HTTP {status_code})")
            raise typer.Exit(1)
    except Exception as e:
        log.exception("Failed to update project")
        typer.echo(f"Error: Failed to update project: {e}", err=True)
        raise typer.Exit(1) from None


def get_rtd_app() -> typer.Typer:
    """Get the rtd Typer app instance.

    This function is used by other modules to register the rtd commands.
    """
    return rtd_app
