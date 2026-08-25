# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the split between command results and diagnostics.

Results must reach stdout so a caller can parse them; diagnostics must reach
stderr so they cannot corrupt that stream. Principle VI of the constitution
requires it, and docs/commands/rtd.rst promises it to callers.

These run the CLI in a subprocess rather than in-process. The logging handler
binds to the real ``sys.stderr`` when ``lftools_uv`` is first imported, so an
in-process test using capsys would capture the wrong stream and prove nothing.
"""

import subprocess
import sys
import textwrap

PROGRAM = """
import logging

import lftools_uv  # noqa: F401  - installs the console handler
from lftools_uv.output import echo

log = logging.getLogger("lftools_uv.test")
echo("result-line")
log.info("info-diagnostic")
log.warning("warning-diagnostic")
log.error("error-diagnostic")
"""


def _run() -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", textwrap.dedent(PROGRAM)],
        capture_output=True,
        text=True,
        check=True,
    )


def test_results_go_to_stdout_alone():
    """stdout carries the result and nothing else."""
    result = _run()

    assert result.stdout == "result-line\n"


def test_diagnostics_go_to_stderr():
    """Every log level lands on stderr, keeping stdout parsable."""
    result = _run()

    assert "info-diagnostic" in result.stderr
    assert "warning-diagnostic" in result.stderr
    assert "error-diagnostic" in result.stderr


def test_diagnostics_never_reach_stdout():
    """The regression this guards: a warning corrupting a --json payload."""
    result = _run()

    for diagnostic in ("info-diagnostic", "warning-diagnostic", "error-diagnostic"):
        assert diagnostic not in result.stdout


def test_level_prefixes_are_applied_to_diagnostics_only():
    """INFO renders bare; higher levels carry their level name."""
    result = _run()

    assert "WARNING: warning-diagnostic" in result.stderr
    assert "ERROR: error-diagnostic" in result.stderr
    assert "info-diagnostic\n" in result.stderr
    assert "INFO: info-diagnostic" not in result.stderr


# ---------------------------------------------------------------------------
# Real commands
#
# The contract above is only worth anything if the commands themselves honour
# it. Sending every log record to stderr moved the *results* of any command
# that still announced them with log.info() onto the wrong stream, so these
# drive real commands end to end through the CLI entry point with their
# backends stubbed, and assert where each stream's content lands.
# ---------------------------------------------------------------------------

_COMMAND_PROGRAM = """
import sys
from unittest import mock

import lftools_uv  # noqa: F401  - installs the console handler
from lftools_uv.cli import main

{setup}

sys.argv = {argv!r}
main()
"""


def _run_command(setup: str, argv: list[str], legacy_cli: bool = False) -> subprocess.CompletedProcess[str]:
    """Run one real CLI command in a subprocess against stubbed backends.

    :arg setup: Python source installing the mocks, run before the command.
        Patches must be started rather than entered as context managers so
        they stay live for the duration of the command.
    :arg argv: Full argument vector, including the program name.
    :arg legacy_cli: Run the deprecated Click CLI instead of the Typer one.
    """
    program = _COMMAND_PROGRAM.format(setup=textwrap.dedent(setup), argv=argv)
    env = {"LEGACY_CLI": "1"} if legacy_cli else {}
    return subprocess.run(  # noqa: S603
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        check=True,
        env={**_base_env(), **env},
    )


def _base_env() -> dict[str, str]:
    """Environment for a command subprocess, minus any CLI selection."""
    import os

    return {key: value for key, value in os.environ.items() if key != "LEGACY_CLI"}


_NEXUS3_SETUP = """
from lftools_uv.api.endpoints import nexus3 as nexus3_api

