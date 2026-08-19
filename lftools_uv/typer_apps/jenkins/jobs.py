# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer commands enabling and disabling Jenkins jobs."""

import logging

import typer

log = logging.getLogger(__name__)

jobs_app = typer.Typer(help="Command to update Jenkins Jobs.")


# Jobs subcommands
enable_disable_jobs = """
import jenkins.*
import jenkins.model.*
import hudson.*
import hudson.model.*


def jobTypes = [hudson.model.FreeStyleProject.class]

def filter = {{job->
    if (job.disabled == true) {{
        println("${{job.fullName}}")
    }}
    job.getDisplayName().contains("{0}")
}}

def disableClosure = {{job->job.{1}()}}

jobTypes.each{{ className->
    jenkins.model.Jenkins.instance.getAllItems(className).findAll(filter).each(disableClosure)}}
"""


@jobs_app.command("enable")
def jobs_enable(ctx: typer.Context, regex: str = typer.Argument(..., help="Regex pattern to match job names")) -> None:
    """Enable all Jenkins jobs matching REGEX."""
    try:
        jenkins = ctx.obj["jenkins"]
        result = jenkins.server.run_script(enable_disable_jobs.format(regex, "enable"))
        log.info(result)
    except Exception:
        log.exception("Failed to enable jobs")
        raise typer.Exit(1) from None


@jobs_app.command("disable")
def jobs_disable(ctx: typer.Context, regex: str = typer.Argument(..., help="Regex pattern to match job names")) -> None:
    """Disable all Jenkins jobs matching REGEX."""
    try:
        jenkins = ctx.obj["jenkins"]
        result = jenkins.server.run_script(enable_disable_jobs.format(regex, "disable"))
        log.info(result)
    except Exception:
        log.exception("Failed to disable jobs")
        raise typer.Exit(1) from None
