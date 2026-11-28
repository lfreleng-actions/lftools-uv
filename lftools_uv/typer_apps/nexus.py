# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Typer version of the legacy nexus commands."""

from os import environ
from pathlib import Path
from typing import cast

import typer

import lftools_uv.nexus.release_docker_hub as rdh
from lftools_uv.nexus import cmd as nexuscmd

NEXUS_URL_ENV = "NEXUS_URL"

nexus_app = typer.Typer(
    name="nexus",
    help="(Deprecated) Use the Nexus2 API Interface",
    add_completion=False,
)

create_app = typer.Typer(help="Create resources in Nexus.")
nexus_app.add_typer(create_app, name="create")

docker_app = typer.Typer(help="Docker repos in Nexus.")
nexus_app.add_typer(docker_app, name="docker")

SETTINGS_HELP = 'Yaml file containing "nexus" (url), "user", and "password" definitions.'
SERVER_HELP = (
    f"Nexus server URL. Can also be set as {NEXUS_URL_ENV} in the environment. "
    "This will override any URL set in settings.yaml."
)


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


# The legacy command declares PATTERN before REPO, so both front ends take
# PATTERN first and need both arguments.
@docker_app.command("list")
def docker_list(
    pattern: str = typer.Argument("*", metavar="PATTERN"),
    repo: str = typer.Argument(..., metavar="REPO"),
    server: str | None = typer.Option(None, "-s", "--server", help=SERVER_HELP),
    settings: str | None = typer.Option(None, "--settings", help=SETTINGS_HELP),
    csv: Path | None = typer.Option(
        None, "--csv", dir_okay=False, writable=True, help="Write a csv file of the search results to PATH."
    ),
) -> None:
    """List images matching the PATTERN.

    Use '*' for wildcard, or begin with '!' to search for images NOT matching
    the string.
    """
    if not server and NEXUS_URL_ENV in environ:
        server = environ[NEXUS_URL_ENV]
    images = nexuscmd.search(settings, server, repo, pattern)
    if images:
        nexuscmd.output_images(images, str(csv) if csv else None)


@docker_app.command("delete")
def docker_delete(
    pattern: str = typer.Argument("*", metavar="PATTERN"),
    repo: str = typer.Argument(..., metavar="REPO"),
    server: str | None = typer.Option(None, "-s", "--server", help=SERVER_HELP),
    settings: str | None = typer.Option(None, "--settings", help=SETTINGS_HELP),
    yes: bool = typer.Option(False, "-y", "--yes", help="Answer yes to all prompts"),
) -> None:
    """Delete all images matching the PATTERN.

    By default, prints to console only. Use '*' for wildcard, or begin with '!'
    to delete images NOT matching the string.
    """
    images = nexuscmd.search(settings, server, repo, pattern)
    if yes or typer.confirm(f"Would you like to delete all {len(images)} images?"):
        nexuscmd.delete_images(settings, server, images)


@docker_app.command("releasedockerhub")
# aislop-ignore-next-line too-many-params -- Typer binds one parameter per CLI option
def docker_releasedockerhub(
    org: str = typer.Option(..., "-o", "--org", help="Specify repository organization."),
    repo: str = typer.Option(
        "",
        "-r",
        "--repo",
        help="Only repos containing this string will be selected. Default set to blank string, which is every repo.",
    ),
    exact: bool = typer.Option(
        False, "-e", "--exact", help="Match the exact repo name. If used, --repo parameter can not be empty."
    ),
    summary: bool = typer.Option(False, "-s", "--summary", help="Prints a summary of missing docker tags."),
    verbose: bool = typer.Option(False, "-v", "--verbose", help="Prints all collected repo/tag information."),
    copy: bool = typer.Option(False, "-c", "--copy", help="Copy missing tags from Nexus3 repos to Docker Hub repos."),
    progbar: bool = typer.Option(False, "-p", "--progbar", help="Display a progress bar for the time consuming jobs."),
    repofile: bool = typer.Option(
        False,
        "-f",
        "--repofile",
        help=(
            "Repo Name is a file name, which contains one repo per row."
            " Syntax: 'Nexus3 docker.release repo'; 'dockerhub dockername'."
            " Sample: onap/msb/msb_apigateway; onap/msb-msb_apigateway"
        ),
    ),
    version_regexp: str = typer.Option(
        "",
        "-x",
        "--version_regexp",
        "--version-regexp",
        help=(
            "Specify a file which contains a regexp expression to validate version number."
            r" File sample: ^\d+.\d+.\d+$"
        ),
    ),
) -> None:
    """Find missing repos in Docker Hub, Copy from Nexus3.

    Will by default list all missing repos in Docker Hub, compared to Nexus3.
    If -c (--copy) is provided, it will copy the repos from Nexus3 to Docker Hub.
    """
    rdh.start_point(org, repo, exact, summary, verbose, copy, progbar, repofile, version_regexp)
