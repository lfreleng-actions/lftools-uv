# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer version of infofile commands."""

import logging

import typer

from lftools_uv.cli.errors import error_handler
from lftools_uv.cli.infofile import print_committers, print_info_file, sync_committer, tally_votes

_HELP_INFO_YAML_PATH = "Path to INFO.yaml file"


log = logging.getLogger(__name__)

infofile_app = typer.Typer(
    name="infofile",
    help="INFO.yaml file management tools",
    add_completion=False,
)


@infofile_app.callback()
def infofile_callback() -> None:
    """INFO.yaml TOOLS."""
    pass


@infofile_app.command("create-info-file")
@error_handler
def create_info_file(
    gerrit_url: str = typer.Argument(..., help="Gerrit URL (e.g., gerrit.example.com)"),
    gerrit_project: str = typer.Argument(..., help="Gerrit project path (e.g., project/full-name)"),
    directory: str = typer.Option("r", "--directory", help="Custom gerrit directory, e.g. not /r/"),
    empty: bool = typer.Option(False, "--empty", help="Create info file for uncreated project"),
    tsc_approval: str = typer.Option(
        "missing", "--tsc-approval", "--tsc_approval", help="Optionally provide a TSC approval link"
    ),
    group: str | None = typer.Option(
        None,
        "--group",
        help="SSO group name of the LFX committee whose members become the committers, in place of "
        "UMBRELLA-gerrit-PROJECT-committers",
    ),
) -> None:
    """Create an initial INFO file.

    The INFO.yaml template goes to stdout. Unless --empty is given, the
    project's access is read from Gerrit and the committers are the
    members of the LFX committee whose SSO group name is
    UMBRELLA-gerrit-PROJECT-committers, or --group. Reading them needs an
    LFX token with the auditor relation on the committee. A failed member
    lookup prints nothing and exits non-zero.

    Examples:
        lftools-uv infofile create-info-file gerrit.example.com project/name
        lftools-uv infofile create-info-file gerrit.example.com project/name --empty
        lftools-uv infofile create-info-file gerrit.example.com project/name --group project-maintainers
    """
    print_info_file(gerrit_url, gerrit_project, directory, empty, tsc_approval, group)


@infofile_app.command("get-committers")
@error_handler
def get_committers(
    file: str = typer.Argument(..., envvar="FILE_NAME", help="INFO.yaml file or LDAP dump to read"),
    full: bool = typer.Option(False, "--full", help="Output name email and id for all committers in an infofile"),
    committer_id: str | None = typer.Option(None, "--id", help="Full output for a specific LFID"),
) -> None:
    """Extract Committer info from INFO.yaml or LDAP dump.

    Each committer's id goes to stdout; --full adds the name and email.

    Examples:
        lftools-uv infofile get-committers INFO.yaml
        lftools-uv infofile get-committers --full --id alice INFO.yaml
    """
    print_committers(file, full, committer_id)


@infofile_app.command("sync-committers")
@error_handler
def sync_committers(
    info_file: str = typer.Argument(..., help=_HELP_INFO_YAML_PATH),
    ldap_file: str = typer.Argument(..., help="LDAP dump to copy the committer from"),
    committer_id: str = typer.Argument(..., help="LFID of the committer to add"),
    repo: str | None = typer.Option(None, "--repo", help="Repository name to set as the first in repositories"),
) -> None:
    """Sync committer information from LDAP into INFO.yaml.

    Exits 0 without writing when the committer is already in the INFO
    file, and 1 when the LDAP dump lists no such committer. Without
    --repo, repositories is left unchanged.

    Examples:
        lftools-uv infofile sync-committers INFO.yaml LDAP.yaml alice
        lftools-uv infofile sync-committers INFO.yaml LDAP.yaml alice --repo my-repo
    """
    sync_committer(info_file, ldap_file, committer_id, repo)


@infofile_app.command("check-votes")
@error_handler
def check_votes(
    info_file: str = typer.Argument(..., help=_HELP_INFO_YAML_PATH),
    endpoint: str = typer.Argument(..., help="Gerrit URL, or the GitHub organization with --github_repo"),
    change_number: int = typer.Argument(..., help="Gerrit change or GitHub pull request number"),
    tsc: str | None = typer.Option(None, "--tsc", help="Path to TSC INFO file"),
    github_repo: str | None = typer.Option(
        None, "--github_repo", help="Provide github repo to Check against a Github Change"
    ),
) -> None:
    """Check votes on an INFO.yaml change.

    Check for a majority of committer votes on a Gerrit or GitHub change
    to an INFO.yaml file. The vote count and outcome go to stdout; the
    command exits 1 when no majority is reached.

    Examples:
        lftools-uv infofile check-votes INFO.yaml https://gerrit.example.org/r/ 67302
        lftools-uv infofile check-votes INFO.yaml example-org 18 --github_repo test
    """
    tally_votes(info_file, endpoint, change_number, tsc, github_repo)


def get_infofile_app() -> typer.Typer:
    """Get the infofile Typer app instance.

    This function is used by other modules to register the infofile commands.
    """
    return infofile_app
