# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""CLI main for lftools-uv."""

import configparser
import getpass
import logging

import click

# input is built-in in Python 3, no import needed
from lftools_uv import config as conf
from lftools_uv.cli.config import config_sys
from lftools_uv.cli.dco import dco
from lftools_uv.cli.deploy import deploy
from lftools_uv.cli.gerrit import gerrit_cli
from lftools_uv.cli.github_cli import github_cli
from lftools_uv.cli.infofile import infofile
from lftools_uv.cli.jenkins import jenkins_cli
from lftools_uv.cli.lfidapi import lfidapi
from lftools_uv.cli.license import license
from lftools_uv.cli.nexus import nexus
from lftools_uv.cli.nexus2 import nexus_two
from lftools_uv.cli.nexus3 import nexus_three
from lftools_uv.cli.rtd import rtd
from lftools_uv.cli.schema import schema
from lftools_uv.cli.sign import sign
from lftools_uv.cli.state import AppState
from lftools_uv.cli.utils import utils
from lftools_uv.cli.version import version

log = logging.getLogger(__name__)


@click.group()
@click.option("--debug", envvar="DEBUG", is_flag=True, default=False)
@click.option("--password", envvar="LFTOOLS_PASSWORD", default=None)
@click.option("--username", envvar="LFTOOLS_USERNAME", default=None)
@click.option("-i", "--interactive", is_flag=True, default=False)
@click.pass_context
@click.version_option()
def cli(ctx, debug, interactive, password, username):
    """CLI entry point for lftools-uv."""
    if debug:
        logging.getLogger("").setLevel(logging.DEBUG)

    if ctx.obj is None:
        ctx.obj = {}
    # Initialize or reuse structured application state
    state = ctx.obj.get("state") or AppState()
    state.debug = debug
    state.interactive = interactive
    ctx.obj["state"] = state
    ctx.obj["DEBUG"] = debug  # Backward compatibility for legacy access
    log.debug("DEBUG mode enabled.")

    # Start > Credentials
    if username is None:
        if interactive:
            username = input("Username: ")
        else:
            try:
                username = conf.get_setting("global", "username")
            except (configparser.NoOptionError, configparser.NoSectionError):
                username = None

    if password is None:
        if interactive:
            password = getpass.getpass("Password: ")
        else:
            try:
                password = conf.get_setting("global", "password")
            except (configparser.NoOptionError, configparser.NoSectionError):
                password = None

    state.update_credentials(username, password)
    ctx.obj["username"] = state.username  # legacy compatibility
    ctx.obj["password"] = state.password  # legacy compatibility
    # End > Credentials
    log.debug("Initialized state: %s", ctx.obj["state"].describe())


cli.add_command(config_sys)
cli.add_command(deploy)
cli.add_command(dco)
cli.add_command(gerrit_cli, name="gerrit")
cli.add_command(github_cli, name="github")
cli.add_command(infofile)
cli.add_command(jenkins_cli, name="jenkins")
cli.add_command(license)
cli.add_command(nexus)
cli.add_command(nexus_two)
cli.add_command(nexus_three)
cli.add_command(rtd)
cli.add_command(schema)
cli.add_command(lfidapi)
cli.add_command(sign)
cli.add_command(utils)
cli.add_command(version)

try:
    from lftools_uv.cli.ldap_cli import ldap_cli

    cli.add_command(ldap_cli, name="ldap")
except ImportError:
    from lftools_uv.cli.no_cmd import no_ldap as ldap_cli

    cli.add_command(ldap_cli, name="ldap")


try:
    from lftools_uv.openstack.cmd import openstack

    cli.add_command(openstack)
except ImportError:
    from lftools_uv.openstack.no_cmd import openstack

    cli.add_command(openstack)


def main():
    """Entry point for lftools-uv CLI."""
    import os

    # Check if legacy Click CLI is explicitly requested
    if os.environ.get("LEGACY_CLI") == "1":
        cli(obj={})
    else:
        # Default to modern Typer CLI
        try:
            from lftools_uv.cli_app import app as typer_app

            typer_app()
        except ImportError as e:
            log.exception("Failed to import Typer CLI: %s", e)
            log.info("Falling back to legacy Click CLI")
            cli(obj={})
        except Exception as e:
            # For runtime errors, don't fall back to avoid duplicate error messages
            # Both Typer and Click CLIs will fail with the same underlying issues
            log.debug("Typer CLI encountered a runtime error: %s", e)
            # Re-raise the exception to avoid falling back and duplicating errors
            raise


if __name__ == "__main__":
    main()
