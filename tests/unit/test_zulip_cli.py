# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Unit tests for the Zulip Typer CLI layer.

Tests are populated by subsequent tasks in the implementation plan.
"""

from __future__ import annotations

from typer.testing import CliRunner

from lftools_uv.typer_apps.zulip import MISSING_EXTRA_MESSAGE, zulip_app


def test_zulip_app_registered() -> None:
    """The zulip Typer app exposes help even without subcommands."""
    runner = CliRunner()
    result = runner.invoke(zulip_app, ["--help"])
    assert result.exit_code == 0
    assert "zulip" in result.stdout.lower()


def test_missing_extra_message_is_canonical() -> None:
    """The FR-022 canonical install hint must be exposed for reuse."""
    assert 'pip install "lftools-uv[zulip]"' in MISSING_EXTRA_MESSAGE
    assert MISSING_EXTRA_MESSAGE.startswith("Zulip support requires the zulip extra.")
