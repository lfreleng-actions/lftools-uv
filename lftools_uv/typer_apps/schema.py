# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of schema verification commands."""

import logging
from pathlib import Path

import typer

from lftools_uv.schema import check_schema_file

log = logging.getLogger(__name__)

# Create the schema subcommand group
schema_app = typer.Typer(
    name="schema",
    help="Verify YAML Schema",
    add_completion=False,
)


@schema_app.callback()
def schema_callback() -> None:
    """Verify YAML Schema."""
    pass


@schema_app.command("verify")
def verify_schema(
    yamlfile: Path = typer.Argument(..., help="Release YAML file to be validated"),
    schemafile: Path = typer.Argument(..., help="SCHEMA file to validate against"),
) -> None:
    """Verify YAML Schema.

    Args:
        yamlfile: Release YAML file to be validated
        schemafile: SCHEMA file to validate against

    Examples:
        lftools-uv schema verify release.yaml schema.yaml
    """
    try:
        check_schema_file(str(yamlfile), str(schemafile))
        typer.echo(f"✅ Schema validation passed for {yamlfile}")
    except Exception as e:
        log.exception(f"Schema validation failed: {e}")
        typer.echo(f"❌ Schema validation failed: {e}", err=True)
        raise typer.Exit(1) from None


def get_schema_app() -> typer.Typer:
    """Get the schema Typer app instance.

    This function is used by other modules to register the schema commands.
    """
    return schema_app
