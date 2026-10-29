# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for OpenStack image, server and volume cleanup failures.

``server cleanup`` and ``volume cleanup`` must read the cloud name from
a real openstacksdk connection. A delete OpenStack refuses, or one that
times out, must not stop the cleanup: it is logged, the rest are still
removed, and the command exits 1. ``volume remove`` with an unknown ID
must exit 1 without a traceback. ``--days`` must give the same result
in every local time zone. Every case runs through both the Click and
the Typer front-ends.

The connection is a real, offline openstacksdk ``Connection`` whose API
methods each test replaces: no test reaches OpenStack or the network,
or reads a ``clouds.yaml``.
"""

import logging
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import openstack
import openstack.connection
import pytest
from click.testing import CliRunner as ClickRunner
from openstack.exceptions import ConflictException, NotFoundException, ResourceTimeout, SDKException
from typer.testing import CliRunner as TyperRunner

from lftools_uv.openstack import cmd as os_cmd
from lftools_uv.typer_apps.openstack import openstack_app

PROJECT_ID = "project-0001"
NOVA_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
CINDER_FORMAT = "%Y-%m-%dT%H:%M:%S.%f"


def _invoke_click(args: list[str]) -> Any:
    return ClickRunner().invoke(os_cmd.openstack, ["--os-cloud", "test-cloud", *args], obj={})


def _invoke_typer(args: list[str]) -> Any:
    return TyperRunner().invoke(openstack_app, ["--os-cloud", "test-cloud", *args])


FRONT_ENDS = pytest.mark.parametrize("invoke", [_invoke_click, _invoke_typer], ids=["click", "typer"])


@pytest.fixture
def cloud(monkeypatch):
    """Return a real, offline openstacksdk connection used by every command."""
    conn = openstack.connect(
        auth_url="http://127.0.0.1:9/v3",
        username="tester",
        password="not-a-secret",  # noqa: S106  # nosec B106
        project_name="test-project",
        user_domain_name="Default",
        project_domain_name="Default",
        load_yaml_config=False,
        load_envvars=False,
    )
    monkeypatch.setattr(openstack.connection, "from_config", lambda **_kwargs: conn)
    return conn


@pytest.fixture
def local_tz():
    """Set the process time zone for one test and restore it afterwards."""
    if not hasattr(time, "tzset"):
        pytest.skip("time.tzset is not available on this platform")
    original = os.environ.get("TZ")

    def _set(zone: str) -> None:
        os.environ["TZ"] = zone
        time.tzset()

    yield _set

    if original is None:
        os.environ.pop("TZ", None)
    else:
        os.environ["TZ"] = original
    time.tzset()


class FakeDelete:
    """Record each delete call and raise the given exception for given IDs."""

    def __init__(self, failures: dict[str, Exception] | None = None) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.failures = failures or {}

    def __call__(self, name_or_id: str, **kwargs: Any) -> bool:
        self.calls.append((name_or_id, kwargs))
        if name_or_id in self.failures:
            raise self.failures[name_or_id]
        return True

    @property
    def ids(self) -> list[str]:
        """Return the IDs passed to each call, in order."""
        return [name_or_id for name_or_id, _ in self.calls]


def _created(age: timedelta, fmt: str) -> str:
    return (datetime.now(UTC) - age).strftime(fmt)


def _image(name: str, age: timedelta) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        id=f"{name}-id",
        created_at=_created(age, NOVA_FORMAT),
        visibility="private",
        properties={},
        is_protected=False,
        owner=PROJECT_ID,
    )


def _server(name: str, age: timedelta) -> SimpleNamespace:
    return SimpleNamespace(name=name, id=f"{name}-id", created_at=_created(age, NOVA_FORMAT))


def _volume(name: str, age: timedelta) -> SimpleNamespace:
    return SimpleNamespace(name=name, id=f"{name}-id", created_at=_created(age, CINDER_FORMAT))


def _stub_images(
    monkeypatch: pytest.MonkeyPatch, cloud: Any, images: list[SimpleNamespace], delete: FakeDelete
) -> None:
    monkeypatch.setattr(cloud, "list_images", lambda *_args, **_kwargs: images)
    monkeypatch.setattr(cloud, "delete_image", delete)
    monkeypatch.setattr(cloud, "_get_project_info", lambda *_args, **_kwargs: {"id": PROJECT_ID})


def _stub_servers(
    monkeypatch: pytest.MonkeyPatch, cloud: Any, servers: list[SimpleNamespace], delete: FakeDelete
) -> None:
    monkeypatch.setattr(cloud, "list_servers", lambda *_args, **_kwargs: servers)
    monkeypatch.setattr(cloud, "delete_server", delete)


def _stub_volumes(
    monkeypatch: pytest.MonkeyPatch, cloud: Any, volumes: list[SimpleNamespace], delete: FakeDelete
) -> None:
    monkeypatch.setattr(cloud, "list_volumes", lambda *_args, **_kwargs: volumes)
    monkeypatch.setattr(cloud, "delete_volume", delete)


def _get_volume(volumes: list[SimpleNamespace], error: Exception | None = None) -> Callable[[str], Any]:
    def _lookup(volume_id: str) -> Any:
        if error is not None:
            raise error
        return next((v for v in volumes if v.id == volume_id), None)

    return _lookup


def _errors(caplog: pytest.LogCaptureFixture) -> str:
    return "\n".join(r.getMessage() for r in caplog.records if r.levelno == logging.ERROR)


# --- #961: read the cloud name from the connection's config ---------------


@FRONT_ENDS
def test_server_cleanup_deletes_old_servers(invoke, cloud, monkeypatch, caplog):
    """``server cleanup`` deletes only the servers older than ``--days``."""
    old, new = _server("old", timedelta(days=10)), _server("new", timedelta(days=1))
    delete = FakeDelete()
    _stub_servers(monkeypatch, cloud, [old, new], delete)

    with caplog.at_level(logging.INFO):
        result = invoke(["server", "cleanup", "--days", "5"])

    assert result.exit_code == 0, result.exception
    assert delete.ids == [old.id]
    assert "Removing 1 servers from defaults." in caplog.text


@FRONT_ENDS
def test_volume_cleanup_deletes_old_volumes(invoke, cloud, monkeypatch, caplog):
    """``volume cleanup`` deletes only the volumes older than ``--days``."""
    old, new = _volume("old", timedelta(days=10)), _volume("new", timedelta(days=1))
    delete = FakeDelete()
    _stub_volumes(monkeypatch, cloud, [old, new], delete)

    with caplog.at_level(logging.INFO):
        result = invoke(["volume", "cleanup", "--days", "5"])

    assert result.exit_code == 0, result.exception
    assert delete.ids == [old.id]
    assert "Removing 1 volumes from defaults." in caplog.text


# --- #962: keep cleaning up after a failed delete --------------------------


@pytest.mark.xfail(strict=True, reason="#962: a refused delete stops image cleanup")
@FRONT_ENDS
def test_image_cleanup_continues_after_failure(invoke, cloud, monkeypatch, caplog):
    """A refused image delete is logged, the rest are removed, and it exits 1."""
    images = [_image(name, timedelta(days=40)) for name in ("img-a", "img-b", "img-c")]
    delete = FakeDelete({images[0].id: ConflictException("409 Conflict")})
    _stub_images(monkeypatch, cloud, images, delete)

    result = invoke(["image", "cleanup", "--days", "30"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert delete.ids == [image.id for image in images]
    assert images[0].id in _errors(caplog)


@pytest.mark.xfail(strict=True, reason="#962: a refused delete stops server cleanup")
@FRONT_ENDS
def test_server_cleanup_continues_after_failure(invoke, cloud, monkeypatch, caplog):
    """A refused server delete is logged, the rest are removed, and it exits 1."""
    servers = [_server(name, timedelta(days=10)) for name in ("srv-a", "srv-b")]
    delete = FakeDelete({servers[0].id: SDKException("Error in deleting server")})
    _stub_servers(monkeypatch, cloud, servers, delete)

    result = invoke(["server", "cleanup", "--days", "5"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert delete.ids == [server.id for server in servers]
    assert servers[0].id in _errors(caplog)


@pytest.mark.xfail(strict=True, reason="#962: volume deletes wait without limit and stop cleanup")
@FRONT_ENDS
def test_volume_cleanup_bounds_and_survives_timeout(invoke, cloud, monkeypatch, caplog):
    """A timed-out volume delete is logged, the rest are removed, and it exits 1."""
    volumes = [_volume(name, timedelta(days=10)) for name in ("vol-a", "vol-b")]
    delete = FakeDelete({volumes[0].id: ResourceTimeout("Timeout waiting for the volume to be deleted.")})
    _stub_volumes(monkeypatch, cloud, volumes, delete)

    result = invoke(["volume", "cleanup", "--days", "5"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert delete.ids == [volume.id for volume in volumes]
    assert all(kwargs.get("timeout") for _, kwargs in delete.calls)
    assert volumes[0].id in _errors(caplog)


@pytest.mark.xfail(strict=True, reason="#962: an unknown volume ID ends in a NotFoundException traceback")
@FRONT_ENDS
def test_volume_remove_unknown_id(invoke, cloud, monkeypatch, caplog):
    """``volume remove`` with an unknown ID logs it and exits 1."""
    delete = FakeDelete()
    monkeypatch.setattr(cloud, "get_volume_by_id", _get_volume([], NotFoundException("No Volume found")))
    monkeypatch.setattr(cloud, "delete_volume", delete)

    result = invoke(["volume", "remove", "vol-missing"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert delete.calls == []
    assert "vol-missing" in _errors(caplog)


@pytest.mark.xfail(strict=True, reason="#962: volume remove waits without limit for the delete")
@FRONT_ENDS
def test_volume_remove_timeout(invoke, cloud, monkeypatch, caplog):
    """A timed-out ``volume remove`` is bounded, logged, and exits 1."""
    volume = _volume("stuck", timedelta(hours=2))
    delete = FakeDelete({volume.id: ResourceTimeout("Timeout waiting for the volume to be deleted.")})
    monkeypatch.setattr(cloud, "get_volume_by_id", _get_volume([volume]))
    monkeypatch.setattr(cloud, "delete_volume", delete)

    result = invoke(["volume", "remove", volume.id, "--minutes", "15"])

    assert result.exit_code == 1
    assert isinstance(result.exception, SystemExit)
    assert len(delete.calls) == 1
    assert delete.calls[0][1].get("timeout")
    assert volume.id in _errors(caplog)


# --- #963: compare resource ages in UTC ------------------------------------

SHIFTED_ZONES = pytest.mark.parametrize("zone", ["Pacific/Kiritimati", "America/Los_Angeles"])


@pytest.mark.xfail(strict=True, reason="#963: --days compares UTC created_at with local time")
@SHIFTED_ZONES
@FRONT_ENDS
def test_image_cleanup_days_in_any_zone(invoke, zone, cloud, monkeypatch, local_tz):
    """``image cleanup --days 1`` removes only the image older than a day."""
    local_tz(zone)
    young, old = _image("young", timedelta(hours=20)), _image("old", timedelta(hours=30))
    delete = FakeDelete()
    _stub_images(monkeypatch, cloud, [young, old], delete)

    result = invoke(["image", "cleanup", "--days", "1"])

    assert result.exit_code == 0, result.exception
    assert delete.ids == [old.id]


@pytest.mark.xfail(strict=True, reason="#963: --days compares UTC created_at with local time")
@SHIFTED_ZONES
@FRONT_ENDS
def test_server_list_days_in_any_zone(invoke, zone, cloud, monkeypatch, local_tz):
    """``server list --days 1`` lists only the server older than a day."""
    local_tz(zone)
    servers = [_server("young", timedelta(hours=20)), _server("old", timedelta(hours=30))]
    monkeypatch.setattr(cloud, "list_servers", lambda *_args, **_kwargs: servers)

    result = invoke(["server", "list", "--days", "1"])

    assert result.exit_code == 0, result.exception
    assert result.stdout == "old\n"


@pytest.mark.xfail(strict=True, reason="#963: --days compares UTC created_at with local time")
@SHIFTED_ZONES
@FRONT_ENDS
def test_volume_list_days_in_any_zone(invoke, zone, cloud, monkeypatch, local_tz):
    """``volume list --days 1`` lists only the volume older than a day."""
    local_tz(zone)
    volumes = [_volume("young", timedelta(hours=20)), _volume("old", timedelta(hours=30))]
    monkeypatch.setattr(cloud, "list_volumes", lambda *_args, **_kwargs: volumes)

    result = invoke(["volume", "list", "--days", "1"])

    assert result.exit_code == 0, result.exception
    assert result.stdout == "old\n"


# --- Behaviour that already holds and must keep holding -------------------


@FRONT_ENDS
def test_image_cleanup_deletes_old_images(invoke, cloud, monkeypatch):
    """``image cleanup --days 30`` deletes only the image older than 30 days."""
    old, new = _image("old", timedelta(days=40)), _image("new", timedelta(days=1))
    delete = FakeDelete()
    _stub_images(monkeypatch, cloud, [old, new], delete)

    result = invoke(["image", "cleanup", "--days", "30"])

    assert result.exit_code == 0, result.exception
    assert delete.ids == [old.id]


@FRONT_ENDS
def test_volume_remove_old_volume(invoke, cloud, monkeypatch):
    """``volume remove --minutes 15`` deletes a two-hour-old volume."""
    volume = _volume("old", timedelta(hours=2))
    delete = FakeDelete()
    monkeypatch.setattr(cloud, "get_volume_by_id", _get_volume([volume]))
    monkeypatch.setattr(cloud, "delete_volume", delete)

    result = invoke(["volume", "remove", volume.id, "--minutes", "15"])

    assert result.exit_code == 0, result.exception
    assert delete.ids == [volume.id]


@FRONT_ENDS
def test_image_cleanup_days_in_utc(invoke, cloud, monkeypatch, local_tz):
    """In UTC, ``image cleanup --days 1`` removes only the older image."""
    local_tz("UTC")
    young, old = _image("young", timedelta(hours=20)), _image("old", timedelta(hours=30))
    delete = FakeDelete()
    _stub_images(monkeypatch, cloud, [young, old], delete)

    result = invoke(["image", "cleanup", "--days", "1"])

    assert result.exit_code == 0, result.exception
    assert delete.ids == [old.id]
