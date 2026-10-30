# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""The builds a Jenkins server is running."""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import unquote, urlsplit

if TYPE_CHECKING:
    import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package

log = logging.getLogger(__name__)

# Every executor of every node, in one request. A Pipeline build runs on a
# node's one-off executors, so those are read as well as the regular ones.
_EXECUTORS = ("executors", "oneOffExecutors")
_TREE = "computer[displayName,{}]".format(",".join(f"{key}[currentExecutable[url]]" for key in _EXECUTORS))


class BuildsError(Exception):
    """Jenkins answered without listing its nodes' executors."""


@dataclass(frozen=True)
class RunningBuild:
    """A build occupying an executor of a node."""

    job: str
    node: str


def _job_name(url: str) -> str:
    """Return the full name, such as ``folder/job``, of the job a build URL belongs to.

    A URL without a ``/job/`` segment is returned whole.
    """
    names: list[str] = []
    parts = iter(urlsplit(url).path.split("/"))
    for part in parts:
        if part == "job":
            names.append(unquote(next(parts, "")))
    return "/".join(names) or url


def _listed(value: Any, what: str) -> list[Any]:
    """Return *value*, Jenkins' list of *what*; raise if it is not a list."""
    if not isinstance(value, list):
        msg = f"Jenkins did not list {what}: {value!r}"
        raise BuildsError(msg)
    return value


def running_builds(server: jenkins.Jenkins) -> list[RunningBuild]:
    """Return every build running on any of *server*'s nodes.

    One request reads the regular and one-off executors of every node, so
    no node is skipped and Pipeline builds are included. An executor busy
    with something that has no URL is logged and left out.

    Raises:
        BuildsError: If the answer does not list the nodes and their executors.
    """
    info = server.get_info(item="computer", query=f"?tree={_TREE}")
    if not isinstance(info, dict):
        msg = f"Jenkins did not list its nodes: {info!r}"
        raise BuildsError(msg)
    computers = _listed(info.get("computer"), "its nodes")
    builds: list[RunningBuild] = []
    for computer in computers:
        if not isinstance(computer, dict):
            msg = f"Jenkins listed a node as {computer!r}"
            raise BuildsError(msg)
        node = str(computer.get("displayName"))
        for key in _EXECUTORS:
            for executor in _listed(computer.get(key), f"the {key} of node {node}"):
                current = executor.get("currentExecutable") if isinstance(executor, dict) else None
                if not current:
                    continue
                url = current.get("url") if isinstance(current, dict) else None
                if not isinstance(url, str) or not url:
                    log.warning("Node %s is running %r, which has no URL; it is not listed", node, current)
                    continue
                builds.append(RunningBuild(_job_name(url), node))
    return builds
