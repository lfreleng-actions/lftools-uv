# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the exits ``handle_errors`` lets the CLI frameworks keep.

Click and Typer signal exits, aborts and usage errors with exceptions that
are not ``SystemExit``. The decorator must pass them through so each keeps
the exit code and message its framework gives it, while other exceptions
still map to the decorator's own codes.
"""

import sys

import click
import pytest
import typer
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.errors import error_handler

XFAIL_866 = pytest.mark.xfail(strict=True, reason="#866: handle_errors turns framework exits into exit 1")


@click.group()
def click_app() -> None:
    """Hold the decorated Click commands."""


@click_app.command("ctx-exit")
@click.pass_context
@error_handler
def click_ctx_exit(ctx: click.Context) -> None:
    """Exit 0 through the Click context."""
    ctx.exit(0)


@click_app.command("usage-error")
@error_handler
def click_usage_error() -> None:
    """Raise a Click usage error."""
    raise click.UsageError("bad usage")


@click_app.command("abort")
@error_handler
def click_abort() -> None:
    """Abort through Click."""
    raise click.Abort()


@click_app.command("value-error")
@error_handler
def click_value_error() -> None:
    """Raise an exception the decorator maps."""
    raise ValueError("boom")


@click_app.command("sys-exit")
@error_handler
def click_sys_exit() -> None:
    """Exit 4 through ``sys.exit``."""
    sys.exit(4)


typer_app = typer.Typer()


@typer_app.callback()
def typer_callback() -> None:
    """Keep the decorated Typer commands under their own names."""


@typer_app.command("exit")
@error_handler
def typer_exit() -> None:
    """Exit 3 through Typer."""
    raise typer.Exit(3)


@typer_app.command("abort")
@error_handler
def typer_abort() -> None:
    """Abort through Typer."""
    raise typer.Abort()


@typer_app.command("bad-parameter")
@error_handler
def typer_bad_parameter() -> None:
    """Raise a Typer usage error."""
    raise typer.BadParameter("bad value")


def _click(command: str) -> ClickResult:
    return ClickRunner().invoke(click_app, [command])


def _typer(command: str) -> TyperResult:
    return TyperRunner().invoke(typer_app, [command])


@XFAIL_866
def test_click_ctx_exit_keeps_code() -> None:
    """``ctx.exit(0)`` exits 0."""
    assert _click("ctx-exit").exit_code == 0


@XFAIL_866
def test_click_usage_error_keeps_code() -> None:
    """``click.UsageError`` exits 2."""
    assert _click("usage-error").exit_code == 2


@XFAIL_866
def test_click_abort_reaches_click() -> None:
    """``click.Abort`` reaches Click, which prints ``Aborted!``."""
    result = _click("abort")
    assert result.exit_code == 1
    assert "Aborted!" in result.output


@XFAIL_866
def test_typer_exit_keeps_code() -> None:
    """``typer.Exit(3)`` exits 3."""
    assert _typer("exit").exit_code == 3


@XFAIL_866
def test_typer_abort_reaches_typer() -> None:
    """``typer.Abort`` reaches Typer, which prints ``Aborted.``."""
    result = _typer("abort")
    assert result.exit_code == 1
    assert "Aborted." in result.output


@XFAIL_866
def test_typer_bad_parameter_keeps_code() -> None:
    """``typer.BadParameter`` exits 2."""
    assert _typer("bad-parameter").exit_code == 2


def test_value_error_still_maps_to_one() -> None:
    """Other exceptions still become the decorator's exit code."""
    assert _click("value-error").exit_code == 1


def test_sys_exit_keeps_code() -> None:
    """``sys.exit(4)`` still exits 4."""
    assert _click("sys-exit").exit_code == 4
