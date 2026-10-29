# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Jenkins Jobs."""

__author__ = "Anil Belur"

import logging
import sys

import click

from lftools_uv.jenkins.jobs import JobsError, set_jobs_disabled
from lftools_uv.output import echo

log = logging.getLogger(__name__)


def _set_disabled(ctx: click.Context, regex: str, disable: bool) -> None:
    """Print each job changed; exit 1 if none matched or one did not change."""
    try:
        changed, failed = set_jobs_disabled(ctx.obj["jenkins"].server, regex, disable)
    except JobsError as exc:
        log.error("%s", exc)
        sys.exit(1)
    for name in changed:
        echo(name)
    if failed:
        log.error("Could not %s %d job(s): %s", "disable" if disable else "enable", len(failed), ", ".join(failed))
        sys.exit(1)


@click.group()
@click.pass_context
def jobs(ctx):
    """Command to update Jenkins Jobs."""
    pass


@click.command()
@click.argument("regex")
@click.pass_context
def enable(ctx, regex):
    """Enable all Jenkins jobs matching REGEX."""
    _set_disabled(ctx, regex, False)


@click.command()
@click.argument("regex")
@click.pass_context
def disable(ctx, regex):
    """Disable all Jenkins jobs matching REGEX."""
    _set_disabled(ctx, regex, True)


jobs.add_command(enable)
jobs.add_command(disable)
