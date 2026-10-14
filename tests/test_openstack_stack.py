# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for OpenStack stack operations."""

import logging
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from openstack.orchestration.v1.stack import Stack
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.openstack import cmd as os_cmd
from lftools_uv.openstack import stack as os_stack
from lftools_uv.typer_apps.openstack import openstack_app


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


def _heat_stack(stack_id: str, name: str, status: str, age_hours: float = 48) -> Stack:
    """Build a Stack as openstacksdk returns it from the Heat API."""
    created = datetime.now(UTC) - timedelta(hours=age_hours)
    return Stack.existing(
        id=stack_id,
        stack_name=name,
        stack_status=status,
        creation_time=created.strftime("%Y-%m-%dT%H:%M:%SZ"),
    )


@patch("lftools_uv.openstack.stack.delete")
@patch("lftools_uv.openstack.stack.Jenkins")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_matches_by_name_and_deletes_by_id(mock_from_config, mock_jenkins, mock_delete):
    """Stacks of running builds are kept; orphans are deleted by id.

    openstacksdk exposes the Heat stack name as ``Stack.name``, leaving
    ``stack_name`` as None. Matching on ``stack_name`` marked every
    stack, including those of running builds, for deletion with a None
    identifier.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.search_stacks.return_value = [
        _heat_stack("id-active", "releng-csit-job-112", "CREATE_COMPLETE"),
        _heat_stack("id-orphan", "releng-csit-job-99", "CREATE_COMPLETE"),
        _heat_stack("id-failed", "releng-other-job-7", "CREATE_FAILED"),
        _heat_stack("id-busy", "releng-csit-job-113", "CREATE_IN_PROGRESS"),
    ]
    jenkins = mock_jenkins.return_value
    jenkins.url = "https://jenkins.example.org/releng/"
    jenkins.server.get_running_builds.return_value = [{"name": "csit-job", "number": 112}]

    os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"])

    assert [c.args for c in mock_delete.call_args_list] == [
        ("test-cloud", "id-orphan"),
        ("test-cloud", "id-failed"),
    ]


@patch("lftools_uv.openstack.stack.delete")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_with_no_stacks_exits_cleanly(mock_from_config, mock_delete):
    """No stacks means nothing to delete and a zero exit."""
    mock_from_config.return_value.search_stacks.return_value = []

    with pytest.raises(SystemExit) as exc_info:
        os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"])

    assert exc_info.value.code == 0
    mock_delete.assert_not_called()


@patch("lftools_uv.openstack.stack.delete")
@patch("lftools_uv.openstack.stack.Jenkins")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_protects_young_stacks(mock_from_config, mock_jenkins, mock_delete):
    """A stack younger than min_age_hours is never reaped.

    python-jenkins' get_running_builds() walks the node list and silently
    skips any node that returns HTTP 500 or that disappears mid-query, both
    routine with ephemeral cloud agents. The resulting short build list makes
    live stacks look orphaned, so age alone has to veto the deletion.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.search_stacks.return_value = [
        _heat_stack("id-young", "releng-csit-job-99", "CREATE_COMPLETE", age_hours=1),
        _heat_stack("id-old", "releng-csit-job-98", "CREATE_COMPLETE", age_hours=48),
    ]
    jenkins = mock_jenkins.return_value
    jenkins.url = "https://jenkins.example.org/releng/"
    jenkins.server.get_running_builds.return_value = []

    os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"])

    assert [c.args for c in mock_delete.call_args_list] == [("test-cloud", "id-old")]


@patch("lftools_uv.openstack.stack.delete")
@patch("lftools_uv.openstack.stack.Jenkins")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_skips_stacks_of_unknown_age(mock_from_config, mock_jenkins, mock_delete):
    """A stack whose creation time cannot be determined is left alone.

    Covers both reasons an age is unknown: Heat omitted the field entirely,
    and Heat returned a timestamp that will not parse. Either way the stack
    could belong to a running build, so the fail-safe is to keep it.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.search_stacks.return_value = [
        Stack.existing(id="id-noage", stack_name="releng-csit-job-99", stack_status="CREATE_COMPLETE"),
        Stack.existing(
            id="id-badage",
            stack_name="releng-csit-job-98",
            stack_status="CREATE_COMPLETE",
            creation_time="not-a-timestamp",
        ),
    ]
    jenkins = mock_jenkins.return_value
    jenkins.url = "https://jenkins.example.org/releng/"
    jenkins.server.get_running_builds.return_value = []

    os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"])

    mock_delete.assert_not_called()


@patch("lftools_uv.openstack.stack.delete")
@patch("lftools_uv.openstack.stack.Jenkins")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_honours_custom_min_age(mock_from_config, mock_jenkins, mock_delete):
    """The caller-supplied threshold decides, not the module default.

    The stack sits between the custom threshold and the default, so a
    regression that ignored the argument and compared against
    STALE_MIN_AGE_HOURS would keep it and go unnoticed.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.search_stacks.return_value = [
        _heat_stack("id-12h", "releng-csit-job-99", "CREATE_COMPLETE", age_hours=12),
    ]
    jenkins = mock_jenkins.return_value
    jenkins.url = "https://jenkins.example.org/releng/"
    jenkins.server.get_running_builds.return_value = []

    os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"])
    mock_delete.assert_not_called()  # 12h < default 24h

    os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"], min_age_hours=6)
    assert [c.args for c in mock_delete.call_args_list] == [("test-cloud", "id-12h")]


