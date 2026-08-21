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
