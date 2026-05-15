# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Root Typer application for lftools-uv.

This module defines the main Typer app instance and the global callback
that handles initialization, state management, and credential handling.
"""

import configparser
import logging
from importlib.metadata import version

import typer

from lftools_uv import config as conf
from lftools_uv.cli.state import AppState
from lftools_uv.typer_apps.config import config_app
from lftools_uv.typer_apps.dco import dco_app
from lftools_uv.typer_apps.deploy import deploy_app
from lftools_uv.typer_apps.gerrit import gerrit_app
from lftools_uv.typer_apps.github_cli import github_app
from lftools_uv.typer_apps.infofile import get_infofile_app
from lftools_uv.typer_apps.jenkins import jenkins_app
from lftools_uv.typer_apps.lfidapi import get_lfidapi_app
from lftools_uv.typer_apps.license import get_license_app
from lftools_uv.typer_apps.nexus2 import nexus2_app
from lftools_uv.typer_apps.nexus3 import nexus3_app
from lftools_uv.typer_apps.openstack import get_openstack_app
from lftools_uv.typer_apps.rtd import get_rtd_app
from lftools_uv.typer_apps.schema import get_schema_app
from lftools_uv.typer_apps.sign import get_sign_app
from lftools_uv.typer_apps.utils import get_utils_app
from lftools_uv.typer_apps.version import get_version_app
from lftools_uv.typer_apps.zulip import zulip_app

log = logging.getLogger(__name__)


def version_callback(value: bool) -> None:
    """Show version and exit."""
    if value:
        try:
            app_version = version("lftools-uv")
            typer.echo(f"lftools-uv {app_version}")
        except Exception:
            typer.echo("lftools-uv version unknown")
        raise typer.Exit()


# Create the main Typer app
app = typer.Typer(
    name="lftools-uv",
    help="Linux Foundation Release Engineering Tools (Typer-based)",
    add_completion=False,
    rich_markup_mode="markdown",
)


@app.callback()
def main(
    ctx: typer.Context,
    version_flag: bool | None = typer.Option(
        None, "--version", callback=version_callback, is_eager=True, help="Show version and exit"
    ),
    debug: bool = typer.Option(False, "--debug", envvar="DEBUG", help="Enable debug logging"),
    username: str | None = typer.Option(
        None, "--username", envvar="LFTOOLS_USERNAME", help="Username for authentication"
    ),
    password: str | None = typer.Option(
        None, "--password", envvar="LFTOOLS_PASSWORD", help="Password for authentication", hide_input=True
    ),
    interactive: bool = typer.Option(False, "--interactive", "-i", help="Prompt for missing credentials"),
) -> None:
    """Linux Foundation Release Engineering Tools.

    This is the Typer-based version of lftools-uv. Enable it by setting
    the environment variable LFTOOLS_CLI_V2=1.
    """
    # Configure debug logging
    if debug:
        logging.getLogger("").setLevel(logging.DEBUG)
        log.debug("DEBUG mode enabled.")

    # Initialize application state
    if ctx.obj is None:
        ctx.obj = {}

    state = AppState()
    state.debug = debug
    state.interactive = interactive
    ctx.obj["state"] = state

    # Legacy compatibility - maintain the old context structure
    ctx.obj["DEBUG"] = debug

    # Handle credentials
    if username is None:
        if interactive:
            username = typer.prompt("Username")
        else:
            try:
                setting_value = conf.get_setting("global", "username")
                username = setting_value if isinstance(setting_value, str) else None
            except (configparser.NoOptionError, configparser.NoSectionError):
                username = None

    if password is None:
        if interactive:
            password = typer.prompt("Password", hide_input=True)
        else:
            try:
                setting_value = conf.get_setting("global", "password")
                password = setting_value if isinstance(setting_value, str) else None
            except (configparser.NoOptionError, configparser.NoSectionError):
                password = None

    # Update state with credentials
    state.update_credentials(username, password)

    # Legacy compatibility - maintain old context keys
    ctx.obj["username"] = state.username
    ctx.obj["password"] = state.password

    log.debug("Initialized state: %s", state.describe())


# Register subcommands
app.add_typer(get_utils_app(), name="utils")
app.add_typer(get_version_app(), name="version")
app.add_typer(config_app, name="config")
app.add_typer(dco_app, name="dco")
app.add_typer(deploy_app, name="deploy")
app.add_typer(github_app, name="github")
app.add_typer(gerrit_app, name="gerrit")
app.add_typer(jenkins_app, name="jenkins")
app.add_typer(nexus2_app, name="nexus2")
app.add_typer(nexus3_app, name="nexus3")
app.add_typer(get_openstack_app(), name="openstack")
app.add_typer(get_schema_app(), name="schema")
app.add_typer(get_lfidapi_app(), name="lfidapi")
app.add_typer(get_license_app(), name="license")
app.add_typer(get_sign_app(), name="sign")
app.add_typer(get_infofile_app(), name="infofile")
app.add_typer(get_rtd_app(), name="rtd")
app.add_typer(zulip_app, name="zulip")


def get_app() -> typer.Typer:
    """Get the main Typer app instance.

    This function is used by cli_app.py to expose the app.
    """
    return app
