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

            output = "---> {}:\n{}\n".format(" ".join(c), output)
            _ = sysinfo_log.write(output)
            log.info(output)

    build_details.close()

    # Magic string used to trim console logs at the appropriate level during wget
    MAGIC_STRING: str = "-----END_OF_BUILD-----"
    log.info(MAGIC_STRING)

    resp: requests.Response = requests.get(f"{_format_url(build_url)}/consoleText", timeout=30)
    with open("console.log", "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(str(resp.content.decode("utf-8").split(MAGIC_STRING)[0]))

    resp = requests.get(f"{_format_url(build_url)}/timestamps?time=HH:mm:ss&appendLog", timeout=30)
    with open("console-timestamp.log", "w+", encoding="utf-8") as f:  # noqa: PTH123
        _ = f.write(str(resp.content.decode("utf-8").split(MAGIC_STRING)[0]))
