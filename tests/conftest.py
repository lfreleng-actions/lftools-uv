# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Fixtures shared by every test module."""

import pytest

# The variables `git rev-parse --local-env-vars` lists: they tie git to one
# repository. A git hook inherits them; in a linked worktree that includes
# an absolute GIT_DIR and GIT_INDEX_FILE. Left set, they would make every
# git command a test runs act on that repository, not the one under
# tmp_path the test created.
GIT_LOCAL_ENV_VARS = (
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_CONFIG",
    "GIT_CONFIG_PARAMETERS",
    "GIT_CONFIG_COUNT",
    "GIT_OBJECT_DIRECTORY",
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_IMPLICIT_WORK_TREE",
    "GIT_GRAFT_FILE",
    "GIT_INDEX_FILE",
    "GIT_NO_REPLACE_OBJECTS",
    "GIT_REPLACE_REF_BASE",
    "GIT_PREFIX",
    "GIT_SHALLOW_FILE",
    "GIT_COMMON_DIR",
)


@pytest.fixture(autouse=True)
def _no_outer_git_repository(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep each test's git commands off any repository the suite runs from."""
    for name in GIT_LOCAL_ENV_VARS:
        monkeypatch.delenv(name, raising=False)
