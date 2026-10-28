# -*- code: utf-8 -*-
# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Functions for DCO check tasks."""

__author__ = "DW Talton"

import contextlib
import logging
import os
import re
import subprocess
import sys

from lftools_uv.output import echo

log = logging.getLogger(__name__)


def get_branches(path=".", invert=False):
    """List the commits reachable from ``HEAD`` or any remote-tracking branch.

    Merge commits are left out. Each entry is a commit hash and its author
    email, separated by a space.

    :arg path: Repository to read.
    :arg invert: List the commits without a ``Signed-off-by`` line instead
        of those with one.
    :returns: The entries, or ``False`` when there are none.
    """
    command = ["git", "log", "HEAD", "--remotes", "--no-merges", "--pretty=%H %ae", "--grep", "Signed-off-by"]
    if invert:
        command.append("--invert-grep")
    try:
        hashlist = subprocess.check_output(command, cwd=path).decode(encoding="UTF-8").splitlines()
    except subprocess.CalledProcessError as e:
        log.exception(e)
        sys.exit(1)
    return hashlist or False


def check(path=".", signoffs_dir="dco_signoffs"):
    """Check repository for commits missing DCO."""
    with contextlib.chdir(path):
        _check(".", signoffs_dir)


def _check(path, signoffs_dir):
    """Report commits missing DCO; run inside the repository."""
    try:
        hashes = get_branches(path, invert=True)
        if not hashes:
            sys.exit(0)
        else:
            missing = []
            for commit in hashes:
                if commit:
                    missing.append(commit.split(" ")[0])

            if not missing:
                sys.exit(0)

            # de-dupe the commit list
            missing_list = list(dict.fromkeys(missing))

            if os.path.isdir(signoffs_dir):
                missing_list = [
                    commit
                    for commit in missing_list
                    if subprocess.run(["grep", "-Ri", commit, signoffs_dir], capture_output=True).returncode
                ]

            if missing_list:
                for commit in missing_list:
                    echo(f"{commit}")
                sys.exit(1)
    except subprocess.CalledProcessError as e:
        log.exception(e)
        sys.exit(1)


def match(path=".", signoffs_dir="dco_signoffs"):
    """Check for commits where DCO does not match the commit author's email."""
    with contextlib.chdir(path):
        _match(".", signoffs_dir)


def _match(path, signoffs_dir):
    """Report DCO mismatches; run inside the repository."""
    try:
        hashes = get_branches(path)
        exit_code = 0
        if not hashes:
            sys.exit(exit_code)

        # de-dupe the commit list
        hashes_list = list(dict.fromkeys(hashes))

        for commit in hashes_list:
            commit_id = commit.split(" ")[0]
            if commit_id:
                commit_log_message = subprocess.check_output(
                    f"git log --format=%B -n 1 {commit_id}", shell=True
                ).decode(encoding="UTF-8")
                commit_author_email = (
                    subprocess.check_output(f"git log --format='%ae' {commit_id}^!", shell=True)
                    .decode(encoding="UTF-8")
                    .strip()
                )
                sob_email_regex = r"(?=Signed\-off\-by: ).*[\<](.*)[\>]"
                sob_results = re.findall(sob_email_regex, commit_log_message)

                if commit_author_email in sob_results:
                    continue

                if os.path.isdir(signoffs_dir):
                    dco_file = subprocess.run(
                        ["grep", "-Rli", commit_author_email, signoffs_dir], capture_output=True
                    ).stdout
                    # If commit_author_email and commit_id are in the same file, do not print info
                    if (
                        dco_file
                        and not subprocess.run(
                            ["grep", "-li", commit_id, dco_file.strip()], capture_output=True
                        ).returncode
                    ):
                        continue

                echo(
                    f"For commit ID {commit_id}: \n\tCommitter is {commit_author_email}\n\tbut commit is signed off by {sob_results}\n"
                )
                exit_code = 1

        sys.exit(exit_code)
    except subprocess.CalledProcessError as e:
        log.exception(e)
        sys.exit(1)
