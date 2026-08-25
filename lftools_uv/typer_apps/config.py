# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer CLI interface for config subsystem."""

__author__ = "Thanh Ha"

import configparser
import logging

import typer

from lftools_uv import config
from lftools_uv.output import echo

log = logging.getLogger(__name__)

config_app = typer.Typer(name="config", help="Configuration subsystem.")


@config_app.callback()
def config_callback() -> None:
    """Configuration subsystem callback."""
    pass


@config_app.command(name="get")
def get_setting(
    section: str = typer.Argument(..., help="Configuration section name"),
    option: str | None = typer.Argument(None, help="Configuration option name (optional)"),
) -> None:
    """Print section or setting from config file."""
    try:
        result = config.get_setting(section, option)
    except (configparser.NoOptionError, configparser.NoSectionError) as e:
        log.exception(e)
        raise typer.Exit(1) from None

    if isinstance(result, list):
        for i in result:
            echo(f"{i}: {config.get_setting(section, i)}")
    else:
        echo(result)


@config_app.command(name="set")
def set_setting(
    section: str = typer.Argument(..., help="Configuration section name"),
    option: str = typer.Argument(..., help="Configuration option name"),
    value: str = typer.Argument(..., help="Configuration option value"),
) -> None:
    """Set a setting in the config file."""
    log.debug(f"Set config\n[{section}]\n{option}:{value}")
    config.set_setting(section, option, value)
