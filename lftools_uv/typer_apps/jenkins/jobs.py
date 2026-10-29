# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands enabling and disabling Jenkins jobs."""

import logging

import typer

from lftools_uv.jenkins.jobs import JobsError, set_jobs_disabled
from lftools_uv.output import echo

log = logging.getLogger(__name__)

jobs_app = typer.Typer(help="Command to update Jenkins Jobs.")


def _set_disabled(ctx: typer.Context, regex: str, disable: bool) -> None:
    """Print each job changed; exit 1 if none matched or one did not change."""
    action = "disable" if disable else "enable"
    try:
        changed, failed = set_jobs_disabled(ctx.obj["jenkins"].server, regex, disable)
    except JobsError as exc:
        log.error("%s", exc)
        raise typer.Exit(1) from None
    except Exception:
        log.exception("Failed to %s jobs", action)
        raise typer.Exit(1) from None
    for name in changed:
        echo(name)
    if failed:
        log.error("Could not %s %d job(s): %s", action, len(failed), ", ".join(failed))
        raise typer.Exit(1)


@jobs_app.command("enable")
def jobs_enable(ctx: typer.Context, regex: str = typer.Argument(..., help="Regex pattern to match job names")) -> None:
    """Enable all Jenkins jobs matching REGEX."""
    _set_disabled(ctx, regex, False)


@jobs_app.command("disable")
def jobs_disable(ctx: typer.Context, regex: str = typer.Argument(..., help="Regex pattern to match job names")) -> None:
    """Disable all Jenkins jobs matching REGEX."""
    _set_disabled(ctx, regex, True)
