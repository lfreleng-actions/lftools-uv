# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests that deploy nexus-stage and infofile check-votes print their results on stdout.

global-jjb reads both from stdout. maven-stage.sh and maven-central.sh take
the staging repository from the line "Staging repository <id> created.", and
check-info-votes.sh keeps the vote count in gerrit_comment.txt. Legacy
lftools printed both there; lftools-uv logged them, which goes to stderr, so
the scripts found nothing.

Each test drives the real HTTP calls through ``responses``, so no test
reaches a server.
"""

import re
from collections.abc import Callable
from pathlib import Path

import pytest
import responses as responses_lib
from click.testing import CliRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperCliRunner
from typer.testing import Result as TyperResult

from lftools_uv import cli
from lftools_uv.typer_apps.deploy import deploy_app

NEXUS = "https://nexus.example.org"
STAGING = f"{NEXUS}/service/local/staging"
PROFILE = "93fb68073c18"
REPO = "autorelease-1234"
GERRIT = "https://gerrit.example.org/r/"
CHANGE = "1234"

Run = Callable[[list[str]], ClickResult | TyperResult]


def _stage_click(args: list[str]) -> ClickResult:
    return CliRunner().invoke(cli.cli, ["deploy", "nexus-stage", *args], obj={})


def _stage_typer(args: list[str]) -> TyperResult:
    return TyperCliRunner().invoke(deploy_app, ["nexus-stage", *args])


FRONT_ENDS = pytest.mark.parametrize("run", [_stage_click, _stage_typer], ids=["click", "typer"])


@pytest.fixture
def m2repo(tmp_path, responses):
    """Return a Maven repository holding one jar, with Nexus staging it as ``REPO``."""
    version = tmp_path / "m2repo" / "org" / "example" / "app" / "1.0"
    version.mkdir(parents=True)
    (version / "app-1.0.jar").write_bytes(b"jar")
    created = f"<promoteResponse><data><stagedRepositoryId>{REPO}</stagedRepositoryId></data></promoteResponse>"
    responses.add(responses.POST, f"{STAGING}/profiles/{PROFILE}/start", body=created, status=201)
    responses.add(responses.PUT, f"{STAGING}/deployByRepositoryId/{REPO}/org/example/app/1.0/app-1.0.jar", status=201)
    responses.add(responses.POST, f"{STAGING}/profiles/{PROFILE}/finish", status=201)
    return tmp_path / "m2repo"


def _staged_repository(stdout: str) -> list[str]:
    """Return what maven-stage.sh extracts: sed -n -e 's/Staging repository \\(.*\\) created\\./\\1/p'."""
    pattern = re.compile(r"Staging repository (.*) created\.")
    return [pattern.sub(r"\1", line) for line in stdout.splitlines() if pattern.search(line)]


@FRONT_ENDS
def test_nexus_stage_stages_and_closes(run: Run, m2repo: Path, responses: responses_lib.RequestsMock) -> None:
    result = run([NEXUS, PROFILE, str(m2repo)])

    assert result.exit_code == 0, result.output
    assert [call.request.url for call in responses.calls] == [
        f"{STAGING}/profiles/{PROFILE}/start",
        f"{STAGING}/deployByRepositoryId/{REPO}/org/example/app/1.0/app-1.0.jar",
        f"{STAGING}/profiles/{PROFILE}/finish",
    ]


@FRONT_ENDS
def test_nexus_stage_prints_staging_repository_on_stdout(run: Run, m2repo: Path) -> None:
    result = run([NEXUS, PROFILE, str(m2repo)])

    assert result.exit_code == 0, result.output
    assert _staged_repository(result.stdout) == [REPO]
    assert f"Completed uploading files to {REPO}." in result.stdout.splitlines()


INFO = """---
project: 'demo'
committers:
    - name: 'Alice Example'
      id: 'alice'
    - name: 'Bob Example'
      id: 'bob'
    - name: 'Carol Example'
      id: 'carol'
"""

# Who has voted, and what check-votes then decides.
VOTES = pytest.mark.parametrize(
    ("voters", "exit_code", "outcome"),
    [
        ([], 1, "No one has voted."),
        (["alice"], 1, "Majority not yet reached"),
        (["alice", "bob"], 0, "Majority committer vote reached"),
    ],
    ids=["none", "minority", "majority"],
)


def _check_votes(tmp_path: Path, responses: responses_lib.RequestsMock, voters: list[str]) -> ClickResult:
    """Run Click's infofile check-votes for ``CHANGE``, with Gerrit answering *voters* as Code-Review +1."""
    reviewers = [
        f'{{"username": "{user}", "approvals": {{"Code-Review": "{"+1" if user in voters else " 0"}"}}}}'
        for user in ("alice", "bob", "carol")
    ]
    responses.add(
        responses.GET,
        f"{GERRIT}changes/{CHANGE}/reviewers",
        body=")]}'\n[" + ",".join(reviewers) + "]",
        content_type="application/json",
    )
    info = tmp_path / "INFO.yaml"
    info.write_text(INFO)
    return CliRunner().invoke(cli.cli, ["infofile", "check-votes", str(info), GERRIT, CHANGE], obj={})


@VOTES
def test_check_votes_exit_code(
    tmp_path: Path, responses: responses_lib.RequestsMock, voters: list[str], exit_code: int, outcome: str
) -> None:
    result = _check_votes(tmp_path, responses, voters)

    assert result.exit_code == exit_code, result.output


@VOTES
def test_check_votes_prints_vote_on_stdout(
    tmp_path: Path, responses: responses_lib.RequestsMock, voters: list[str], exit_code: int, outcome: str
) -> None:
    result = _check_votes(tmp_path, responses, voters)

    assert result.exit_code == exit_code, result.output
    lines = result.stdout.splitlines()
    assert "Number of Committers: 3" in lines
    assert f"Committers that have voted: {voters} ({len(voters)})" in lines
    assert outcome in lines