@patch("lftools_uv.openstack.stack.delete", return_value=True)
@patch("lftools_uv.openstack.stack.time.sleep")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_create_exits_non_zero_when_all_tries_fail(mock_from_config, mock_sleep, mock_delete):
    """Exhausting every try must fail the command, not return quietly.

    create() tracked the outcome in a local it never acted on, so a build
    whose stack never came up saw a zero exit and carried on to copy SSH keys
    to hosts that do not exist, burning the whole job timeout before dying
    somewhere unrelated to the real cause.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.create_stack.return_value = _heat_stack("id-1", "a-stack", "CREATE_IN_PROGRESS")
    mock_cloud.get_stack.return_value = _heat_stack("id-1", "a-stack", "CREATE_FAILED")

    with pytest.raises(SystemExit) as exc_info:
        os_stack.create("test-cloud", "a-stack", "template.yaml", "params.yaml", timeout=1, tries=2)

    assert exc_info.value.code == 1
    assert mock_cloud.create_stack.call_count == 2


@patch("lftools_uv.openstack.stack.time.sleep")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_create_returns_without_exit_on_success(mock_from_config, mock_sleep):
    """A stack reaching CREATE_COMPLETE returns normally."""
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.create_stack.return_value = _heat_stack("id-1", "a-stack", "CREATE_IN_PROGRESS")
    mock_cloud.get_stack.return_value = _heat_stack("id-1", "a-stack", "CREATE_COMPLETE")

    os_stack.create("test-cloud", "a-stack", "template.yaml", "params.yaml", timeout=1, tries=2)

    assert mock_cloud.create_stack.call_count == 1


@pytest.mark.xfail(strict=True, reason="delete-stale with no Jenkins reaps every stack")
@patch("lftools_uv.openstack.stack.delete")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_refuses_without_jenkins(mock_from_config, mock_delete):
    """No Jenkins servers means no build list, so every stack would look stale."""
    mock_from_config.return_value.search_stacks.return_value = [
        _heat_stack("id-orphan", "releng-csit-job-99", "CREATE_COMPLETE"),
    ]

    with pytest.raises(SystemExit) as exc_info:
        os_stack.delete_stale("test-cloud", [])

    assert exc_info.value.code == 1
    mock_delete.assert_not_called()


@pytest.mark.xfail(strict=True, reason="delete-stale ignores failed deletes")
@patch("lftools_uv.openstack.stack.delete", side_effect=[False, True])
@patch("lftools_uv.openstack.stack.Jenkins")
@patch("lftools_uv.openstack.stack.openstack.connection.from_config")
def test_delete_stale_exits_non_zero_when_a_delete_fails(mock_from_config, mock_jenkins, mock_delete, caplog):
    """A stack that will not delete fails the run, after every stack is tried.

    Exiting 0 let the cleanup cron pass while orphans kept consuming quota.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.search_stacks.return_value = [
        _heat_stack("id-stuck", "releng-csit-job-99", "CREATE_COMPLETE"),
        _heat_stack("id-orphan", "releng-csit-job-98", "CREATE_COMPLETE"),
    ]
    jenkins = mock_jenkins.return_value
    jenkins.url = "https://jenkins.example.org/releng/"
    jenkins.server.get_running_builds.return_value = []

    with pytest.raises(SystemExit) as exc_info:
        os_stack.delete_stale("test-cloud", ["https://jenkins.example.org/releng"])

    assert exc_info.value.code == 1
    assert [c.args[1] for c in mock_delete.call_args_list] == ["id-stuck", "id-orphan"]
    assert "releng-csit-job-99" in caplog.text


def _run_click(args: list[str]) -> ClickResult:
    return ClickRunner().invoke(os_cmd.openstack, ["--os-cloud", "test-cloud", *args], obj={})


def _run_typer(args: list[str]) -> TyperResult:
    return TyperRunner().invoke(openstack_app, ["--os-cloud", "test-cloud", *args])


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
@pytest.mark.parametrize(
    ("delete_result", "expected"),
    [
        (True, 0),
        (None, 0),
        pytest.param(False, 1, marks=pytest.mark.xfail(strict=True, reason="stack delete exits 0 on timeout")),
    ],
    ids=["deleted", "forced", "timed-out"],
)
def test_stack_delete_exit_code(run, delete_result, expected):
    """A timed-out delete fails the command unless --force asked to ignore it.

    delete() returns True on success, False on timeout, and None when --force
    is set; only False is a failure.
    """
    with patch("lftools_uv.openstack.stack.delete", return_value=delete_result):
        result = run(["stack", "delete", "a-stack"])

    assert result.exit_code == expected


@pytest.mark.parametrize(
    "run",
    [
        pytest.param(_run_click, marks=pytest.mark.xfail(strict=True, reason="Click accepts no Jenkins URLs")),
        _run_typer,
    ],
    ids=["click", "typer"],
)
def test_delete_stale_requires_jenkins_urls(run):
    """Omitting the Jenkins URLs is a usage error, not a reap-everything run."""
    with patch("lftools_uv.openstack.stack.delete_stale") as mock_delete_stale:
        result = run(["stack", "delete-stale"])

    assert result.exit_code == 2
    mock_delete_stale.assert_not_called()
