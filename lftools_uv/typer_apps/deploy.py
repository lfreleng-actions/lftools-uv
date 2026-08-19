# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer CLI interface for deploy subsystem."""

__author__ = "Thanh Ha"

import logging

import typer
from requests.exceptions import HTTPError

import lftools_uv.deploy as deploy_sys

_HELP_NEXUS_STAGING_ID = "Nexus staging profile ID"
_HELP_NEXUS_URL = "Nexus server URL"


log = logging.getLogger(__name__)

deploy_app = typer.Typer(
    name="deploy",
    help="Deploy files to a Nexus sites repository.",
    epilog="""Deploy commands use ~/.netrc for authentication. This file should be
pre-configured with an entry for the Nexus server. Eg.

    machine nexus.opendaylight.org login logs_user password logs_password""",
)


@deploy_app.callback()
def deploy_callback() -> None:
    """Deploy files to a Nexus sites repository."""
    pass


@deploy_app.command(name="archives")
def archives(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    nexus_path: str = typer.Argument(..., envvar="NEXUS_PATH", help="Path on Nexus where files will be deployed"),
    workspace: str = typer.Argument(..., envvar="WORKSPACE", help="Workspace directory containing files to deploy"),
    pattern: list[str] = typer.Option([], "-p", "--pattern", help="Unix glob patterns for files to deploy"),
) -> None:
    """Archive files to a Nexus site repository.

    Provides 2 ways to archive files:

        1) globstar pattern provided by the user.
        2) $WORKSPACE/archives directory provided by the user.

    To use this command the Nexus server must have a site repository configured
    with the name "logs" as this is a hardcoded log path.
    """
    deploy_sys.deploy_archives(nexus_url, nexus_path, workspace, pattern if pattern else None)


@deploy_app.command(name="copy-archives")
def copy_archives(
    workspace: str = typer.Argument(..., envvar="WORKSPACE", help="Workspace directory to copy files from"),
    pattern: list[str] | None = typer.Argument(None, help="Unix glob patterns of files to copy for archiving"),
) -> None:
    """Copy files for archiving.

    Arguments:
        workspace: Typically a Jenkins WORKSPACE to copy files from.
        pattern: Space-separated list of Unix style glob patterns of files to
                 copy for archiving.
    """
    deploy_sys.copy_archives(workspace, pattern if pattern else None)


@deploy_app.command(name="file")
def file(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    nexus_repo_id: str = typer.Argument(..., help="Nexus repository ID"),
    group_id: str = typer.Argument(..., help="Maven Group ID"),
    artifact_id: str = typer.Argument(..., help="Maven Artifact ID"),
    version: str = typer.Argument(..., help="Maven version"),
    packaging: str = typer.Argument(..., help="Maven packaging type"),
    file_path: str = typer.Argument(..., help="Path to file to deploy"),
    classifier: str = typer.Option("", "-c", "--classifier", help="Maven classifier"),
) -> None:
    """Deploy a file to Nexus using Maven.

    This command will upload a file to a Nexus repository using the Maven
    deploy plugin.
    """
    # Use the upload_maven_file_to_nexus function instead
    deploy_sys.upload_maven_file_to_nexus(
        nexus_url, nexus_repo_id, group_id, artifact_id, version, packaging, file_path, classifier
    )


@deploy_app.command(name="logs")
def logs(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    nexus_path: str = typer.Argument(..., envvar="NEXUS_PATH", help="Path on Nexus where logs will be deployed"),
    build_url: str = typer.Argument(..., envvar="BUILD_URL", help="Build URL for log collection"),
) -> None:
    """Deploy logs to a Nexus site repository.

    This script fetches logs and system information and pushes them to Nexus
    for log archiving.

    To use this script the Nexus server must have a site repository configured
    with the name "logs" as this is a hardcoded path.
    """
    deploy_sys.deploy_logs(nexus_url, nexus_path, build_url)


@deploy_app.command(name="s3")
def s3(
    s3_bucket: str = typer.Argument(..., envvar="S3_BUCKET", help="S3 bucket name"),
    s3_path: str = typer.Argument(..., help="S3 path where files will be deployed"),
    build_url: str = typer.Argument(..., envvar="BUILD_URL", help="Build URL for log collection"),
    workspace: str = typer.Argument(..., envvar="WORKSPACE", help="Workspace directory containing files to deploy"),
    pattern: list[str] = typer.Option([], "-p", "--pattern", help="Unix glob patterns for files to deploy"),
) -> None:
    """Deploy logs and archives to a S3 bucket."""
    pattern_str = None if not pattern else pattern
    deploy_sys.deploy_s3(s3_bucket, s3_path, build_url, workspace, pattern_str)