client = mock.Mock()
client.list_roles.return_value = [["nx-admin"], ["nx-anonymous"]]
_ = mock.patch.object(nexus3_api, "Nexus3", return_value=client).start()
"""


def test_nexus3_role_list_writes_its_table_to_stdout():
    """``nexus3 role list`` puts the role table where a pipe can read it."""
    result = _run_command(_NEXUS3_SETUP, ["lftools-uv", "nexus3", "nexus.example.org", "role", "list"])

    assert "Roles" in result.stdout
    assert "nx-admin" in result.stdout
    assert "nx-anonymous" in result.stdout


def test_nexus3_role_list_keeps_its_table_off_stderr():
    """The same table must not be duplicated onto the diagnostic stream."""
    result = _run_command(_NEXUS3_SETUP, ["lftools-uv", "nexus3", "nexus.example.org", "role", "list"])

    assert "nx-admin" not in result.stderr


_RTD_SETUP = """
from lftools_uv.api.endpoints import readthedocs

client = mock.Mock()
client.project_list.return_value = ["onap-cps", "onap-doc"]
_ = mock.patch.object(readthedocs, "ReadTheDocs", return_value=client).start()
"""

_RTD_ARGV = ["lftools-uv", "rtd", "project-list"]


def test_legacy_rtd_project_list_emits_only_slugs_on_stdout():
    """The legacy Click command still writes a clean, parsable list."""
    result = _run_command(_RTD_SETUP, _RTD_ARGV, legacy_cli=True)

    assert result.stdout == "onap-cps\nonap-doc\n"


def test_legacy_rtd_deprecation_notice_stays_on_stderr():
    """A command emitting both a result and a diagnostic separates them.

    ``rtd`` warns that the legacy group is deprecated on every call. That
    warning must not land in the middle of the project list.
    """
    result = _run_command(_RTD_SETUP, _RTD_ARGV, legacy_cli=True)

    assert "deprecated" in result.stderr
    assert "deprecated" not in result.stdout


_GITHUB_SETUP = """
from lftools_uv import github_helper

first = mock.Mock()
first.name = "repo-a"
second = mock.Mock()
second.name = "repo-b"

org = mock.Mock()
org.get_repos.return_value = [first, second]
client = mock.Mock()
client.get_organization.return_value = org

_ = mock.patch.object(github_helper, "Github", return_value=client).start()
_ = mock.patch.object(github_helper.config, "has_section", return_value=True).start()
_ = mock.patch.object(github_helper.config, "get_setting", return_value="a-token").start()
"""

_GITHUB_ARGV = ["lftools-uv", "github", "list", "example-org", "--repos"]


def test_github_list_repos_keeps_heading_and_names_together():
    """``github list --repos`` must not straddle the two streams.

    The heading already went to stdout while the repository names went to
    the logger; a caller redirecting stdout got the heading and nothing
    else.
    """
    result = _run_command(_GITHUB_SETUP, _GITHUB_ARGV)

    assert "All repos for organization:  example-org" in result.stdout
    assert "repo-a" in result.stdout
    assert "repo-b" in result.stdout


def test_github_list_repos_writes_no_names_to_stderr():
    """None of the listing leaks onto the diagnostic stream."""
    result = _run_command(_GITHUB_SETUP, _GITHUB_ARGV)

    assert "repo-a" not in result.stderr
    assert "repo-b" not in result.stderr


_OPENSTACK_SETUP = """
from types import SimpleNamespace

import openstack.connection

images = [
    SimpleNamespace(
        name="ubuntu-2204",
        visibility="private",
        properties={"ci_managed": "yes"},
        is_protected=False,
        created_at="2026-01-01T00:00:00Z",
    ),
    SimpleNamespace(
        name="ubuntu-2404",
        visibility="private",
        properties={"ci_managed": "yes"},
        is_protected=False,
        created_at="2026-01-02T00:00:00Z",
    ),
]

cloud = mock.Mock()
cloud.list_images.return_value = images
_ = mock.patch.object(openstack.connection, "from_config", return_value=cloud).start()
"""


def test_openstack_image_list_emits_only_names_on_stdout():
    """``openstack image list`` stays pipeable into grep or xargs."""
    result = _run_command(
        _OPENSTACK_SETUP,
        ["lftools-uv", "openstack", "--os-cloud", "test-cloud", "image", "list"],
    )

    assert result.stdout == "ubuntu-2204\nubuntu-2404\n"
