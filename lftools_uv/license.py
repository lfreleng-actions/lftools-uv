# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Scans code for a valid license header."""

from __future__ import annotations

__author__ = "Thanh Ha"


import logging
import os
import re
import sys

log: logging.Logger = logging.getLogger(__name__)


def get_header_text(_file: str) -> str:
    """Scan a file and pulls out the license header.

    Returns a string containing the license header with newlines and copyright
    lines stripped.

    Note: This function only supports '#' comments for license headers.
    """
    text: str = ""
    with open(_file) as data:
        lines: list[str] = data.readlines()
        for line in lines:
            result: re.Match[str] | None = re.search(r"\s*[#]", line)
            if not result:
                break
            string: str = re.sub(r"^\s*#+", "", line).strip()
            if bool(re.match("Copyright", string, re.I)) or bool(  # Ignore the Copyright line
                re.match("^#!", line, re.I)
            ):  # Ignore #! shebang lines
                continue
            text += f" {string}"
    # Strip unnecessary spacing
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _reference_header(license_file: str) -> str:
    """Return the reference header text, refusing one that is empty."""
    text: str = get_header_text(license_file)
    if not text:
        raise ValueError(f"{license_file} has no '#' comment lines to use as a license header.")
    return text


def check_license(license_file: str, code_file: str) -> int:
    """Compare a file with the provided license header.

    Reports if license header is missing or does not match the text of
    license_file. Raises ValueError when license_file has no '#' comment
    lines, since an empty reference header would match every file.
    """
    license_header: str = _reference_header(license_file)
    code_header: str = get_header_text(code_file)

    if license_header not in code_header:
        log.error(f"{code_file} is missing or has incorrect license header.")
        return 1

    return 0


def check_license_directory(license_file: str, directory: str, regex: str = r".+\.py$") -> None:
    """Search a directory for files and calls check_license().

    Exits 1 when any matching file is missing the header, and also when the
    scan checked nothing: the directory does not exist, or no file in it
    matches regex. Raises ValueError when license_file has no '#' comment
    lines.
    """
    if not os.path.isdir(directory):
        log.error(f"{directory} is not a directory.")
        sys.exit(1)

    _reference_header(license_file)

    missing_license: bool = False
    checked: int = 0

    for root, _dirs, files in os.walk(directory):
        for f in files:
            if re.search(regex, f):
                checked += 1
                if check_license(license_file, os.path.join(root, f)):
                    missing_license = True

    if checked == 0:
        log.error(f"No files in {directory} match the regex {regex}.")
        sys.exit(1)

    if missing_license:
        sys.exit(1)

    log.info("Scan completed did not detect any files missing license headers.")
