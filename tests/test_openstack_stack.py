# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for OpenStack stack operations."""

import logging
from unittest.mock import MagicMock, patch

import pytest

from lftools_uv.openstack import stack as os_stack


@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_with_no_servers_reports_zero(mock_connect, capsys):
    """A stack holding no servers costs nothing and succeeds."""
    mock_cloud = MagicMock()
    mock_connect.return_value = mock_cloud
    mock_cloud.orchestration.resources.return_value = []

    os_stack.cost("test-cloud", "empty-stack")

    assert capsys.readouterr().out.strip() == "total: 0.0"


@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_exits_non_zero_when_enumeration_fails(mock_connect, capsys, caplog):
    """Stack enumeration failing must fail the command, not report 0.0.

    The per-server pricing lookup already falls back to 0.0 when the pricing
    API misbehaves, so reaching the outer handler means no total can be
    derived at all. Reporting 0.0 there would be indistinguishable from a
    genuinely idle stack, and a pipeline reading the figure would silently
    under-report.
    """
    mock_cloud = MagicMock()
    mock_connect.return_value = mock_cloud
    mock_cloud.orchestration.resources.side_effect = RuntimeError("enumeration failed")

    with pytest.raises(SystemExit) as exc_info:
        os_stack.cost("test-cloud", "broken-stack")

    assert exc_info.value.code == 1
    assert "total:" not in capsys.readouterr().out
    assert any(record.levelno >= logging.ERROR for record in caplog.records)
