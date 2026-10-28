# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for the files ``_capture_build_logs`` leaves in the working dir."""

import logging
import subprocess
from pathlib import Path

import pytest
import requests

from lftools_uv.deploy import _build_logs

BUILD_URL = "https://jenkins.example.org/job/demo/7"
CONSOLE_URL = f"{BUILD_URL}/consoleText"
TIMESTAMPS_URL = f"{BUILD_URL}/timestamps?time=HH:mm:ss&appendLog"
MAGIC = "-----END_OF_BUILD-----"
ERROR_PAGE = "<html><body><h1>Error</h1></body></html>"


def _response(status: int, body: str) -> requests.Response:
    resp = requests.Response()
    resp.status_code = status
    resp._content = body.encode("utf-8")
    return resp


class _Env:
    """Configure the HTTP responses and command failures a test sees."""

    def __init__(self) -> None:
        self.responses: dict[str, requests.Response] = {
            CONSOLE_URL: _response(200, f"console body\n{MAGIC}\ntrailer\n"),
            TIMESTAMPS_URL: _response(200, f"00:00:01 stamped body\n{MAGIC}\ntrailer\n"),
        }
        self.failures: dict[str, BaseException] = {}

    def get(self, url: str, timeout: int | None = None) -> requests.Response:
        return self.responses[url]

    def check_output(self, cmd: list[str]) -> bytes:
        if cmd[0] in self.failures:
            raise self.failures[cmd[0]]
        return f"output of {' '.join(cmd)}\n".encode()


@pytest.fixture
def env(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, caplog: pytest.LogCaptureFixture) -> _Env:
    environment = _Env()
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(_build_logs.sys, "platform", "linux")
    monkeypatch.setattr(_build_logs.requests, "get", environment.get)
    monkeypatch.setattr(_build_logs.subprocess, "check_output", environment.check_output)
    caplog.set_level(logging.WARNING, logger="lftools_uv.deploy")
    return environment


def test_successful_responses_are_trimmed_at_magic_string(env: _Env) -> None:
    _build_logs._capture_build_logs(BUILD_URL)

    assert Path("console.log").read_text() == "console body\n"
    assert Path("console-timestamp.log").read_text() == "00:00:01 stamped body\n"


@pytest.mark.parametrize("status", [404, 500])
@pytest.mark.parametrize(
    ("url", "filename"),
    [(CONSOLE_URL, "console.log"), (TIMESTAMPS_URL, "console-timestamp.log")],
)
def test_error_status_writes_placeholder(
    env: _Env, caplog: pytest.LogCaptureFixture, url: str, filename: str, status: int
) -> None:
    env.responses[url] = _response(status, ERROR_PAGE)

    _build_logs._capture_build_logs(BUILD_URL)

    content = Path(filename).read_text()
    assert "<html>" not in content
    assert url in content
    assert f"HTTP {status}" in content
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any(url in w and str(status) in w for w in warnings)


def test_missing_command_is_skipped(env: _Env) -> None:
    env.failures["sar"] = FileNotFoundError("sar")

    _build_logs._capture_build_logs(BUILD_URL)

    sysinfo = Path("_sys-info.log").read_text()
    assert "output of uname -a" in sysinfo
    assert "output of free -m" in sysinfo
    assert "sar" not in sysinfo


def test_failing_command_is_skipped_with_warning(env: _Env, caplog: pytest.LogCaptureFixture) -> None:
    env.failures["sar"] = subprocess.CalledProcessError(1, ["sar"])

    _build_logs._capture_build_logs(BUILD_URL)

    sysinfo = Path("_sys-info.log").read_text()
    assert "output of uname -a" in sysinfo
    assert "output of free -m" in sysinfo
    assert "sar" not in sysinfo
    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert any("sar" in w for w in warnings)
