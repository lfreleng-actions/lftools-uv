# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands listing Jenkins build nodes."""

import logging

import typer

from lftools_uv.output import echo

log = logging.getLogger(__name__)

nodes_app = typer.Typer(help="Find information about builders connected to Jenkins Master.")


# Nodes subcommands
def offline_str(status):
    """Convert the offline node status from a boolean to a string."""
    if status:
        return "Offline"
    return "Online"


@nodes_app.command("list")
def nodes_list(ctx: typer.Context) -> None:
    """List Jenkins nodes."""
    try:
        jenkins = ctx.obj["jenkins"]
        node_list = jenkins.server.get_nodes()

        for node in node_list:
            echo(f"{node['name']} [{offline_str(node['offline'])}]")
    except Exception:
        log.exception("Failed to list nodes")
        raise typer.Exit(1) from None
