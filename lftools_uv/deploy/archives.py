# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Collect build archives and logs, and ship them to a Nexus logs repo."""

from __future__ import annotations

import datetime
import errno
import fnmatch
import functools
import os
import re
import shutil
import tempfile
from pathlib import Path, PurePosixPath

from lftools_uv.deploy._build_logs import _capture_build_logs
from lftools_uv.deploy._common import log
from lftools_uv.deploy._late import _copy_archives
from lftools_uv.deploy._util import _compress_text, _format_url, _remove_duplicates_and_sort
from lftools_uv.deploy.nexus import deploy_nexus_zip

# A bracket expression within one component, as fnmatch reads one: a
# "]" straight after "[" or "[!" is a member, so "[]" and "[!]" are not.
_BRACKET = re.compile(r"\[!?+\]?+[^\]/]*\]")
# One piece of a pattern component: a run of "*", one "*", a bracket
# expression, or any other single character.
_PIECE = re.compile(rf"\*{{2,}}|\*|{_BRACKET.pattern}|.", re.DOTALL)


def _below_symlink(workspace: Path, path: Path) -> bool:
    """Return whether a directory between *workspace* and *path* is a symlink."""
    parts = path.relative_to(workspace).parts
    return any((workspace / Path(*parts[:i])).is_symlink() for i in range(1, len(parts)))


def _check_pattern(pattern: str) -> None:
    """Raise ``ValueError`` if *pattern* could match outside the workspace."""
    path = PurePosixPath(pattern)
    if path.is_absolute() or ".." in path.parts:
        raise ValueError(f"Pattern {pattern!r} must stay inside the workspace: it may not be absolute or contain '..'")


def _directory_only(pattern: str) -> bool:
    """Return whether *pattern*, as written, matches only directories."""
    return pattern.endswith(("/", "/.")) or pattern == "."


def _has_star_run(pattern: str) -> bool:
    """Return whether *pattern* holds a run of ``*`` that is not a whole ``**`` component.

    Such a run, inside a bracket expression or outside one, is matched by
    ``_fnmatch_components``: pathlib on Python 3.11 and 3.12 rejects it,
    and no rewrite into plain globstar patterns keeps every meaning it can
    have without multiplying the patterns, and the walks, for each run.
    """
    return any(re.search(r"\*{2,}", part) and part != "**" for part in pattern.split("/"))


def _spanning_match(text: str, part: str) -> bool:
    """Return whether *text*, names joined by ``/``, matches pattern component *part*.

    Only a run of ``*`` outside brackets matches ``/``. A single ``*``,
    ``?``, a bracket expression and any other character match within one
    name, as they do for ``Path.glob``.
    """
    pieces: list[str] = _PIECE.findall(part)

    @functools.cache
    def match(piece: int, start: int) -> bool:
        if piece == len(pieces):
            return start == len(text)
        current: str = pieces[piece]
        if current.startswith("**"):
            return any(match(piece + 1, end) for end in range(start, len(text) + 1))
        if current == "*":
            slash: int = text.find("/", start)
            limit: int = len(text) if slash < 0 else slash
            return any(match(piece + 1, end) for end in range(start, limit + 1))
        if start == len(text) or text[start] == "/":
            return False
        if current == "?" or fnmatch.fnmatchcase(text[start], current):
            return match(piece + 1, start + 1)
        return False

    return match(0, 0)


def _components_match(names: tuple[str, ...], parts: tuple[str, ...]) -> bool:
    """Return whether path components *names* match pattern components *parts*.

    A whole ``**`` part matches zero or more names. A part holding a run
    of ``*`` outside its bracket expressions matches one or more names,
    the run crossing directories as it does everywhere else. Any other
    part matches exactly one name. Results are memoized on the positions
    in *names* and *parts*, so the work grows polynomially with them.
    """

    @functools.cache
    def match(name: int, part: int) -> bool:
        if part == len(parts):
            return name == len(names)
        current: str = parts[part]
        if current == "**":
            return any(match(i, part + 1) for i in range(name, len(names) + 1))
        if any(piece.startswith("**") for piece in _PIECE.findall(current)):
            return any(
                _spanning_match("/".join(names[name:i]), current) and match(i, part + 1)
                for i in range(name + 1, len(names) + 1)
            )
        return name < len(names) and fnmatch.fnmatchcase(names[name], current) and match(name + 1, part + 1)

    return match(0, 0)


