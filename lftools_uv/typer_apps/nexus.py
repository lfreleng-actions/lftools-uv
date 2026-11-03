# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Typer version of the legacy nexus commands."""

from os import environ

import typer

from lftools_uv.nexus import cmd as nexuscmd

NEXUS_URL_ENV = "NEXUS_URL"

nexus_app = typer.Typer(
    name="nexus",
    help="(Deprecated) Use the Nexus2 API Interface",
    add_completion=False,
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
