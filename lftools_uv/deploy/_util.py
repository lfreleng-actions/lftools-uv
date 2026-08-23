# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Small helpers shared by the deploy entry points."""

from __future__ import annotations

import glob
import gzip
import os
import re
import shutil
import sys
import zipfile
from typing import NoReturn

from defusedxml.minidom import parseString

from lftools_uv.deploy._common import _DEFAULT_URL_SCHEME, log
from lftools_uv.deploy._late import _fail


def _compress_text(dir: str) -> None:
    """Compress all text files in directory."""
    save_dir: str = os.getcwd()
    os.chdir(dir)

    compress_types: list[str] = [
        "**/*.html",
        "**/*.log",
        "**/*.txt",
        "**/*.xml",
    ]
    paths: list[str] = []
    for _type in compress_types:
        search: str = os.path.join(dir, _type)
        paths.extend(glob.glob(search, recursive=True))

    for _file in paths:
        # glob may follow symlink paths that open can't find
        if os.path.exists(_file):
            log.debug("Compressing file %s", _file)
            with open(_file, "rb") as src, gzip.open(f"{_file}.gz", "wb") as dest:  # noqa: PTH123
                shutil.copyfileobj(src, dest)
                os.remove(_file)
        else:
            log.info(f"Could not open path from glob {_file}")

    os.chdir(save_dir)


def _format_url(url: str) -> str:
    """Ensure url starts with http and trim trailing '/'s."""
    start_pattern: re.Pattern[str] = re.compile("^(http|https)://")
    if not start_pattern.match(url):
        url = f"{_DEFAULT_URL_SCHEME}{url}"

    if url.endswith("/"):
        url = url.rstrip("/")

    return url


def _log_error_and_exit(*msg_list: object) -> NoReturn:
    """Print error message, and exit."""
    for msg in msg_list:
        log.error(msg)
    sys.exit(1)


def _get_filenames_in_zipfile(_zipfile: str) -> list[str]:
    """Return a list with file names."""
    files: list[zipfile.ZipInfo] = zipfile.ZipFile(_zipfile).infolist()
    return [f.filename for f in files]


def _get_node_from_xml(xml_data: str, tag_name: str) -> str:
    """Extract tag data from xml data."""
    log.debug("xml=%s", xml_data)

    try:
        dom1 = parseString(xml_data)
        childnode = dom1.getElementsByTagName(tag_name)[0]
    except Exception:
        _fail(f"Received bad XML, can not find tag {tag_name}", xml_data)
    first_child = childnode.firstChild
    if first_child is None:
        _fail(f"Tag {tag_name} has no text content", xml_data)
    return str(first_child.nodeValue)


def _remove_duplicates_and_sort(lst: list[str]) -> list[str]:
    """Remove duplicates from list, and sort it."""
    no_dups_lst: list[str] = list(dict.fromkeys(lst))
    no_dups_lst.sort()

    duplicated_list: list[str] = []
    for item in no_dups_lst:
        if lst.count(item) > 1:
            duplicated_list.append(item)
    log.debug("duplicates  : %s", duplicated_list)

    return no_dups_lst
