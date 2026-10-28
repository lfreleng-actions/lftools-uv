# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Capture Jenkins build details, system information and console logs."""

from __future__ import annotations

import subprocess
import sys

import requests

from lftools_uv.deploy._common import log
from lftools_uv.deploy._util import _format_url

# Magic string used to trim console logs at the appropriate level during wget
_MAGIC_STRING: str = "-----END_OF_BUILD-----"


def _write_console_log(url: str, filename: str) -> None:
    """Write the console log at *url* to *filename*, trimmed at the magic string.

    An error status from Jenkins leaves a one-line placeholder instead of
    archiving the error page as the build's console log.
    """
    resp: requests.Response = requests.get(url, timeout=30)
    if resp.ok:
        content = resp.content.decode("utf-8").split(_MAGIC_STRING)[0]
    else:
        log.warning("Could not fetch %s: HTTP %s; %s holds a placeholder", url, resp.status_code, filename)
        content = f"Console log unavailable: {url} returned HTTP {resp.status_code}\n"
    with open(filename, "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(content)


def _capture_build_logs(build_url: str) -> None:
    """Write build details, system info and console logs to the current dir.

    Both ``deploy_logs`` and ``deploy_s3`` gather the same set of files into
    the working directory before shipping it, so they share this helper.
    """
    build_details = open("_build-details.log", "w+")  # noqa: PTH123, SIM115
    _ = build_details.write(f"build-url: {build_url}")

    with open("_sys-info.log", "w+") as sysinfo_log:  # noqa: PTH123
        sys_cmds: list[list[str]] = []

        log.debug("Platform: %s", sys.platform)
        if sys.platform == "linux" or sys.platform == "linux2":
            sys_cmds = [
                ["uname", "-a"],
                ["lscpu"],
                ["nproc"],
                ["df", "-h"],
                ["free", "-m"],
                ["ip", "addr"],
                ["sar", "-b", "-r", "-n", "DEV"],
                ["sar", "-P", "ALL"],
            ]

        for c in sys_cmds:
            try:
                output: str = subprocess.check_output(c).decode("utf-8")  # noqa: S603
            except FileNotFoundError:
                log.debug("Command not found: %s", c)
                continue
            except subprocess.CalledProcessError as e:
                log.warning("Command %s failed with exit status %s; skipping", " ".join(c), e.returncode)
                continue

            output = "---> {}:\n{}\n".format(" ".join(c), output)
            _ = sysinfo_log.write(output)
            log.info(output)

    build_details.close()

    log.info(_MAGIC_STRING)

    _write_console_log(f"{_format_url(build_url)}/consoleText", "console.log")
    _write_console_log(f"{_format_url(build_url)}/timestamps?time=HH:mm:ss&appendLog", "console-timestamp.log")
