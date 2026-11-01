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

import gzip
import os
import re
import secrets
import shutil
import sys
import zipfile
from typing import NoReturn

from defusedxml.minidom import parseString

from lftools_uv.deploy._common import _DEFAULT_URL_SCHEME, log
from lftools_uv.deploy._late import _fail


def _files_below(root: str) -> list[str]:
    """Return the files below *root*, relative to it, sorted.

    Hidden files and directories are included. Symlinked directories are
    skipped, never followed: ``copy_archives`` stages the workspace's
    ``archives/`` directory as it is, symlinks included, and following
    one would compress, delete or upload files outside the staging tree.
    """
    files: list[str] = []
    for dirpath, _dirnames, filenames in os.walk(root, followlinks=False):
        files.extend(os.path.relpath(os.path.join(dirpath, name), root) for name in filenames)
    return sorted(files)


def _gzip_beside(path: str) -> None:
    """Write *path*'s contents, gzipped, to ``<path>.gz``.

    The output never goes through a symlink at ``<path>.gz``: staging can
    hold symlinks from the workspace's ``archives/`` directory, and
    writing through one would overwrite a file outside the staging tree.
    The data goes to a new temporary file beside *path*, created
    exclusively, which then replaces ``<path>.gz`` by rename.
    """
    # A short name of its own, so a source name near the length limit
    # still fits; it is renamed away or removed before anything lists it.
    temporary = os.path.join(os.path.dirname(path), f".lftools-gz-{secrets.token_hex(8)}")
    descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o666)
    try:
        with (
            os.fdopen(descriptor, "wb") as raw,
            open(path, "rb") as src,  # noqa: PTH123
            gzip.GzipFile(filename=f"{os.path.basename(path)}.gz", mode="wb", fileobj=raw) as dest,
        ):
            shutil.copyfileobj(src, dest)
        os.replace(temporary, f"{path}.gz")
    except BaseException:
        if os.path.lexists(temporary):
            os.remove(temporary)
        raise


def _compress_text(dir: str) -> None:
    """Gzip every text file below *dir* in place, hidden ones included.

    Symlinked directories are not followed; see ``_files_below``.
    """
    compress_suffixes: tuple[str, ...] = (".html", ".log", ".txt", ".xml")
    compressed: list[str] = []
    for name in _files_below(dir):
        if not name.endswith(compress_suffixes):
            continue
        _file: str = os.path.join(dir, name)
        # A broken symlink can't be read
        if os.path.exists(_file):
            log.debug("Compressing file %s", _file)
            _gzip_beside(_file)
            compressed.append(_file)
        else:
            log.info(f"Could not open path {_file}")
    # Remove the originals only once every file is compressed: a staged
    # symlink may point at another text file, which must still be there
    # when the symlink is read.
    for _file in compressed:
        os.remove(_file)


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
