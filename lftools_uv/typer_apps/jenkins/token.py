# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands managing Jenkins API tokens."""

import configparser
import logging
import os

import requests
import typer

from lftools_uv import config as lftools_cfg
from lftools_uv.jenkins.token import get_token
from lftools_uv.output import echo

log = logging.getLogger(__name__)

_MSG_CREDS_NOT_SET = "Username or password not set."

token_app = typer.Typer(help="Get API token.")


# Token subcommands
def _require_jjb_ini(config):
    if not os.path.isfile(config):
        log.error("jenkins_jobs.ini not found in any of the search paths. Please provide one before proceeding.")
        raise typer.Exit(1)


@token_app.command("change")
def token_change(
    ctx: typer.Context,
    name: str = typer.Option("token-created-by-lftools", "--name", help="set token name"),
) -> None:
    """Generate a new API token."""
    try:
        jenkins = ctx.obj["jenkins"]
        username = ctx.obj["username"]
        password = ctx.obj["password"]

        if not username or not password:
            log.error(_MSG_CREDS_NOT_SET)
            raise typer.Exit(1)

        echo(get_token(name, jenkins.url, username=username, password=password, change=True))
    except Exception:
        log.exception("Failed to change token")
        raise typer.Exit(1) from None


@token_app.command("init")
def token_init(
    ctx: typer.Context,
    name: str = typer.Argument(..., help="Server name for configuration"),
    url: str = typer.Argument(..., help="Jenkins server URL"),
) -> None:
    """Initialize jenkins_jobs.ini config for new server section."""
    try:
        jenkins = ctx.obj["jenkins"]
        username = ctx.obj["username"]
        password = ctx.obj["password"]

        if not username or not password:
            log.error(_MSG_CREDS_NOT_SET)
            raise typer.Exit(1)

        _require_jjb_ini(jenkins.config_file)

        config = configparser.ConfigParser()
        config.read(jenkins.config_file)

        token = get_token(name, url, username, password, change=True)
        try:
            config.add_section(name)
        except configparser.DuplicateSectionError as e:
            log.exception(e)
            raise typer.Exit(1) from None

        config.set(name, "url", url)
        username_setting = lftools_cfg.get_setting("global", "username")
        username_str = username_setting if isinstance(username_setting, str) else str(username_setting)
        config.set(name, "user", username_str)
        # Ensure token is a string for config.set
        token_str = str(token) if token is not None else ""
        config.set(name, "password", token_str)

        with open(jenkins.config_file, "w") as configfile:
            config.write(configfile)
    except Exception:
        log.exception("Failed to initialize token")
        raise typer.Exit(1) from None


@token_app.command("print")
def token_print(ctx: typer.Context) -> None:
    """Print current API token."""
    try:
        jenkins = ctx.obj["jenkins"]
        username = ctx.obj["username"]
        password = ctx.obj["password"]

        if not username or not password:
            log.error(_MSG_CREDS_NOT_SET)
            raise typer.Exit(1)

        echo(get_token("token", jenkins.url, username, password))
    except Exception:
        log.exception("Failed to print token")
        raise typer.Exit(1) from None


@token_app.command("reset")
def token_reset(
    ctx: typer.Context,
    servers: list[str] | None = typer.Argument(None, help="Server names to reset tokens for"),
) -> None:
    """Regenerate API tokens for configurations in jenkins_jobs.ini.

    This command has 2 modes to reset API tokens:

    1. Single-server: Resets the API token and returns the new token value.
    2. Multi-server: Resets the API token for a provided list of servers and
       returns a summary of the outcome.

    If the server parameter is NOT passed then all servers listed in the
    configuration file will be reset via multi-server mode.
    """
    try:
        jenkins = ctx.obj["jenkins"]
        username = ctx.obj["username"]
        password = ctx.obj["password"]

        if not username or not password:
            log.error(_MSG_CREDS_NOT_SET)
            raise typer.Exit(1)

        _require_jjb_ini(jenkins.config_file)

        def _reset_key(config, server):
            url = config.get(server, "url")

            try:
                token = get_token("token-created-by-lftools", url, username=username, password=password, change=True)
                config.set(server, "password", token)
                with open(jenkins.config_file, "w") as configfile:
                    config.write(configfile)
                return token
            except requests.exceptions.ConnectionError:
                return None

        fail = 0
        success = 0
        config = configparser.ConfigParser()
        config.read(jenkins.config_file)

        if not servers or len(servers) == 0:
            cfg_sections = config.sections()
        elif len(servers) == 1:
            key = _reset_key(config, servers[0])
            echo(key)
            return
        else:
            cfg_sections = list(servers)

        for section in cfg_sections:
            if not config.has_option(section, "url"):
                log.debug("Section does not contain a url, skipping...")
                continue

            log.info(f"Resetting API key for {section}")
            if _reset_key(config, section):
                success += 1
            else:
                fail += 1
                log.error(f"Failed to reset API key for {section}")

        log.info("Update configurations complete.")
        log.info(f"Success: {success}")
        log.info(f"Failed: {fail}")
    except Exception:
        log.exception("Failed to reset tokens")
        raise typer.Exit(1) from None
