# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of license scanning commands."""

import logging
from pathlib import Path

import typer

from lftools_uv.license import check_license, check_license_directory

log = logging.getLogger(__name__)

# Create the license subcommand group
license_app = typer.Typer(
    name="license",
    help="Scan code for license headers",
    add_completion=False,
)


@license_app.callback()
def license_callback() -> None:
    """Scan code for license headers."""
    pass


@license_app.command("check")
def check_command(
    source: Path = typer.Argument(..., help="Source file or directory to check"),
    license_file: str = typer.Option(
        "license-header.txt", "-l", "--license", help="License header file to compare against"
    ),
) -> None:
    """Check files for missing license headers.

    Does not care about line formatting of the license as long as all of the
    text is there and in the correct order.

    Note: This code only supports '#' comments for license headers.

    Args:
        source: Source file or directory to check for license headers
        license_file: License header file to compare against

    Examples:
        lftools-uv license check src/
        lftools-uv license check myfile.py --license custom-header.txt
    """
    try:
        if source.is_file():
            result = check_license(str(source), license_file)
            if result:
                typer.echo(f"✅ License header found in {source}")
            else:
                typer.echo(f"❌ License header missing in {source}", err=True)
                raise typer.Exit(1) from None
        elif source.is_dir():
            # check_license_directory returns None but may exit with code 1 if issues found
            # We need to catch the SystemExit and handle it properly
            try:
                check_license_directory(license_file, str(source))
                typer.echo(f"✅ All files in {source} have proper license headers")
            except SystemExit as e:
                if e.code == 1:
                    typer.echo(f"❌ License header issues found in {source}", err=True)
                    raise typer.Exit(1) from None
                else:
                    raise
        else:
            typer.echo(f"Error: {source} is not a valid file or directory", err=True)
            raise typer.Exit(1) from None
    except Exception as e:
        log.exception("License check failed")
        typer.echo(f"Error: License check failed: {e}", err=True)
        raise typer.Exit(1) from None


def get_license_app() -> typer.Typer:
    """Get the license Typer app instance.

    This function is used by other modules to register the license commands.
    """
    return license_app
