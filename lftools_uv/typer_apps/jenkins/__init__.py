# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""Typer Jenkins CLI commands.

Each command group lives in its own module and owns its Typer app.
This package composes them into the `jenkins` command tree.
"""

from lftools_uv.typer_apps.jenkins.builds import builds_app
from lftools_uv.typer_apps.jenkins.jobs import jobs_app
from lftools_uv.typer_apps.jenkins.nodes import nodes_app
from lftools_uv.typer_apps.jenkins.plugins import plugins_app
from lftools_uv.typer_apps.jenkins.server import jenkins_app
from lftools_uv.typer_apps.jenkins.token import token_app

jenkins_app.add_typer(builds_app, name="builds")
jenkins_app.add_typer(jobs_app, name="jobs")
jenkins_app.add_typer(nodes_app, name="nodes")
jenkins_app.add_typer(plugins_app, name="plugins")
jenkins_app.add_typer(token_app, name="token")

__all__ = ["jenkins_app"]