def _fnmatch_components(workspace: Path, pattern: str) -> list[Path]:
    """Return the paths below *workspace* whose components match *pattern*'s.

    The workspace is walked once, and each path's components are matched
    with ``_components_match``. A whole ``**`` component matches zero or
    more components, and repeated ones mean the same as one. Bracket
    expressions keep their exact meaning, as in ``logs/[*-**-z].txt``, and
    a run of ``*`` outside brackets crosses directories. A trailing ``**``
    selects what lies below the directories before it, as for
    ``Path.glob``.
    """
    parts: list[str] = []
    for part in pattern.split("/"):
        if part in ("", ".") or (part == "**" and parts and parts[-1] == "**"):
            continue
        parts.append(part)
    if parts and parts[-1] == "**":
        parts.append("*")
    return [path for path in workspace.rglob("*") if _components_match(path.relative_to(workspace).parts, tuple(parts))]


def _globstar(workspace: Path, pattern: str) -> list[Path]:
    """Return the files below *workspace* that match globstar *pattern*.

    ``**`` matches zero or more directories wherever it appears, as in
    bash with globstar set, so ``logs/**/*.txt`` matches ``logs/top.txt``
    as well as ``logs/sub/deep.txt``. A leading ``./`` is ignored, and
    hidden files and directories match. A run of ``*`` inside a
    component, as in ``logs/**.txt`` or ``logs/[**].txt``, keeps its
    meaning: outside brackets it matches any characters, ``/`` included.
    A pattern holding such a run is matched by ``_fnmatch_components`` in
    one walk of the workspace; any other pattern by ``Path.glob``.

    A file below a symlinked directory is never returned, so a symlink
    cannot pull files from outside the workspace into the archive. A
    symlinked file is returned as any other file.
    """
    # Only files are archived, and a pattern ending in "/" or "/." matches
    # directories only.
    if _directory_only(pattern):
        return []
    candidates: list[Path]
    if _has_star_run(pattern):
        candidates = _fnmatch_components(workspace, pattern)
    else:
        normalized: str = str(PurePosixPath(pattern))
        # pathlib returns only directories for a trailing **, so select
        # the files below them instead.
        if normalized == "**" or normalized.endswith("/**"):
            normalized += "/*"
        candidates = list(workspace.glob(normalized))
    matches: dict[Path, None] = {}
    for path in candidates:
        if path in matches or not path.is_file():
            continue
        if _below_symlink(workspace, path):
            log.warning("Not archiving %s: a directory on its path is a symbolic link", path)
            continue
        matches[path] = None
    return list(matches)


def copy_archives(workspace: str, pattern: list[str] | None = None) -> None:
    """Copy files matching PATTERN in a WORKSPACE to the current directory.

    The best way to use this function is to cd into the directory you wish to
    store the files first before calling the function.

    This function provides 2 ways to archive files:

        1) copy $WORKSPACE/archives directory
        2) copy globstar pattern

    :params:

        :arg str pattern: Space-separated list of Unix style glob patterns.
            (default: None)

    :raises ValueError: if a pattern is absolute or contains ``..``,
        before any file is moved.
    """
    for p in pattern or []:
        if p:
            _check_pattern(p)

    archives_dir: str = os.path.join(workspace, "archives")
    dest_dir: str = os.getcwd()

    log.debug("Copying files from %s with pattern '%s' to %s.", workspace, pattern, dest_dir)
    log.debug("archives_dir = %s", archives_dir)

    if os.path.exists(archives_dir):
        if os.path.isfile(archives_dir):
            log.error("Archives %s is a file, not a directory.", archives_dir)
            raise OSError(errno.ENOENT, "Not a directory", archives_dir)
        else:
            log.debug("Archives dir %s does exist.", archives_dir)
            for file_or_dir in os.listdir(archives_dir):
                f: str = os.path.join(archives_dir, file_or_dir)
                try:
                    log.debug("Moving %s", f)
                    _ = shutil.move(f, dest_dir)
                except shutil.Error as e:
                    log.error(e)
                    raise OSError(errno.EPERM, "Could not move to", archives_dir) from e
    else:
        log.error("Archives dir %s does not exist.", archives_dir)
        raise OSError(errno.ENOENT, "Missing directory", archives_dir)

    if pattern is None:
        return

    no_dups_pattern: list[str] = _remove_duplicates_and_sort(pattern)

    paths: list[str] = []

    # Debug: List all files in workspace for troubleshooting
    log.debug("Workspace contents before pattern matching:")
    for root, _dirs, files in os.walk(workspace):
        for file in files:
            rel_path: str = os.path.relpath(os.path.join(root, file), workspace)
            log.debug("  %s", rel_path)

    # Use pathlib for more reliable pattern matching across Python versions
    workspace_path: Path = Path(workspace)

    for p in no_dups_pattern:
        if p == "":  # Skip empty patterns as they are invalid
            continue

        log.debug("Searching for pattern: %s", p)

        absolute_paths: list[str] = [str(path) for path in _globstar(workspace_path, p)]
        log.debug("Found files for pattern '%s': %s", p, absolute_paths)
        paths.extend(absolute_paths)

    log.debug("Files found: %s", paths)

    no_dups_paths: list[str] = _remove_duplicates_and_sort(paths)
    for src in no_dups_paths:
        if len(os.path.basename(src)) > 255:
            log.warning("Filename %s is over 255 characters. Skipping...", os.path.basename(src))

        # relpath, not slicing the WORKSPACE string, so a trailing slash,
        # a relative path or "." still keeps each file's own path.
        dest: str = os.path.join(dest_dir, os.path.relpath(src, workspace))
        log.debug("%s -> %s", src, dest)

        if os.path.isfile(src):
            os.makedirs(os.path.dirname(dest), exist_ok=True)
            _ = shutil.move(src, dest)
        else:
            log.info("Not copying directories: %s.", src)

    if os.environ.get("S3_BUCKET") is not None:
        now: datetime.datetime = datetime.datetime.now()
        p = now.strftime("_%d%m%Y_%H%M%S_")
        for dirpath, _dirnames, files in os.walk(dest_dir):
            if not files:
                fd, _tmp = tempfile.mkstemp(prefix=p, dir=dirpath)
                os.close(fd)
                log.debug("temp file created in dir: %s.", dirpath)


