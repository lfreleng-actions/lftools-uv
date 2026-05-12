# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of version bump commands for Maven based projects."""

import logging
import os
import subprocess

import typer

_MSG_VERSION_NOT_FOUND = "'version' command not found in PATH"
_MSG_VERSION_NOT_FOUND_LONG = "Error: 'version' command not found in PATH. Please ensure it's installed."


log = logging.getLogger(__name__)

# Create the version subcommand group
version_app = typer.Typer(
    name="version",
    help="Version bump script for Maven based projects",
    add_completion=False,
)


@version_app.callback()
def version_callback() -> None:
    """Version bump script for Maven based projects.

    In general, versions should be: <major>.<minor>.<micro>[-<human-readable-tag>]

    **Rules:**
    - Human readable tag should not have any dots in it
    - SNAPSHOT is used for development

    **Scenarios:**

    - **master before release**: x.y.z-SNAPSHOT (or x.y-SNAPSHOT in which case we treat it as x.y.0-SNAPSHOT)
    - **at release**: x.y.z-Helium
    - **stable/helium after release**: x.y.(z+1)-SNAPSHOT
    - **master after release**: x.(y+1).0-SNAPSHOT
    - **Autorelease on master**: <human-readable-tag> is "PreLithium-<date>"
    - **Autorelease on stable/helium**: <human-readable-tag> is "PreHeliumSR1-<date>"
    - **Release job on master**: <human-readable-tag> is "Lithium"
    - **Release job on stable/helium**: <human-readable-tag> is "HeliumSR1"

    Some things have a date for a version, e.g., 2014.09.24.4

    - We treat this as YYYY.MM.DD.<minor>
    - Note that all such dates currently in ODL are in YANG tools
    - They are all now YYYY.MM.DD.7 since 7 is the minor version for yangtools
    """
    pass


@version_app.command("bump")
def bump(
    ctx: typer.Context,
    release_tag: str = typer.Argument(..., help="Release tag to use for version bumping"),
) -> None:
    """Version bump pom files in a Maven project by x.(y+1).z or x.y.(z+1).

    This script performs version bumping as follows:

    1. Change YYYY.MM.DD.y.z-SNAPSHOT to YYYY.MM.DD.(y+1).0-SNAPSHOT
    2. Change YYYY.MM.DD.y.z-Helium to YYMMDD.y.(z+1)-SNAPSHOT
    3. Change x.y.z-SNAPSHOT versions to x.(y+1).0-SNAPSHOT
    4. Change x.y.z-RELEASE_TAG versions to x.y.(z+1)-SNAPSHOT

    Args:
        release_tag: The release tag to use for version bumping

    Examples:
        lftools-uv version bump "Lithium-SR1"
        lftools-uv version bump "2024.01.15"
    """
    try:
        subprocess.run(["version", "bump", release_tag], check=True, capture_output=False)
        typer.echo(f"Version bump completed successfully for release tag: {release_tag}")
    except subprocess.CalledProcessError as e:
        log.exception("Version bump failed with exit code %s", e.returncode)
        typer.echo(f"Error: Version bump failed with exit code {e.returncode}", err=True)
        raise typer.Exit(e.returncode) from None
    except FileNotFoundError:
        log.error(_MSG_VERSION_NOT_FOUND)
        typer.echo(_MSG_VERSION_NOT_FOUND_LONG, err=True)
        raise typer.Exit(127) from None


@version_app.command("release")
def release(
    ctx: typer.Context,
    release_tag: str = typer.Argument(..., help="Release tag to replace SNAPSHOT versions"),
) -> None:
    """Version bump pom files in a Maven project from SNAPSHOT to RELEASE_TAG.

    Searches poms for all instances of SNAPSHOT version and changes it to
    RELEASE_TAG.

    Args:
        release_tag: The release tag to replace SNAPSHOT versions with

    Examples:
        lftools-uv version release "Lithium"
        lftools-uv version release "1.2.3"
    """
    try:
        subprocess.run(["version", "release", release_tag], check=True, capture_output=False)
        typer.echo(f"Version release completed successfully for tag: {release_tag}")
    except subprocess.CalledProcessError as e:
        log.exception("Version release failed with exit code %s", e.returncode)
        typer.echo(f"Error: Version release failed with exit code {e.returncode}", err=True)
        raise typer.Exit(e.returncode) from None
    except FileNotFoundError:
        log.error(_MSG_VERSION_NOT_FOUND)
        typer.echo(_MSG_VERSION_NOT_FOUND_LONG, err=True)
        raise typer.Exit(127) from None


@version_app.command("patch")
def patch(
    ctx: typer.Context,
    release_tag: str = typer.Argument(..., help="Release tag to use for version bumping after patching"),
    patch_dir: str = typer.Argument(..., help="Directory containing git.bundle patches to apply"),
    project: str = typer.Option("OpenDaylight", "--project", help="Project name to use when tagging"),
) -> None:
    """Patch a project with git.bundles and then version bump.

    Applies git.bundle patches to the project and then performs a version bump
    using RELEASE_TAG in order to version bump by x.y.(z+1)-SNAPSHOT.

    Args:
        release_tag: Release tag to use for version bumping after patching
        patch_dir: Directory containing git.bundle patches to apply
        project: Project name to use when tagging (default: OpenDaylight)

    Examples:
        lftools-uv version patch "Lithium-SR1" /path/to/patches
        lftools-uv version patch "1.2.3" /path/to/patches --project "MyProject"
    """
    # Validate patch directory exists
    if not os.path.isdir(patch_dir):
        log.error(f"{patch_dir} is not a valid directory.")
        typer.echo(f"Error: {patch_dir} is not a valid directory.", err=True)
        raise typer.Exit(404)

    try:
        subprocess.run(["version", "patch", release_tag, patch_dir, project], check=True, capture_output=False)
        typer.echo(f"Version patch completed successfully for release tag: {release_tag}")
    except subprocess.CalledProcessError as e:
        log.exception("Version patch failed with exit code %s", e.returncode)
        typer.echo(f"Error: Version patch failed with exit code {e.returncode}", err=True)
        raise typer.Exit(e.returncode) from None
    except FileNotFoundError:
        log.error(_MSG_VERSION_NOT_FOUND)
        typer.echo(_MSG_VERSION_NOT_FOUND_LONG, err=True)
        raise typer.Exit(127) from None


def get_version_app() -> typer.Typer:
    """Get the version Typer app instance.

    This function is used by other modules to register the version commands.
    """
    return version_app
