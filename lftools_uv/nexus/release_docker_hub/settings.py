# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2018 The Linux Foundation
"""Mutable settings shared by the release-to-Docker-Hub workflow.

:func:`initialize` establishes these values before any other part of the
workflow runs. Read them as attributes of this module
(``settings.nexus3_base``) rather than importing them by name, so that
readers observe the value current at call time rather than the value bound
when their own module was imported.
"""

from __future__ import annotations

import os
import re

nexus3_base: str = ""
nexus3_catalog: str = ""
nexus3_proj_name_header: str = ""
docker_proj_name_header: str = ""
version_regexp: str = ""
DEFAULT_REGEXP: str = r"^\d+.\d+.\d+$"


def which_version_regexp_to_use(input_regexp_or_filename: str) -> None:
    """Set version regexp as per user request.

    regexp is either a regexp to be directly used, or its a file name,
    and the file contains the regexp to use
    """
    global version_regexp
    if len(input_regexp_or_filename) == 0:
        version_regexp = DEFAULT_REGEXP
    else:
        isFile = os.path.isfile(input_regexp_or_filename)
        if isFile:
            with open(input_regexp_or_filename) as fp:
                version_regexp = fp.readline().strip()
        else:
            version_regexp = input_regexp_or_filename


def validate_regexp() -> bool:
    """Return True when the configured version regexp compiles."""
    try:
        re.compile(version_regexp)
        is_valid = True
    except re.error:
        is_valid = False
    return is_valid


def initialize(org_name: str, input_regexp_or_filename: str = "") -> None:
    """Set constant strings."""
    global nexus3_base
    global nexus3_catalog
    global nexus3_proj_name_header
    global docker_proj_name_header
    nexus3_base = f"https://nexus3.{org_name}.org:10002"
    nexus3_catalog = nexus3_base + "/v2/_catalog"
    nexus3_proj_name_header = "Nexus3 Project Name"
    docker_proj_name_header = "Docker HUB Project Name"
    which_version_regexp_to_use(input_regexp_or_filename)
