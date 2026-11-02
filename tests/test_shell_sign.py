# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the exit status of ``shell/sign``'s sigul commands.

``sign git-tag`` and ``sign container`` sign with sigul. When sigul fails,
the script, and both front-ends that run it, must fail too, rather than
report an unsigned tag or container as signed.

The script runs under real bash, with a PATH holding only a stub ``sigul``,
which records its arguments and input and exits as the test asks, and a
``sign`` command that runs the script, as the installed one does.
"""

import json
import shutil
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
from click.testing import CliRunner as ClickRunner
from click.testing import Result as ClickResult
from typer.testing import CliRunner as TyperRunner
from typer.testing import Result as TyperResult

from lftools_uv.cli.sign import sign
from lftools_uv.typer_apps.sign import sign_app

XFAIL = pytest.mark.xfail(strict=True, reason="#831: sign git-tag and container exit 0 when sigul fails")

SCRIPT = Path(__file__).resolve().parent.parent / "shell" / "sign"
BASH = shutil.which("bash") or "/bin/bash"

# Records its arguments and standard input, then exits with $SIGUL_EXIT.
SIGUL_STUB = r"""
import json
import os
import sys

with open(os.environ["CALL_LOG"], "a") as log:
    log.write(json.dumps({"args": sys.argv[1:], "stdin": sys.stdin.read()}) + "\n")
status = int(os.environ["SIGUL_EXIT"])
if status:
    print("sigul: authentication failed", file=sys.stderr)
sys.exit(status)
"""

# What the script's sigul commands sign, by subcommand.
SIGNED = {"git-tag": ["v1.0.0"], "container": ["app", "1.0"]}
COMMANDS = pytest.mark.parametrize("command", list(SIGNED))

Run = Callable[[dict[str, str], list[str]], ClickResult | TyperResult]


@pytest.fixture
def sandbox(tmp_path):
    """Return the environment to sign in: a stub sigul, a sign command and sigul's settings."""
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    sigul = bin_dir / "sigul"
    sigul.write_text(f"#!{sys.executable}{SIGUL_STUB}")
    sigul.chmod(0o755)
    wrapper = bin_dir / "sign"
    wrapper.write_text(f'#!/bin/sh\nexec "{BASH}" "{SCRIPT}" "$@"\n')
    wrapper.chmod(0o755)
    password = tmp_path / "sigul-password"
    password.write_text("secret\0")
    return {
        "PATH": str(bin_dir),
        "HOME": str(tmp_path),
        "CALL_LOG": str(tmp_path / "calls.log"),
        "SIGUL_CONFIG": str(tmp_path / "client.conf"),
        "SIGUL_KEY": "release-key",
        "SIGUL_PASSWORD": str(password),
        "SIGUL_EXIT": "0",
    }


def _run(env: dict[str, str], *args: str) -> subprocess.CompletedProcess[str]:
    """Run ``sign`` with *args* in *env*, from its home directory."""
    return subprocess.run(
        [BASH, str(SCRIPT), *args], capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60, check=False
    )


def _calls(env: dict[str, str]) -> list[dict[str, Any]]:
    """Return each call to the sigul stub: its arguments and standard input."""
    log = Path(env["CALL_LOG"])
    return [json.loads(line) for line in log.read_text().splitlines()] if log.exists() else []


def _sigul_args(env: dict[str, str], command: str) -> list[str]:
    """Return the arguments the script should pass sigul for *command*."""
    if command == "git-tag":
        return ["--batch", "-c", env["SIGUL_CONFIG"], "sign-git-tag", "release-key", "v1.0.0"]
    return ["--batch", "-c", env["SIGUL_CONFIG"], "sign-container", "-o", "app-1.0.asc", "release-key", "app", "1.0"]


@COMMANDS
def test_signs_with_sigul(sandbox: dict[str, str], command: str) -> None:
    result = _run(sandbox, command, *SIGNED[command])

    assert result.returncode == 0, result.stderr
    assert _calls(sandbox) == [{"args": _sigul_args(sandbox, command), "stdin": "secret\0"}]


@XFAIL
@COMMANDS
def test_failed_sigul_exits_1(sandbox: dict[str, str], command: str) -> None:
    sandbox["SIGUL_EXIT"] = "3"

    result = _run(sandbox, command, *SIGNED[command])

    assert result.returncode == 1
    assert "ERROR" in result.stderr


@XFAIL
@COMMANDS
def test_missing_password_file_exits_1(sandbox: dict[str, str], command: str) -> None:
    """sigul never runs when its password file cannot be read."""
    sandbox["SIGUL_PASSWORD"] = str(Path(sandbox["HOME"]) / "missing")

    result = _run(sandbox, command, *SIGNED[command])

    assert result.returncode == 1
    assert _calls(sandbox) == []


def _run_click(env: dict[str, str], args: list[str]) -> ClickResult:
    return ClickRunner().invoke(sign, args, obj={}, env=env)


def _run_typer(env: dict[str, str], args: list[str]) -> TyperResult:
    return TyperRunner().invoke(sign_app, args, env=env)


# Each front-end command that runs a sigul subcommand: the Typer front-end
# has no container command.
FRONT_ENDS = pytest.mark.parametrize(
    ("run", "command"),
    [(_run_click, "git-tag"), (_run_typer, "git-tag"), (_run_click, "container")],
    ids=["click-git-tag", "typer-git-tag", "click-container"],
)


@FRONT_ENDS
def test_front_end_signs(sandbox: dict[str, str], run: Run, command: str) -> None:
    result = run(sandbox, [command, *SIGNED[command]])

    assert result.exit_code == 0, result.output
    assert [call["args"] for call in _calls(sandbox)] == [_sigul_args(sandbox, command)]


@XFAIL
@FRONT_ENDS
def test_front_end_reports_failed_signing(sandbox: dict[str, str], run: Run, command: str) -> None:
    """Neither front-end reports a failed signature as a success."""
    sandbox["SIGUL_EXIT"] = "3"

    result = run(sandbox, [command, *SIGNED[command]])

    assert result.exit_code == 1
    assert "Successfully signed" not in result.output
