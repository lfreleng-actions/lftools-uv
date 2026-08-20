# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Utility commands for lftools-uv Typer CLI.

This module contains utility commands that have been migrated from the
Click-based CLI. It serves as a pilot for the Typer migration.
"""

import logging

import typer

from lftools_uv import helpers

log = logging.getLogger(__name__)

utils_app = typer.Typer(
    name="utils",
    help="Tools to make life easier",
    add_completion=False,
)


@utils_app.callback()
def utils_callback() -> None:
    """Tools to make life easier."""
    pass


@utils_app.command("passgen")
def password_generator(
    ctx: typer.Context,
    length: int | None = typer.Argument(None, help="Length of the password to generate (default: 12)"),
) -> None:
    """Generate a complex password.

    Generates a password using a mix of letters, digits, and punctuation
    characters. The default length is 12 characters if not specified.

    Examples:
        lftools-uv utils passgen        # Generate 12-character password
        lftools-uv utils passgen 16     # Generate 16-character password
    """
    # Set default length if not provided
    if length is None:
        length = 12

    if length <= 0:
        typer.echo("Error: Password length must be greater than 0", err=True)
        raise typer.Exit(1)

    if length > 256:
        typer.echo("Error: Password length cannot exceed 256 characters", err=True)
        raise typer.Exit(1)

    try:
        password = helpers.generate_password(length)
        typer.echo(password)
    except Exception as e:
        log.exception("Failed to generate password")
        typer.echo(f"Error: Failed to generate password: {e}", err=True)
        raise typer.Exit(1) from None


def get_utils_app() -> typer.Typer:
    """Get the utils Typer app instance.

    This function is used by other modules to register the utils commands.
    """
    return utils_app