@deploy_app.command(name="maven-file")
def maven_file(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    repo_id: str = typer.Argument(..., envvar="REPO_ID", help="Repository ID"),
    file_name: str = typer.Argument(..., envvar="FILE_NAME", help="File name to deploy"),
    # Maven Config
    maven_bin: str | None = typer.Option(None, "-b", "--maven-bin", envvar="MAVEN_BIN", help="Path of maven binary."),
    global_settings: str | None = typer.Option(
        None, "-gs", "--global-settings", envvar="GLOBAL_SETTINGS_FILE", help="Global settings file."
    ),
    settings: str | None = typer.Option(None, "-s", "--settings", envvar="SETTINGS_FILE", help="Settings file."),
    maven_params: str | None = typer.Option(
        None, "-p", "--maven-params", help="Pass Maven commandline options to the mvn command."
    ),
    # Maven Artifact GAV
    artifact_id: str | None = typer.Option(None, "-a", "--artifact-id", help="Maven Artifact ID."),
    classifier: str | None = typer.Option(None, "-c", "--classifier", help="Maven Artifact classifier."),
    group_id: str | None = typer.Option(None, "-g", "--group-id", help="Maven Group ID."),
    packaging: str | None = typer.Option(None, "-k", "--packaging", help="Maven packaging."),
    version: str | None = typer.Option(None, "-v", "--version", help="Maven Artifact version."),
    # Repository Config
    repo_url: str | None = typer.Option(None, "-r", "--repo-url", help="Maven repository URL."),
    repository_layout: str = typer.Option("default", "-l", "--repository-layout", help="Repository layout."),
) -> None:
    """Deploy a file to Nexus using Maven deploy:deploy-file.

    This script takes a file and deploys to a Nexus repository using Maven
    deploy plugin.
    """
    try:
        # TODO: Implement maven file deployment functionality
        typer.echo(f"Deploy Maven file {file_name} to {nexus_url}")
        typer.echo("Note: This functionality needs to be implemented")
    except FileNotFoundError:
        log.exception("Maven binary not found")
        raise typer.Exit(127) from None
    except Exception:
        log.exception("Maven deployment failed")
        raise typer.Exit(1) from None


@deploy_app.command(name="nexus")
def nexus(
    nexus_repo_url: str = typer.Argument(..., envvar="NEXUS_REPO_URL", help="Nexus repository URL"),
    deploy_dir: str = typer.Argument(..., envvar="DEPLOY_DIR", help="Directory containing Maven repository to deploy"),
    snapshot: bool = typer.Option(False, "-s", "--snapshot", help="Deploy a snapshot repo."),
) -> None:
    """Deploy a Maven repository to a specified Nexus repository.

    This script takes a local Maven repository and deploys it to a Nexus
    repository.

    Requires the Nexus Unpack plugin and permission assigned to the upload user.
    """
    try:
        deploy_sys.deploy_nexus(nexus_repo_url, deploy_dir, snapshot)
    except HTTPError as e:
        log.exception(str(e))
        raise typer.Exit(1) from None
    except OSError as e:
        log.exception(str(e))
        raise typer.Exit(1) from None


@deploy_app.command(name="nexus-stage")
def nexus_stage(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    staging_profile_id: str = typer.Argument(..., envvar="STAGING_PROFILE_ID", help=_HELP_NEXUS_STAGING_ID),
    deploy_dir: str = typer.Argument(..., envvar="DEPLOY_DIR", help="Directory containing Maven repository to deploy"),
) -> None:
    """Deploy a Maven repository to a Nexus staging repository.

    This script takes a local Maven repository and deploys it to a Nexus
    staging repository as defined by the staging-profile-id.
    """
    deploy_sys.deploy_nexus_stage(nexus_url, staging_profile_id, deploy_dir)


@deploy_app.command(name="nexus-stage-repo-close")
def nexus_stage_repo_close(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    staging_profile_id: str = typer.Argument(..., envvar="STAGING_PROFILE_ID", help=_HELP_NEXUS_STAGING_ID),
    staging_repo_id: str = typer.Argument(..., help="Nexus staging repository ID"),
) -> None:
    """Close a Nexus staging repo."""
    deploy_sys.nexus_stage_repo_close(nexus_url, staging_profile_id, staging_repo_id)


@deploy_app.command(name="nexus-stage-repo-create")
def nexus_stage_repo_create(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    staging_profile_id: str = typer.Argument(..., envvar="STAGING_PROFILE_ID", help=_HELP_NEXUS_STAGING_ID),
) -> None:
    """Create a Nexus staging repo."""
    staging_repo_id = deploy_sys.nexus_stage_repo_create(nexus_url, staging_profile_id)
    log.info(staging_repo_id)


@deploy_app.command(name="nexus-zip")
def nexus_zip(
    nexus_url: str = typer.Argument(..., envvar="NEXUS_URL", help=_HELP_NEXUS_URL),
    nexus_repo: str = typer.Argument(..., envvar="NEXUS_REPO", help="Nexus repository name"),
    nexus_path: str = typer.Argument(..., envvar="NEXUS_PATH", help="Path on Nexus where zip will be deployed"),
    deploy_zip: str = typer.Argument(..., envvar="DEPLOY_DIR", help="Path to zip file to deploy"),
) -> None:
    """Deploy zip file containing artifacts to Nexus using cURL.

    This script simply takes a zip file preformatted in the correct
    directory for Nexus and uploads to a specified Nexus repo using the
    content-compressed URL.

    Requires the Nexus Unpack plugin and permission assigned to the upload user.
    """
    try:
        deploy_sys.deploy_nexus_zip(nexus_url, nexus_repo, nexus_path, deploy_zip)
    except HTTPError as e:
        log.exception(str(e))
        raise typer.Exit(1) from None
    except OSError as e:
        log.exception(str(e))
        raise typer.Exit(1) from None

    log.info("Zip file upload complete.")
