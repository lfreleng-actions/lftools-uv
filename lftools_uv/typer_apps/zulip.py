# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer CLI app for Zulip channel management.

The ``zulip`` command group is always registered with the root CLI even
when the optional ``zulip`` extra is not installed. When the extra is
missing, any subcommand invocation produces the canonical FR-022 error
message directing the user to install the extra.

See ``specs/001-zulip-channel-mgmt/`` for the full feature design.
"""

from __future__ import annotations

import typer

from lftools_uv.api.endpoints.zulip import zulip_available

#: Canonical error message displayed when the ``zulip`` extra is missing
#: (FR-022). Matches the wording in ``contracts/cli-commands.md``.
MISSING_EXTRA_MESSAGE = 'Zulip support requires the zulip extra. Install with:\n  pip install "lftools-uv[zulip]"'


zulip_app = typer.Typer(
    name="zulip",
    help="Manage Zulip channels, users, and groups.",
    no_args_is_help=True,
)


@zulip_app.callback()
def zulip_callback(ctx: typer.Context) -> None:
    """Top-level callback for the Zulip command group.

    When the optional ``zulip`` extra is not installed, abort immediately
    with the canonical FR-022 error so that every subcommand presents the
    same guidance to the user.
    """
    if ctx.invoked_subcommand is None:
        # Help/no-args path — let Typer print help without raising.
        return
    if not zulip_available():
        typer.echo(MISSING_EXTRA_MESSAGE, err=True)
        raise typer.Exit(code=1)
