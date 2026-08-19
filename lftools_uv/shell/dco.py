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

import logging
import os
import re
import subprocess
import sys
from os import chdir, getcwd

log = logging.getLogger(__name__)


def get_branches(path=getcwd(), invert=False):
    """Get a list of branches."""
    if invert:
        invert = "--invert-grep"
    else:
        invert = ""
    chdir(path)
    try:
        branches = (
            subprocess.check_output("git branch -r | grep -v origin/HEAD", shell=True)
            .decode(encoding="UTF-8")
            .splitlines()
        )
        hashlist: list[str] = []
        for branch in branches:
            branch = branch.strip()
            hashes = (
                subprocess.check_output(
                    f'git log {branch} --no-merges --pretty="%H %ae" --grep "Signed-off-by" {invert}',
                    shell=True,
                )
                .decode(encoding="UTF-8")
                .split("\n")
            )
            hashlist = hashlist + hashes
        if hashlist:
            # ``git log`` terminates its output with a newline, so the
            # ``split`` above leaves an empty final element.
            hashlist.pop()
            return hashlist
        else:
            return False
    except subprocess.CalledProcessError as e:
        log.exception(e)
        sys.exit(1)


def check(path=getcwd(), signoffs_dir="dco_signoffs"):
    """Check repository for commits missing DCO."""
    chdir(path)
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
                    log.info(f"{commit}")
                sys.exit(1)
    except subprocess.CalledProcessError as e:
        log.exception(e)
        sys.exit(1)


def match(path=getcwd(), signoffs_dir="dco_signoffs"):
    """Check for commits where DCO does not match the commit author's email."""
    chdir(path)
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

                if commit_author_email not in sob_results and os.path.isdir(signoffs_dir):
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

                log.info(
                    f"For commit ID {commit_id}: \n\tCommitter is {commit_author_email}\n\tbut commit is signed off by {sob_results}\n"
                )
                exit_code = 1

        sys.exit(exit_code)
    except subprocess.CalledProcessError as e:
        log.exception(e)
        sys.exit(1)
