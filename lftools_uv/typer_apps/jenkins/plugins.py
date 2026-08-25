# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands inspecting Jenkins plugins."""

import logging

import requests
import typer

log = logging.getLogger(__name__)

plugins_app = typer.Typer(help="Inspect Jenkins plugins on the server.")


# Plugins subcommands
def checkmark(truthy):
    """Return a UTF-8 Checkmark or Cross depending on the truthiness of the argument."""
    if truthy:
        return "\u2713"
    return "\u2717"


def print_plugin(plugin, namefield="longName"):
    """Log the plugin longName and version."""
    log.info("%s:%s", plugin[namefield], plugin["version"])


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
        r = requests.get("http://updates.jenkins-ci.org/update-center.actual.json")
        warn = r.json()["warnings"]

        secdict = {}
        for w in warn:
            name = w["name"]
            lastversion = None
            for version in w["versions"]:
                lastversion = version.get("lastVersion")
            nv = {name: lastversion}
            secdict.update(nv)

        activedict = {}
        jenkins = ctx.obj["jenkins"]
        plugins = jenkins.server.get_plugins()
        for key in plugins.keys():
            _, plugin_name = key
            plugin = plugins[plugin_name]
            if plugin["active"]:
                name = plugin["shortName"]
                version = plugin["version"]
                nv = {name: version}
                activedict.update(nv)

        # find the delta
        shared = []
        for key in set(secdict.keys()) & set(activedict.keys()):
            shared.append(key)
            ourversion = activedict[key]
            theirversion = secdict[key]
            t1 = (ourversion,)
            t2 = (theirversion,)
            if t1 <= t2:
                for w in warn:
                    name = w["name"]
                    url = w["url"]
                    lastversion = None
                    for version in w["versions"]:
                        lastversion = version.get("lastVersion")
                    if name == key and secdict[key] == lastversion:
                        # Tab-separated columns: vulnerable version,
                        # installed version, then the advisory URL.
                        log.info("%s:%s\t%s:%s\t%s", key, secdict[key], key, activedict[key], url)
    except Exception:
        log.exception("Failed to check plugin security")
        raise typer.Exit(1) from None
