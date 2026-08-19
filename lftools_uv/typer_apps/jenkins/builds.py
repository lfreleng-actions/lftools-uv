# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands reporting on Jenkins builds and the queue."""

import logging

import typer

log = logging.getLogger(__name__)

builds_app = typer.Typer(help="Information regarding current builds and the queue.")


@builds_app.command("running")
def builds_running(ctx: typer.Context) -> None:
    """Show all the currently running builds."""
    try:
        jenkins = ctx.obj["jenkins"]
        running_builds = jenkins.server.get_running_builds()

        for build in running_builds:
            log.info("- %s on %s", build["name"], build["node"])
    except Exception:
        log.exception("Failed to get running builds")
        raise typer.Exit(1) from None


@builds_app.command("queued")
def builds_queued(ctx: typer.Context) -> None:
    """Show all jobs waiting in the queue and their status."""
    try:
        jenkins = ctx.obj["jenkins"]
        queue = jenkins.server.get_queue_info()

        queue_length = len(queue)
        log.info("Build Queue (%s)", queue_length)
        for build in queue:
            status_flags = []
            if build.get("stuck"):
                status_flags.append("[Stuck]")
            if build.get("blocked"):
                status_flags.append("[Blocked]")
            log.info(" - %s%s", build["task"]["name"], (" " + " ".join(status_flags)) if status_flags else "")
    except Exception:
        log.exception("Failed to get queued builds")
        raise typer.Exit(1) from None
