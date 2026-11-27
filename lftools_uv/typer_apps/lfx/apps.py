# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Typer apps for the ``lfx`` command group."""

from __future__ import annotations

import typer

lfx_app = typer.Typer(
    name="lfx",
    help="LFX v2 API interface. Reads LFX_TOKEN, or the output of 'lfx auth token'.",
    add_completion=False,
    no_args_is_help=True,
)

committee_app = typer.Typer(
    name="committee",
    help="LFX committees, named by UID or SSO group name.",
    add_completion=False,
    no_args_is_help=True,
)

lfx_app.add_typer(committee_app, name="committee")
