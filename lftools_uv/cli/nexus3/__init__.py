# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Nexus3 REST API sub-interfaces."""

__author__ = "DW Talton"

import click

from lftools_uv.api.endpoints import nexus3
from lftools_uv.cli.state import LazyClient

from .asset import asset
from .privilege import privilege
from .repository import repository
from .role import role
from .script import script
from .tag import tag
from .task import task
from .user import user


@click.group(name="nexus3")
@click.argument("fqdn")
@click.pass_context
def nexus_three(ctx, fqdn):
    """The Nexus3 API Interface."""
    nexus3_obj = LazyClient(lambda: nexus3.Nexus3(fqdn=fqdn))
    # Preserve existing context; add nexus3 client without overwriting other keys
    if ctx.obj is None:
        ctx.obj = {}
    ctx.obj["nexus3"] = nexus3_obj
    # Also register inside structured AppState if available
    state = ctx.obj.get("state")
    if state:
        state.nexus3 = nexus3_obj
    pass


nexus_three.add_command(asset)
nexus_three.add_command(privilege)
nexus_three.add_command(repository)
nexus_three.add_command(role)
nexus_three.add_command(script)
nexus_three.add_command(tag)
nexus_three.add_command(task)
nexus_three.add_command(user)
