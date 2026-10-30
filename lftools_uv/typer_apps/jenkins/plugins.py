# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands inspecting Jenkins plugins."""

import logging

import typer

from lftools_uv.jenkins.plugins import AdvisoriesError, fetch_warnings, vulnerable_plugins
from lftools_uv.output import echo

log = logging.getLogger(__name__)

plugins_app = typer.Typer(help="Inspect Jenkins plugins on the server.")


# Plugins subcommands
def checkmark(truthy):
    """Return a UTF-8 Checkmark or Cross depending on the truthiness of the argument."""
    if truthy:
        return "\u2713"
    return "\u2717"


def print_plugin(plugin, namefield="longName"):
    """Print the plugin longName and version to stdout."""
    echo(f"{plugin[namefield]}:{plugin['version']}")


@plugins_app.command("list")
def plugins_list(ctx: typer.Context) -> None:
    """List installed plugins.

    Defaults to listing all installed plugins and their current versions
    """
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            print_plugin(plugin)
    except Exception:
        log.exception("Failed to list plugins")
        raise typer.Exit(1) from None


@plugins_app.command("pinned")
def plugins_pinned(ctx: typer.Context) -> None:
    """List pinned plugins."""
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if plugin["pinned"]:
                print_plugin(plugin)
    except Exception:
        log.exception("Failed to list pinned plugins")
        raise typer.Exit(1) from None


@plugins_app.command("dynamic")
def plugins_dynamic(ctx: typer.Context) -> None:
    """List dynamically reloadable plugins."""
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if plugin["supportsDynamicLoad"] == "YES":
                print_plugin(plugin)
    except Exception:
        log.exception("Failed to list dynamic plugins")
        raise typer.Exit(1) from None


@plugins_app.command("needs-update")
def plugins_needs_update(ctx: typer.Context) -> None:
    """List pending plugin updates."""
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if plugin["hasUpdate"]:
                print_plugin(plugin)
    except Exception:
        log.exception("Failed to list plugins needing updates")
        raise typer.Exit(1) from None


@plugins_app.command("enabled")
def plugins_enabled(ctx: typer.Context) -> None:
    """List enabled plugins."""
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if plugin["enabled"]:
                print_plugin(plugin)
    except Exception:
        log.exception("Failed to list enabled plugins")
        raise typer.Exit(1) from None


@plugins_app.command("disabled")
def plugins_disabled(ctx: typer.Context) -> None:
    """List disabled plugins.

    TODO: In the future this should be part of a command alias and pass a flag
    to 'enabled' so that we don't duplicate code.
    """
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if not plugin["enabled"]:
                print_plugin(plugin)
    except Exception:
        log.exception("Failed to list disabled plugins")
        raise typer.Exit(1) from None


@plugins_app.command("active")
def plugins_active(ctx: typer.Context) -> None:
    """List active plugins."""
    try:
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if plugin["active"]:
                print_plugin(plugin)
    except Exception:
        log.exception("Failed to list active plugins")
        raise typer.Exit(1) from None


@plugins_app.command("sec")
def plugins_sec(ctx: typer.Context) -> None:
    """List plugins with a known vulnerability.

    Output is in the format:

    Vulnerable Version\t Installed Version\t Link.
    """
    try:
        advisories = vulnerable_plugins(ctx.obj["jenkins"].server, fetch_warnings())
    except AdvisoriesError as exc:
        log.error("%s", exc)
        raise typer.Exit(1) from None
    except Exception:
        log.exception("Failed to check plugin security")
        raise typer.Exit(1) from None
    for advisory in advisories:
        echo(f"{advisory.plugin}:{advisory.last_affected}\t{advisory.plugin}:{advisory.installed}\t{advisory.url}")
