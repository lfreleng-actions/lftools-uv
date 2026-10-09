# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Typer application objects for the Zulip command tree.

Owns ``zulip_app``, its top-level callback, and the four command-group
apps mounted beneath it. The command modules import these objects to
register themselves; the order in which the package imports those
modules is what fixes the order commands appear in ``--help``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import typer
from typer._click.core import Command as ClickCommand
from typer._click.exceptions import UsageError
from typer.core import TyperCommand, TyperGroup

from lftools_uv.typer_apps import zulip as zulip_cli
from lftools_uv.typer_apps.zulip.helpers import MISSING_EXTRA_MESSAGE, zuliprc_callback


def _missing_extra_exit() -> None:
    """Emit the canonical missing-extra message and abort."""
    typer.echo(MISSING_EXTRA_MESSAGE, err=True)
    raise typer.Exit(code=1)


def _help_requested(opts: dict[str, Any], param_order: list[Any]) -> bool:
    """Return whether Click parsed a real help option."""
    return any(getattr(param, "name", None) == "help" and bool(opts.get("help")) for param in param_order)


class ZulipGroup(TyperGroup):
    """Guard Zulip group parse failures without blocking group help."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if ctx.resilient_parsing or not args:
            parsed_args: list[str] = super().parse_args(ctx, args)
            return parsed_args
        parser = self.make_parser(ctx)
        try:
            opts, _, param_order = parser.parse_args(args=list(args))
        except UsageError:
            if not zulip_cli.zulip_available():
                _missing_extra_exit()
            raise
        if _help_requested(opts, param_order):
            parsed_args = super().parse_args(ctx, args)
            return parsed_args
        parsed_args = super().parse_args(ctx, args)
        return parsed_args

    def resolve_command(
        self,
        ctx: Any,
        args: list[str],
    ) -> tuple[str | None, ClickCommand | None, list[str]]:
        try:
            resolved: tuple[str | None, ClickCommand | None, list[str]] = super().resolve_command(ctx, args)
            return resolved
        except UsageError:
            if not zulip_cli.zulip_available():
                _missing_extra_exit()
            raise


class ZulipCommand(TyperCommand):
    """Guard Zulip command execution without blocking command help."""

    def parse_args(self, ctx: Any, args: list[str]) -> list[str]:
        if ctx.resilient_parsing:
            parsed_args: list[str] = super().parse_args(ctx, args)
            return parsed_args
        parser = self.make_parser(ctx)
        try:
            opts, _, param_order = parser.parse_args(args=list(args))
        except UsageError:
            if not zulip_cli.zulip_available():
                _missing_extra_exit()
            raise
        if not _help_requested(opts, param_order) and not zulip_cli.zulip_available():
            _missing_extra_exit()
        parsed_args = super().parse_args(ctx, args)
        return parsed_args

    def invoke(self, ctx: Any) -> Any:
        if not zulip_cli.zulip_available():
            _missing_extra_exit()
        return super().invoke(ctx)


zulip_app = typer.Typer(
    name="zulip",
    help="Manage Zulip channels, users, and groups.",
    no_args_is_help=True,
    cls=ZulipGroup,
)


@zulip_app.callback()
def zulip_callback(
    ctx: typer.Context,
    zuliprc: Path | None = typer.Option(
        None,
        "--zuliprc",
        help="Path to a zuliprc configuration file; overrides other config sources.",
        callback=zuliprc_callback,
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Emit machine-readable JSON instead of a table.",
    ),
) -> None:
    """Top-level callback for the Zulip command group.

    Help renders even when the optional ``zulip`` extra is not
    installed. ``ZulipCommand`` enforces the canonical FR-022 error
    before concrete command bodies run.
    """
    ctx.obj = {
        **(ctx.obj or {}),
        "zuliprc": zuliprc,
        "json_output": json_output,
    }


channel_app = typer.Typer(
    name="channel",
    help="Manage Zulip channels.",
    no_args_is_help=True,
    cls=ZulipGroup,
)
zulip_app.add_typer(channel_app, name="channel")

folder_app = typer.Typer(
    name="folder",
    help="Manage Zulip channel folders.",
    no_args_is_help=True,
    cls=ZulipGroup,
)
zulip_app.add_typer(folder_app, name="folder")


user_app = typer.Typer(
    name="user",
    help="Inspect Zulip users.",
    no_args_is_help=True,
    cls=ZulipGroup,
)
zulip_app.add_typer(user_app, name="user")


group_app = typer.Typer(
    name="group",
    help="Inspect Zulip user groups.",
    no_args_is_help=True,
    cls=ZulipGroup,
)
zulip_app.add_typer(group_app, name="group")
