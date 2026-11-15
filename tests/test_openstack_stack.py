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
    build = {"number": 112, "url": "https://jenkins.example.org/releng/job/csit-job/112/"}
    jenkins.server.get_info.return_value = {
        "computer": [{"displayName": "agent-1", "executors": [{"currentExecutable": build}], "oneOffExecutors": []}]
    }

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

    Jenkins lists a running build only to a client allowed to read its job,
    so a live stack's build can be missing from the list without an error.
    Age alone has to veto the deletion.
    """
    mock_cloud = MagicMock()
    mock_from_config.return_value = mock_cloud
    mock_cloud.search_stacks.return_value = [
        _heat_stack("id-young", "releng-csit-job-99", "CREATE_COMPLETE", age_hours=1),
        _heat_stack("id-old", "releng-csit-job-98", "CREATE_COMPLETE", age_hours=48),
    ]
    jenkins = mock_jenkins.return_value
    jenkins.url = "https://jenkins.example.org/releng/"
    jenkins.server.get_info.return_value = {"computer": []}

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
    jenkins.server.get_info.return_value = {"computer": []}

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
    jenkins.server.get_info.return_value = {"computer": []}

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
    jenkins.server.get_info.return_value = {"computer": []}

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
    [(True, 0), (None, 0), (False, 1)],
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


@pytest.mark.parametrize("run", [_run_click, _run_typer], ids=["click", "typer"])
def test_delete_stale_requires_jenkins_urls(run):
    """Omitting the Jenkins URLs is a usage error, not a reap-everything run."""
    with patch("lftools_uv.openstack.stack.delete_stale") as mock_delete_stale:
        result = run(["stack", "delete-stale"])

    assert result.exit_code == 2
    mock_delete_stale.assert_not_called()


_DEFAULT_PRICING_PREFIX = "https://pricing.vexxhost.net/v1/pricing/v3-standard-2/cost?seconds="


def _cloud_with_one_server(mock_connect: MagicMock) -> None:
    """Make openstack.connect return a stack holding one running server."""
    resource = MagicMock(resource_type="OS::Nova::Server", links=[], physical_resource_id="server-1")
    launched = (datetime.now(UTC) - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")
    mock_cloud = MagicMock()
    mock_cloud.orchestration.resources.return_value = [resource]
    mock_cloud.compute.find_server.return_value = MagicMock(
        launched_at=launched, flavor={"original_name": "v3-standard-2"}
    )
    mock_connect.return_value = mock_cloud


def _pricing_response(cost: float) -> MagicMock:
    response = MagicMock()
    response.__enter__.return_value.read.return_value = f'{{"cost": {cost}}}'.encode()
    return response


@pytest.mark.parametrize("env_value", [None, ""], ids=["unset", "empty"])
@patch("lftools_uv.openstack.stack.urllib.request.urlopen")
@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_uses_vexxhost_pricing_by_default(mock_connect, mock_urlopen, env_value, monkeypatch, capsys):
    """Without an override, pricing comes from Vexxhost as it always has."""
    if env_value is None:
        monkeypatch.delenv("LFTOOLS_STACK_PRICING_URL", raising=False)
    else:
        monkeypatch.setenv("LFTOOLS_STACK_PRICING_URL", env_value)
    _cloud_with_one_server(mock_connect)
    mock_urlopen.return_value = _pricing_response(1.25)

    os_stack.cost("test-cloud", "a-stack", timeout=15)

    url = mock_urlopen.call_args.args[0]
    assert url.startswith(_DEFAULT_PRICING_PREFIX)
    assert url[len(_DEFAULT_PRICING_PREFIX) :].isdigit()
    assert mock_urlopen.call_args.kwargs == {"timeout": 15}
    assert capsys.readouterr().out.strip() == "total: 1.25"


@pytest.mark.xfail(strict=True, reason="Pricing endpoint override not yet implemented")
@patch("lftools_uv.openstack.stack.urllib.request.urlopen")
@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_honours_pricing_url_override(mock_connect, mock_urlopen, monkeypatch, capsys):
    """LFTOOLS_STACK_PRICING_URL redirects the lookup and keeps the output."""
    monkeypatch.setenv("LFTOOLS_STACK_PRICING_URL", "https://pricing.mirror.test/flavors/%s/cost?seconds=%d")
    _cloud_with_one_server(mock_connect)
    mock_urlopen.return_value = _pricing_response(2.5)

    os_stack.cost("test-cloud", "a-stack")

    assert mock_urlopen.call_args.args[0].startswith("https://pricing.mirror.test/flavors/v3-standard-2/cost?seconds=")
    assert mock_urlopen.call_args.kwargs == {"timeout": 60}
    assert capsys.readouterr().out.strip() == "total: 2.5"


@pytest.mark.xfail(strict=True, reason="Pricing endpoint override not yet implemented")
@pytest.mark.parametrize(
    "template",
    [
        pytest.param("http://pricing.mirror.test/%s/cost?seconds=%d", id="plain-http"),
        pytest.param("https:///%s/cost?seconds=%d", id="no-host"),
        pytest.param("https://pricing.mirror.test/flat-rate", id="no-placeholders"),
        pytest.param("https://pricing.mirror.test/%d/cost?seconds=%s", id="swapped-placeholders"),
        pytest.param("https://pricing.mirror.test/%s/cost", id="missing-seconds"),
        pytest.param("https://pricing.mirror.test/%s/cost?seconds=%x", id="integer-only-seconds"),
        pytest.param("https://pricing.mirror.test:not-a-port/%s/cost?seconds=%d", id="malformed-port"),
        pytest.param("https://pricing.mirror.test:99999/%s/cost?seconds=%d", id="port-out-of-range"),
        pytest.param("https://pricing.mirror.test:0/%s/cost?seconds=%d", id="port-zero"),
        pytest.param("https://pricing.mirror.test/v1/bad path/%s/cost?seconds=%d", id="unescaped-space"),
        pytest.param("https://pricing.mirror.test/v1/\t/%s/cost?seconds=%d", id="control-character"),
        pytest.param("https://pricing.mirror.test/v1/pr\u00efce/%s/cost?seconds=%d", id="non-ascii"),
    ],
)
@patch("lftools_uv.openstack.stack.urllib.request.urlopen")
@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_rejects_invalid_pricing_url(mock_connect, mock_urlopen, template, monkeypatch, capsys, caplog):
    """A malformed override fails before contacting OpenStack or the pricing API."""
    monkeypatch.setenv("LFTOOLS_STACK_PRICING_URL", template)

    with pytest.raises(SystemExit) as exc_info:
        os_stack.cost("test-cloud", "a-stack")

    assert exc_info.value.code == 1
    mock_connect.assert_not_called()
    mock_urlopen.assert_not_called()
    assert "total:" not in capsys.readouterr().out
    assert "LFTOOLS_STACK_PRICING_URL" in caplog.text


@pytest.mark.xfail(strict=True, reason="Pricing endpoint override not yet implemented")
@patch("lftools_uv.openstack.stack.urllib.request.urlopen")
@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_accepts_percent_encoded_pricing_url(mock_connect, mock_urlopen, monkeypatch, capsys):
    """A doubled percent sign reaches the pricing API as one percent escape."""
    monkeypatch.setenv("LFTOOLS_STACK_PRICING_URL", "https://pricing.mirror.test/v1/my%%20prices/%s/cost?seconds=%d")
    _cloud_with_one_server(mock_connect)
    mock_urlopen.return_value = _pricing_response(3.75)

    os_stack.cost("test-cloud", "a-stack")

    prefix = "https://pricing.mirror.test/v1/my%20prices/v3-standard-2/cost?seconds="
    url = mock_urlopen.call_args.args[0]
    assert url.startswith(prefix)
    assert url[len(prefix) :].isdigit()
    assert capsys.readouterr().out.strip() == "total: 3.75"


@pytest.mark.xfail(strict=True, reason="Pricing endpoint override not yet implemented")
@pytest.mark.parametrize(
    "template",
    [
        pytest.param("https://pricing.mirror.test/v1/bad%20path/%s/cost?seconds=%d", id="single-percent-escape"),
        pytest.param("https://pricing.mirror.test/v1/%2Fx/%s/cost?seconds=%d", id="escape-read-as-conversion"),
        pytest.param("https://pricing.mirror.test/%s/cost?seconds=%d%", id="trailing-percent"),
    ],
)
@patch("lftools_uv.openstack.stack.urllib.request.urlopen")
@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_explains_doubling_percent_signs(mock_connect, mock_urlopen, template, monkeypatch, caplog):
    """A lone percent sign fails early with an error that says to double it."""
    monkeypatch.setenv("LFTOOLS_STACK_PRICING_URL", template)

    with pytest.raises(SystemExit) as exc_info:
        os_stack.cost("test-cloud", "a-stack")

    assert exc_info.value.code == 1
    mock_connect.assert_not_called()
    mock_urlopen.assert_not_called()
    assert "%%" in caplog.text


@patch("lftools_uv.openstack.stack.urllib.request.urlopen", side_effect=TimeoutError("timed out"))
@patch("lftools_uv.openstack.stack.openstack.connect")
def test_cost_counts_unreachable_pricing_as_zero(mock_connect, mock_urlopen, monkeypatch, capsys):
    """A pricing API that times out still yields a total, as before."""
    monkeypatch.delenv("LFTOOLS_STACK_PRICING_URL", raising=False)
    _cloud_with_one_server(mock_connect)

    os_stack.cost("test-cloud", "a-stack")

    assert capsys.readouterr().out.strip() == "total: 0.0"
