# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of signing commands."""

import logging
import subprocess
from pathlib import Path

import typer

_MSG_SIGN_NOT_FOUND = "'sign' command not found in PATH"
_MSG_SIGN_NOT_FOUND_LONG = "Error: 'sign' command not found in PATH. Please ensure it's installed."


log = logging.getLogger(__name__)

sign_app = typer.Typer(
    name="sign",
    help="GPG or Sigul sign files",
    add_completion=False,
)


@sign_app.callback()
def sign_callback() -> None:
    """GPG or Sigul sign files."""
    pass


@sign_app.command("dir")
def directory(
    directory: Path = typer.Argument(..., help="Directory containing files to sign"),
    mode: str = typer.Option("parallel", "-m", "--mode", help="Signing mode: serial or parallel"),
) -> None:
    """GPG signs all of the files in a directory.

    Args:
        directory: Directory path containing files to sign
        mode: Signing mode (serial or parallel)

    Examples:
        lftools-uv sign dir /path/to/files
        lftools-uv sign dir /path/to/files --mode serial
    """
    if not directory.is_dir():
        typer.echo(f"Error: {directory} is not a valid directory", err=True)
        raise typer.Exit(1)

    try:
        subprocess.run(["sign", "dir", str(directory), mode], check=True, capture_output=False)
        typer.echo(f"✅ Successfully signed files in {directory} using {mode} mode")
    except subprocess.CalledProcessError as e:
        log.exception("Signing failed with exit code %s", e.returncode)
        typer.echo(f"Error: Signing failed with exit code {e.returncode}", err=True)
        raise typer.Exit(e.returncode) from None
    except FileNotFoundError:
        log.error(_MSG_SIGN_NOT_FOUND)
        typer.echo(_MSG_SIGN_NOT_FOUND_LONG, err=True)
        raise typer.Exit(127) from None


@sign_app.command("git-tag")
def git_tag(
    tag: str = typer.Argument(..., help="Git tag to sign"),
) -> None:
    """GPG signs a git tag.

    Args:
        tag: The git tag to sign

    Examples:
        lftools-uv sign git-tag v1.0.0
        lftools-uv sign git-tag release-1.2.3
    """
    try:
        subprocess.run(["sign", "git-tag", tag], check=True, capture_output=False)
        typer.echo(f"✅ Successfully signed git tag: {tag}")
    except subprocess.CalledProcessError as e:
        log.exception("Git tag signing failed with exit code %s", e.returncode)
        typer.echo(f"Error: Git tag signing failed with exit code {e.returncode}", err=True)
        raise typer.Exit(e.returncode) from None
    except FileNotFoundError:
        log.error(_MSG_SIGN_NOT_FOUND)
        typer.echo(_MSG_SIGN_NOT_FOUND_LONG, err=True)
        raise typer.Exit(127) from None


@sign_app.command("nexus")
def nexus(
    nexus_repo_url: str = typer.Argument(..., help="Nexus repository URL"),
) -> None:
    """GPG signs artifacts in a Nexus repository.

    Args:
        nexus_repo_url: The Nexus repository URL to sign artifacts from

    Examples:
        lftools-uv sign nexus https://nexus.example.com/repository/releases
    """
    try:
        subprocess.run(["sign", "nexus", nexus_repo_url], check=True, capture_output=False)
        typer.echo(f"✅ Successfully signed Nexus artifacts at: {nexus_repo_url}")
    except subprocess.CalledProcessError as e:
        log.exception("Nexus signing failed with exit code %s", e.returncode)
        typer.echo(f"Error: Nexus signing failed with exit code {e.returncode}", err=True)
        raise typer.Exit(e.returncode) from None
    except FileNotFoundError:
        log.error(_MSG_SIGN_NOT_FOUND)
        typer.echo(_MSG_SIGN_NOT_FOUND_LONG, err=True)
        raise typer.Exit(127) from None


def get_sign_app() -> typer.Typer:
    """Get the sign Typer app instance.

    This function is used by other modules to register the sign commands.
    """
    return sign_app
