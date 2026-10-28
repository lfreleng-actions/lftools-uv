# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for ``deploy nexus`` and ``deploy nexus-stage`` with nothing to deploy.

A directory holding only files the deploy filters skip has nothing to
upload. Both commands fail rather than report success, and
``nexus-stage`` creates no staging repository, unless ``--allow-empty``
is given.
"""

from unittest import mock

import pytest
from click.testing import CliRunner
from typer.testing import CliRunner as TyperCliRunner

import lftools_uv.deploy as deploy_sys
from lftools_uv import cli
from lftools_uv.typer_apps.deploy import deploy_app

NEXUS_REPO_URL = "https://nexus.example.org/content/repositories/releases"

runner = CliRunner()
typer_runner = TyperCliRunner()


@pytest.fixture
def empty_dir(tmp_path, monkeypatch):
    """Return a deploy directory holding only files the filters skip."""
    monkeypatch.chdir(tmp_path)
    deploy_dir = tmp_path / "m2repo"
    artifact_dir = deploy_dir / "org" / "example" / "app"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "_remote.repositories").write_text("remote\n")
    (artifact_dir / "maven-metadata.xml").write_text("<metadata/>\n")
    return str(deploy_dir)


def test_deploy_nexus_empty_raises(empty_dir, responses):
    """An empty directory raises ``FileNotFoundError`` naming the flag."""
    with pytest.raises(FileNotFoundError, match="--allow-empty"):
        deploy_sys.deploy_nexus(NEXUS_REPO_URL, empty_dir)
    assert not responses.calls


def test_deploy_nexus_empty_allowed(empty_dir, responses):
    """With ``allow_empty`` an empty directory uploads nothing and returns."""
    deploy_sys.deploy_nexus(NEXUS_REPO_URL, empty_dir, allow_empty=True)
    assert not responses.calls


def test_deploy_nexus_stage_empty_creates_no_repo(empty_dir):
    """An empty directory raises before a staging repository is created."""
    with (
        mock.patch("lftools_uv.deploy.nexus.nexus_stage_repo_create", return_value="repo-1") as create,
        mock.patch("lftools_uv.deploy.nexus.nexus_stage_repo_close") as close,
        pytest.raises(FileNotFoundError, match="--allow-empty"),
    ):
        deploy_sys.deploy_nexus_stage("https://nexus.example.org", "profile", empty_dir)
    create.assert_not_called()
    close.assert_not_called()


def _invoke_legacy(args):
    return runner.invoke(cli.cli, ["deploy", *args], obj={})


def _invoke_typer(args):
    return typer_runner.invoke(deploy_app, args)


FRONT_ENDS = {"click": _invoke_legacy, "typer": _invoke_typer}


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_cli_deploy_nexus_empty_exits_1(empty_dir, responses, front_end):
    """``deploy nexus`` exits 1 for an empty directory."""
    result = FRONT_ENDS[front_end](["nexus", NEXUS_REPO_URL, empty_dir])
    assert result.exit_code == 1


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_cli_deploy_nexus_allow_empty_exits_0(empty_dir, responses, front_end):
    """``deploy nexus --allow-empty`` exits 0 for an empty directory."""
    result = FRONT_ENDS[front_end](["nexus", NEXUS_REPO_URL, empty_dir, "--allow-empty"])
    assert result.exit_code == 0


@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_cli_deploy_nexus_stage_passes_allow_empty(empty_dir, front_end):
    """``deploy nexus-stage --allow-empty`` passes the flag on."""
    with mock.patch("lftools_uv.deploy.deploy_nexus_stage") as stage:
        result = FRONT_ENDS[front_end](
            ["nexus-stage", "https://nexus.example.org", "profile", empty_dir, "--allow-empty"]
        )
    assert result.exit_code == 0
    assert stage.call_args.kwargs["allow_empty"] is True


def test_deploy_nexus_uploads_file(tmp_path, monkeypatch, responses):
    """A directory holding one jar uploads that jar."""
    monkeypatch.chdir(tmp_path)
    deploy_dir = tmp_path / "m2repo"
    artifact_dir = deploy_dir / "org" / "example" / "app" / "1.0"
    artifact_dir.mkdir(parents=True)
    (artifact_dir / "app-1.0.jar").write_bytes(b"jar")
    jar_url = f"{NEXUS_REPO_URL}/org/example/app/1.0/app-1.0.jar"
    responses.add(responses.PUT, jar_url, status=201)

    deploy_sys.deploy_nexus(NEXUS_REPO_URL, str(deploy_dir))

    assert [call.request.url for call in responses.calls] == [jar_url]
