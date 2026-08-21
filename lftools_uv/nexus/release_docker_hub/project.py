# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2018 The Linux Foundation
"""The per-repository copy workflow from Nexus3 to Docker Hub."""

from __future__ import annotations

import logging
from collections.abc import Callable
from functools import total_ordering

import docker
import docker.errors
import docker.models.images
import requests
import tqdm
import urllib3

from lftools_uv.nexus.release_docker_hub import settings
from lftools_uv.nexus.release_docker_hub.tags import DockerTagClass, NexusTagClass, TagClass
from lftools_uv.nexus.release_docker_hub.util import (
    _format_image_id,
    _remove_http_from_url,
)

log = logging.getLogger(__name__)

_RETRY_REASONS: tuple[tuple[type[BaseException], str], ...] = (
    (TimeoutError, "Socket Timeout"),
    (requests.exceptions.ConnectionError, "Connection Error"),
    (urllib3.exceptions.ReadTimeoutError, "Read Timeout Error"),
    (docker.errors.APIError, "API Error"),
)
_RETRY_ERRORS: tuple[type[BaseException], ...] = tuple(exc for exc, _ in _RETRY_REASONS)
_MAX_RETRY_ATTEMPTS: int = 90


@total_ordering
class ProjectClass:
    """Main Project class.

    Main Function of this class, is to pull, and push the missing images from
    Nexus3 to Docker Hub.

    Parameters:
        nexus_proj :  list with ['org', 'repo', 'dockername']
            ['onap', 'aaf/aaf_service', 'aaf-aaf_service']

    Upon class Initialize the following happens.
      * Set Nexus and Docker repository names.
      * Initialize the Nexus and Docker tag variables.
      * Find which tags are needed to be copied.

    Main external function is docker_pull_tag_push
    """

    def __init__(self, nexus_proj: list[str], docker_client: docker.DockerClient | None = None) -> None:
        """Initialize this class."""
        self.org_name: str = nexus_proj[0]
        self.nexus_repo_name: str = nexus_proj[1]
        repo_from_file = len(nexus_proj[2]) > 0
        self.docker_repo_name: str = ""
        if repo_from_file:
            self.docker_repo_name = nexus_proj[2].strip()
        else:
            self._set_docker_repo_name(self.nexus_repo_name)
        self.nexus_tags: NexusTagClass = NexusTagClass(self.org_name, self.nexus_repo_name, repo_from_file)
        self.docker_tags: DockerTagClass = DockerTagClass(self.org_name, self.docker_repo_name, repo_from_file)
        self.tags_2_copy: TagClass = TagClass(self.org_name, self.nexus_repo_name, repo_from_file)
        self._populate_tags_to_copy()
        self.docker_client: docker.DockerClient = docker_client if docker_client is not None else docker.from_env()

    def __lt__(self, other: object) -> bool:
        """Implement sort order based on Nexus3 repo name."""
        if not isinstance(other, ProjectClass):
            return NotImplemented
        return self.nexus_repo_name < other.nexus_repo_name

    def __eq__(self, other: object) -> bool:
        """Equality based on Nexus3 repo name (consistent with __lt__)."""
        if not isinstance(other, ProjectClass):
            return NotImplemented
        return self.nexus_repo_name == other.nexus_repo_name

    def __hash__(self) -> int:
        """Hash based on Nexus3 repo name (consistent with __eq__)."""
        return hash(self.nexus_repo_name)

    def calc_nexus_project_name(self) -> str:
        """Get Nexus3 project name."""
        return self.org_name + "/" + self.nexus_repo_name

    def calc_docker_project_name(self) -> str:
        """Get Docker Hub project name."""
        return self.org_name + "/" + self.docker_repo_name

    def _set_docker_repo_name(self, nexus_repo_name: str) -> None:
        """Set Docker Hub repo name.

        Docker repository will be based on the Nexus3 repo name.
        But replacing all '/' with '-'
        """
        self.docker_repo_name = self.nexus_repo_name.replace("/", "-")
        log.debug(f"ProjName = {self.nexus_repo_name} ---> Docker name = {self.docker_repo_name}")

    def _populate_tags_to_copy(self) -> None:
        """Populate tags_to_copy list.

        Check that all valid Nexus3 tags are among the Docker Hub valid tags.
        If not, add them to the tags_2_copy list.
        """
        log.debug(
            f"Populate {self.docker_repo_name} has valid Nexus3 {len(self.nexus_tags.valid)} and valid Docker Hub {len(self.docker_tags.valid)}"
        )

        if len(self.nexus_tags.valid) > 0:
            for nexustag in self.nexus_tags.valid:
                if nexustag not in self.docker_tags.valid:
                    log.debug(f"Need to copy tag {nexustag} from {self.nexus_repo_name}")
                    self.tags_2_copy.add_tag(nexustag)

    def _pull_tag_push_msg(self, info_text: str, count: int, retry_text: str = "", progbar: bool = False) -> None:
        """Print a formatted message using log.info."""
        due_to_txt = ""
        if len(retry_text) > 0:
            due_to_txt = f"due to {retry_text}"
        _attempt_str = "Attempt "
        b4_txt_template = _attempt_str + "{:2d}"
        b4_txt = "".ljust(len(_attempt_str) + 2)
        if count > 1:
            b4_txt = b4_txt_template.format(count)
        if progbar:
            tqdm.tqdm.write(f"{b4_txt}: {info_text} {due_to_txt}")
        else:
            log.info(f"{b4_txt}: {info_text} {due_to_txt}")

    def _docker_pull(
        self, nexus_image_str: str, count: int, tag: str, retry_text: str = "", progbar: bool = False
    ) -> docker.models.images.Image:
        """Pull an image from Nexus."""
        self._pull_tag_push_msg(
            f"Pulling  Nexus3 image {self.calc_nexus_project_name()} with tag {tag}", count, retry_text
        )
        image = self.docker_client.images.pull(nexus_image_str)
        return image

    def _docker_tag(
        self, count: int, image: docker.models.images.Image, tag: str, retry_text: str = "", progbar: bool = False
    ) -> None:
        """Tag the image with proper docker name and version."""
        self._pull_tag_push_msg(
            f"Creating docker image {self.calc_docker_project_name()} with tag {tag}", count, retry_text
        )
        image.tag(self.calc_docker_project_name(), tag=tag)

    def _docker_push(
        self, count: int, image: docker.models.images.Image, tag: str, retry_text: str, progbar: bool = False
    ) -> None:
        """Push the docker image to Docker Hub."""
        self._pull_tag_push_msg(
            f"Pushing  docker image {self.calc_docker_project_name()} with tag {tag}", count, retry_text
        )
        self.docker_client.images.push(self.calc_docker_project_name(), tag=tag)

    def _docker_cleanup(
        self, count: int, image: docker.models.images.Image, tag: str, retry_text: str = "", progbar: bool = False
    ) -> None:
        """Remove the local copy of the image."""
        image_id = _format_image_id(image.short_id)
        self._pull_tag_push_msg(
            f"Cleanup  docker image {self.calc_docker_project_name()} with tag {tag} and id {image_id}",
            count,
            retry_text,
        )
        self.docker_client.images.remove(image.id, force=True)

    def _retry_stage(self, stage: str, run: Callable[[int, str], None]) -> None:
        """Call *run* until it succeeds, retrying transient Docker failures.

        *run* receives the attempt number and the reason the previous
        attempt failed, both of which appear in the progress output.

        :raises requests.HTTPError: once the retry budget is exhausted.
        """
        attempt = 1
        retry_text = ""
        while True:
            try:
                log.debug("stage = %s. attempt %d, reason %s", stage, attempt, retry_text)
                run(attempt, retry_text)
                return
            except _RETRY_ERRORS as error:
                retry_text = next(text for exc, text in _RETRY_REASONS if isinstance(error, exc))
            attempt += 1
            if attempt > _MAX_RETRY_ATTEMPTS:
                raise requests.HTTPError(retry_text)

    def _copy_tag(self, tag: str, nexus_image_str: str, progbar: bool = False) -> None:
        """Pull one tag from Nexus3, retag it, push it, then drop the local copy.

        Each stage is retried independently, so a transient failure in one
        stage does not restart the stages that already succeeded.
        """
        image: docker.models.images.Image | None = None

        def pull(count: int, retry_text: str) -> None:
            nonlocal image
            image = self._docker_pull(nexus_image_str, count, tag, retry_text, progbar)

        self._retry_stage("pull", pull)
        if image is None:
            return

        pulled = image
        remaining: tuple[tuple[str, Callable[..., None]], ...] = (
            ("tag", self._docker_tag),
            ("push", self._docker_push),
            ("cleanup", self._docker_cleanup),
        )
        for stage, action in remaining:
            self._retry_stage(stage, self._image_stage(action, pulled, tag, progbar))

    @staticmethod
    def _image_stage(
        action: Callable[..., None],
        image: docker.models.images.Image,
        tag: str,
        progbar: bool,
    ) -> Callable[[int, str], None]:
        """Bind an image stage to everything but the per-attempt arguments."""

        def run(count: int, retry_text: str) -> None:
            action(count, image, tag, retry_text, progbar)

        return run

    def docker_pull_tag_push(self, progbar: bool = False) -> None:
        """Copy all missing Docker Hub images from Nexus3.

        This is the main function which will copy a specific tag from Nexu3
        to Docker Hub repository.

        It has 4 stages, pull, tag, push and cleanup.
        Each of these stages, will be retried 10 times upon failures.
        """
        if len(self.tags_2_copy.valid) == 0:
            return

        for tag in self.tags_2_copy.valid:
            org_path = _remove_http_from_url(settings.nexus3_base)
            nexus_image_str = f"{org_path}/{self.org_name}/{self.nexus_repo_name}:{tag}"
            log.debug(f"Nexus Image Str = {nexus_image_str}")
            self._copy_tag(tag, nexus_image_str, progbar)
