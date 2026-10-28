# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Nexus2 REST API sub-interfaces."""

__author__ = "DW Talton"


import click

from lftools_uv.api.endpoints import nexus2
from lftools_uv.cli.state import LazyClient

from .privilege import privilege
from .repository import repo
from .role import role
from .user import user


@click.group(name="nexus2")
@click.argument("fqdn")
@click.pass_context
def nexus_two(ctx, fqdn):
    """The Nexus2 API Interface."""
    nexus2_obj = LazyClient(lambda: nexus2.Nexus2(fqdn=fqdn))
    if ctx.obj is None:
        ctx.obj = {}
    # Store client in raw context (legacy) and structured AppState if available
    ctx.obj["nexus2"] = nexus2_obj
    state = ctx.obj.get("state")
    if state:
        state.nexus2 = nexus2_obj
    pass


nexus_two.add_command(privilege)
nexus_two.add_command(repo)
nexus_two.add_command(role)
nexus_two.add_command(user)
