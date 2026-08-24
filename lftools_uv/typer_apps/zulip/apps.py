# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer application objects for the Zulip command tree.

Owns ``zulip_app``, its top-level callback, and the four command-group
apps mounted beneath it. The command modules import these objects to
register themselves; the order in which the package imports those
modules is what fixes the order commands appear in ``--help``.
"""

from __future__ import annotations

from pathlib import Path

import typer

from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.helpers import MISSING_EXTRA_MESSAGE, zuliprc_callback

zulip_app = typer.Typer(
    name="zulip",
    help="Manage Zulip channels, users, and groups.",
    no_args_is_help=True,
)


@zulip_app.callback()
def zulip_callback(
    ctx: typer.Context,
    zuliprc: Path | None = typer.Option(
        None,
        "--zuliprc",
        help="Path to a zuliprc configuration file (FR-011 precedence applies).",
        callback=zuliprc_callback,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
) -> None:
    """Top-level callback for the Zulip command group.

    When the optional ``zulip`` extra is not installed, abort
    immediately with the canonical FR-022 error so that every
    subcommand presents the same guidance to the user.
    """
    ctx.obj = {
        **(ctx.obj or {}),
        "zuliprc": zuliprc,
        "json_output": json_output,
    }
    # Allow ``--help`` (including nested subcommand help) to render even
    # when the optional extra is missing. Typer sets resilient_parsing
    # while it is walking the command tree for help discovery.
    if ctx.resilient_parsing:
        return
    if ctx.invoked_subcommand is None:
        # Help / no-args path — let Typer print help without raising.
        return
    if not zulip_cli.zulip_available():
        typer.echo(MISSING_EXTRA_MESSAGE, err=True)
        raise typer.Exit(code=1)


channel_app = typer.Typer(
    name="channel",
    help="Manage Zulip channels.",
    no_args_is_help=True,
)
zulip_app.add_typer(channel_app, name="channel")

folder_app = typer.Typer(
    name="folder",
    help="Manage Zulip channel folders.",
    no_args_is_help=True,
)
zulip_app.add_typer(folder_app, name="folder")


user_app = typer.Typer(
    name="user",
    help="Inspect Zulip users.",
    no_args_is_help=True,
)
zulip_app.add_typer(user_app, name="user")


group_app = typer.Typer(
    name="group",
    help="List Zulip user groups.",
    no_args_is_help=True,
)
zulip_app.add_typer(group_app, name="group")