def deploy_archives(nexus_url: str, nexus_path: str, workspace: str, pattern: list[str] | None = None) -> None:
    """Archive files to a Nexus site repository named logs.

    Provides 2 ways to archive files:
        1) $WORKSPACE/archives directory provided by the user.
        2) globstar pattern provided by the user.

    Requirements:

    To use this API a Nexus server must have a site repository configured
    with the name "logs" as this is a hardcoded path.

    Parameters:

        :nexus_url: URL of Nexus server. Eg: https://nexus.opendaylight.org
        :nexus_path: Path on nexus logs repo to place the logs. Eg:
            $SILO/$JENKINS_HOSTNAME/$JOB_NAME/$BUILD_NUMBER
        :workspace: Directory in which to search, typically in Jenkins this is
            $WORKSPACE. A relative path is taken from the current directory.
        :pattern: Space-separated list of Globstar patterns of files to
            archive. (optional)
    """
    nexus_url = _format_url(nexus_url)
    # Anchor a relative WORKSPACE to the caller's directory before changing
    # into staging. Path.absolute keeps "..", which must follow a symlink
    # before it as the shell does; os.path.abspath would fold it away.
    workspace = str(Path(workspace).absolute())
    previous_dir: str = os.getcwd()
    work_dir: str = tempfile.mkdtemp(prefix="lftools-da.")
    os.chdir(work_dir)
    log.debug("workspace: %s, work_dir: %s", workspace, work_dir)

    _copy_archives(workspace, pattern)
    _compress_text(work_dir)

    archives_zip: str = shutil.make_archive(f"{workspace}/archives", "zip")
    log.debug("archives zip: %s", archives_zip)
    deploy_nexus_zip(nexus_url, "logs", nexus_path, archives_zip)

    os.chdir(previous_dir)
    shutil.rmtree(work_dir)


def deploy_logs(nexus_url: str, nexus_path: str, build_url: str) -> None:
    """Deploy logs to a Nexus site repository named logs.

    Fetches logs and system information and pushes them to Nexus
    for log archiving.
    Requirements:

    To use this API a Nexus server must have a site repository configured
    with the name "logs" as this is a hardcoded path.

    Parameters:

        :nexus_url: URL of Nexus server. Eg: https://nexus.opendaylight.org
        :nexus_path: Path on nexus logs repo to place the logs. Eg:
            $SILO/$JENKINS_HOSTNAME/$JOB_NAME/$BUILD_NUMBER
        :build_url: URL of the Jenkins build. Jenkins typically provides this
                    via the $BUILD_URL environment variable.
    """
    nexus_url = _format_url(nexus_url)
    previous_dir: str = os.getcwd()
    work_dir: str = tempfile.mkdtemp(prefix="lftools-dl.")
    os.chdir(work_dir)
    log.debug("work_dir: %s", work_dir)

    _capture_build_logs(build_url)

    _compress_text(work_dir)

    console_zip = tempfile.NamedTemporaryFile(prefix="lftools-dl", delete=True)  # noqa: SIM115
    log.debug("console-zip: %s", console_zip.name)
    _ = shutil.make_archive(console_zip.name, "zip", work_dir)
    deploy_nexus_zip(nexus_url, "logs", nexus_path, f"{console_zip.name}.zip")
    console_zip.close()

    os.chdir(previous_dir)
    shutil.rmtree(work_dir)
