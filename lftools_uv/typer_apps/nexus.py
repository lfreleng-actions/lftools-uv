# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Typer version of the legacy nexus commands."""

from os import environ
from typing import cast

import typer

from lftools_uv.nexus import cmd as nexuscmd

NEXUS_URL_ENV = "NEXUS_URL"

nexus_app = typer.Typer(
    name="nexus",
    help="(Deprecated) Use the Nexus2 API Interface",
    add_completion=False,
)

create_app = typer.Typer(help="Create resources in Nexus.")
nexus_app.add_typer(create_app, name="create")


@nexus_app.callback()
def nexus_callback() -> None:
    """(Deprecated) Use the Nexus2 API Interface.

    Provide an interface to Nexus.
    """


@nexus_app.command("release")
def release(
    repos: list[str] = typer.Argument(..., help="Staging repository IDs to release"),
    verify: bool = typer.Option(False, "-v", "--verify-only", help="Only verify the repositories"),
    server: str | None = typer.Option(
        None,
        "-s",
        "--server",
        help=(
            f"Nexus server URL. Can also be set as {NEXUS_URL_ENV} in the environment. "
            "This will override any URL set in settings.yaml."
        ),
    ),
    max_wait: int = typer.Option(
        60,
        "--max-wait",
        min=1,
        show_default=True,
        help="Minutes to wait for Nexus to release each repository before giving up.",
    ),
) -> None:
    """Release one or more staging repositories."""
    if not server and NEXUS_URL_ENV in environ:
        server = environ[NEXUS_URL_ENV]
    nexuscmd.release_staging_repos(tuple(repos), verify, server or "", max_wait=max_wait)


@nexus_app.command("reorder-staged-repos")
def reorder_staged_repos(
    settings: str = typer.Option(..., "-s", "--settings"),
) -> None:
    """Reorder staging repositories in Nexus.

    Reorders staging repositories in Nexus such that the newest repository gets
    priority in the aggregate repo.
    """
    nexuscmd.reorder_staged_repos(settings)


@create_app.command("repo")
def create_repo(
    configfile: str = typer.Option(
        ...,
        "-c",
        "--configfile",
        help="Repo config file for how the Nexus repository should be created.",
    ),
    settings: str | None = typer.Option(
        None, "-s", "--settings", help="Optional config file containing administrative settings."
    ),
    url: str | None = typer.Option(
        None,
        "-u",
        "--url",
        help=(
            f"Nexus server URL. In the format https:// Can also be set as {NEXUS_URL_ENV} in the environment. "
            "This will override any URL set in settings.yaml."
        ),
    ),
) -> None:
    """Create a Nexus repository as defined by a repo-config.yaml file."""
    # create_repos annotates url as str, yet the legacy command also passes
    # None when --url is absent; it then takes the URL from --settings.
    nexuscmd.create_repos(configfile, settings, cast(str, url))


@create_app.command("role")
def create_role(
    config: str = typer.Option(
        ..., "-c", "--config", help="Role config file for how the Nexus role should be created."
    ),
    settings: str = typer.Option(..., "-s", "--settings", help="Config file containing administrative settings."),
) -> None:
    """Create a Nexus role as defined by a role-config.yaml file."""
    nexuscmd.create_roles(config, settings)
