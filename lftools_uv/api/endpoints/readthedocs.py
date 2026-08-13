# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Read the Docs REST API interface.

Every method in this module returns typed Python data (``dict``,
``list`` or ``bool``) and raises a :class:`ReadTheDocsError` subclass on
failure. Presentation concerns -- JSON serialisation, table rendering
and human-readable prose -- belong to the command-line layer in
:mod:`lftools_uv.typer_apps.rtd`.
"""

from __future__ import annotations

__author__ = "DW Talton"

import json
import re
from typing import TYPE_CHECKING, cast

import lftools_uv.api.client as client
from lftools_uv import config
from lftools_uv.api.client import ApiResponse

if TYPE_CHECKING:
    from collections.abc import Mapping

    import requests

_LIST_OBJECT_TYPE = list[object]
_DICT_STR_OBJECT_TYPE = dict[str, object]

_HTTP_NOT_FOUND = 404
_HTTP_BAD_REQUEST = 400

#: Characters Read the Docs preserves verbatim in a version slug.
_SLUG_KEEP = re.compile(r"[^a-z0-9._-]+")


# ---------------------------------------------------------------------------
# Error hierarchy
# ---------------------------------------------------------------------------


class ReadTheDocsError(Exception):
    """Base class for all Read the Docs errors raised by this module."""


class ReadTheDocsAPIError(ReadTheDocsError):
    """Raised when the Read the Docs API returns an error response.

    Carries the HTTP status code so callers can branch on it rather
    than matching against prose in the response body.
    """

    def __init__(self, message: str, status_code: int) -> None:
        super().__init__(message)
        self.status_code = status_code


class ReadTheDocsNotFoundError(ReadTheDocsAPIError):
    """Raised when a project, version, build or subproject is absent."""

    def __init__(self, message: str) -> None:
        super().__init__(message, _HTTP_NOT_FOUND)


class ReadTheDocsValidationError(ReadTheDocsError):
    """Raised for client-side validation failures."""


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------


def version_slug(branch: str) -> str:
    """Convert a branch name into a Read the Docs version slug.

    Read the Docs stores a version under a slugified form of the branch
    name: it lowercases the value and replaces every character outside
    ``[a-z0-9._-]`` with a hyphen. A branch named ``maintenance/3.7.10``
    is therefore addressable as ``maintenance-3.7.10``, and ``mr/879/1``
    as ``mr-879-1``.

    Passing an unslugified branch name to the API produces a request
    path that does not resolve, so always route branch names through
    this function before building a request.

    Args:
        branch: A git branch name, for example ``maintenance/3.7.10``.

    Returns:
        The corresponding Read the Docs version slug.

    Raises:
        ReadTheDocsValidationError: If ``branch`` is empty, or slugifies
            to an empty string.
    """
    if not branch or not branch.strip():
        msg = "Branch name cannot be empty"
        raise ReadTheDocsValidationError(msg)

    slug = _SLUG_KEEP.sub("-", branch.strip().lower()).strip("-")

    if not slug:
        msg = f"Branch name {branch!r} does not yield a usable version slug"
        raise ReadTheDocsValidationError(msg)

    return slug


class ReadTheDocs(client.RestApi):
    """API endpoint wrapper for readthedocs.org.

    Be sure to always include the trailing "/" when adding
    new methods.
    """

    def __init__(self, **params: str | dict[str, str]) -> None:
        """Initialize the class."""
        self.params: dict[str, str | dict[str, str]] = params
        if "creds" not in self.params:
            creds: dict[str, str] = {
                "authtype": "token",
                "token": config.get_setting("rtd", "token"),
                "endpoint": config.get_setting("rtd", "endpoint"),
            }
            params["creds"] = creds

        super().__init__(**params)

    # -- Response handling ---------------------------------------------------

    @staticmethod
    def _detail_of(response: ApiResponse) -> str:
        """Return the API's ``detail`` message, when it supplies one."""
        if isinstance(response, tuple):
            body = response[1]
            if isinstance(body, dict):
                detail = body.get("detail")
                if isinstance(detail, str):
                    return detail
            if isinstance(body, str) and body:
                return body
        return ""

    def _check(self, response: ApiResponse, context: str) -> requests.Response:
        """Raise a typed error when a response carries a failure status.

        Args:
            response: The value returned by a request helper.
            context: Human-readable description of the attempted
                operation, used to build the error message.

        Returns:
            The underlying :class:`requests.Response`.

        Raises:
            ReadTheDocsNotFoundError: On HTTP 404.
            ReadTheDocsAPIError: On any other status at or above 400.
        """
        resp = self._response_of(response)

        if resp.status_code < _HTTP_BAD_REQUEST:
            return resp

        detail = self._detail_of(response)
        suffix = f": {detail}" if detail else ""

        if resp.status_code == _HTTP_NOT_FOUND:
            msg = f"{context} not found{suffix}"
            raise ReadTheDocsNotFoundError(msg)

        msg = f"{context} failed with HTTP {resp.status_code}{suffix}"
        raise ReadTheDocsAPIError(msg, resp.status_code)

    def _get_json(self, url: str, context: str) -> dict[str, object]:
        """GET a URL and return its JSON object body."""
        response: ApiResponse = self.get(url)
        _ = self._check(response, context)
        return self._json_body(response)

    # -- Projects ------------------------------------------------------------

    def project_list(self) -> list[str]:
        """Return a list of projects.

        This returns the list of projects by their slug name ['slug'],
        not their pretty name ['name']. Since we use these for getting
        details, triggering builds, etc., the pretty name is useless.

        :return: [projects]
        """
        result = self._get_json("projects/?limit=999", "Project list")  # NOQA
        data: object = result.get("results")
        project_list: list[str] = []

        if isinstance(data, list):
            for project in cast(_LIST_OBJECT_TYPE, data):
                if isinstance(project, dict):
                    project_dict = cast(_DICT_STR_OBJECT_TYPE, project)
                    if "slug" in project_dict:
                        slug: object = project_dict["slug"]
                        if isinstance(slug, str):
                            project_list.append(slug)
        return project_list

    def project_details(self, project: str) -> dict[str, object]:
        """Retrieve the details of a specific project.

        :param project: The project's slug
        :return: {result}
        :raises ReadTheDocsNotFoundError: If the project does not exist.
        """
        return self._get_json(
            f"projects/{project}/?expand=active_versions",
            f"Project {project!r}",
        )

    def project_exists(self, project: str) -> bool:
        """Report whether a project exists.

        Prefer this over matching the prose in an error body, which
        varies between API versions.

        :param project: The project's slug
        :return: True when the project exists.
        """
        try:
            _ = self.project_details(project)
        except ReadTheDocsNotFoundError:
            return False
        return True

    def project_version_list(self, project: str) -> list[str]:
        """Retrieve a list of all ACTIVE versions of a project.

        :param project: The project's slug
        :return: [version slugs]
        """
        result = self._get_json(
            f"projects/{project}/versions/?active=True",
            f"Version list for project {project!r}",
        )
        more_results: str | None = None
        versions: list[str] = []

        initial_versions: object = result.get("results")
        if isinstance(initial_versions, list):
            versions.extend(self._version_slugs(initial_versions))

        next_val: object = result.get("next")
        if isinstance(next_val, str):
            more_results = next_val.rsplit("/", 1)[-1]

        while more_results is not None:
            get_more_results = self._get_json(
                f"projects/{project}/versions/" + more_results,
                f"Version list for project {project!r}",
            )
            raw_next: object = get_more_results.get("next")
            more_results = raw_next if isinstance(raw_next, str) else None

            results_data: object = get_more_results.get("results")
            if isinstance(results_data, list):
                versions.extend(self._version_slugs(results_data))

            if more_results is not None:
                more_results = more_results.rsplit("/", 1)[-1]

        return versions

    @staticmethod
    def _version_slugs(data: list[object]) -> list[str]:
        """Extract the ``slug`` field from a list of version objects."""
        slugs: list[str] = []
        for version in data:
            if isinstance(version, dict):
                version_dict = cast(_DICT_STR_OBJECT_TYPE, version)
                slug: object = version_dict.get("slug")
                if isinstance(slug, str):
                    slugs.append(slug)
        return slugs

    def project_version_details(self, project: str, version: str) -> dict[str, object]:
        """Retrieve details of a single version.

        :param project: The project's slug
        :param version: The version's slug. Route branch names through
                        :func:`version_slug` first.
        :return: {result}
        :raises ReadTheDocsNotFoundError: If the version does not exist.
        """
        return self._get_json(
            f"projects/{project}/versions/{version}/",
            f"Version {version!r} of project {project!r}",
        )

    def project_version_update(self, project: str, version: str, active: bool) -> dict[str, object]:
        """Edit version activity.

        :param project: The project slug
        :param version: The version slug
        :param active: Whether the version should be active
        :return: {status payload}
        """
        data: dict[str, bool] = {"active": active}

        json_data: str = json.dumps(data)
        result: ApiResponse = self.patch(f"projects/{project}/versions/{version}/", data=json_data)
        resp = self._check(result, f"Update of version {version!r} for project {project!r}")

        return {
            "status": "success",
            "operation": "project-version-update",
            "project": project,
            "version": version,
            "active": active,
            "status_code": resp.status_code,
        }

    def project_update(self, project: str, updates: Mapping[str, object]) -> dict[str, object]:
        """Update any project details.

        :param project: Project's name (slug).
        :param updates: Any of the JSON keys allowed by the RTD API.
        :return: {status payload}
        :raises ReadTheDocsValidationError: If ``updates`` is empty.
        """
        if not updates:
            msg = f"No fields supplied to update for project {project!r}"
            raise ReadTheDocsValidationError(msg)

        json_data: str = json.dumps(dict(updates))
        result: ApiResponse = self.patch(f"projects/{project}/", data=json_data)
        resp = self._check(result, f"Update of project {project!r}")

        return {
            "status": "success",
            "operation": "project-update",
            "project": project,
            "updated": dict(updates),
            "status_code": resp.status_code,
        }

    def project_create(
        self,
        name: str,
        repository_url: str,
        repository_type: str,
        homepage: str,
        programming_language: str,
        language: str,
    ) -> dict[str, object]:
        """Create a new Read the Docs project.

        :param name: Project name. Any spaces will convert to dashes for the
                        project slug
        :param repository_url:
        :param repository_type: Valid types are git, hg, bzr, and svn
        :param homepage:
        :param programming_language: valid programming language abbreviations
                        are py, java, js, cpp, ruby, php, perl, go, c, csharp,
                        swift, vb, r, objc, css, ts, scala, groovy, coffee,
                        lua, haskell, other, words
        :param language: Most two letter language abbreviations: en, es, etc.
        :return: {result}
        """
        data: dict[str, str | dict[str, str]] = {
            "name": name,
            "repository": {"url": repository_url, "type": repository_type},
            "homepage": homepage,
            "programming_language": programming_language,
            "language": language,
        }

        json_data: str = json.dumps(data)
        result: ApiResponse = self.post("projects/", data=json_data)
        _ = self._check(result, f"Creation of project {name!r}")
        return self._json_body(result)

    # -- Builds --------------------------------------------------------------

    def project_build_list(self, project: str) -> list[dict[str, object]]:
        """Retrieve the project's running build list.

        For future expansion, the statuses are cloning,
        installing, building.

        :param project: The project's slug
        :return: [builds]. An empty list when no builds are running.
        """
        result = self._get_json(
            f"projects/{project}/builds/?running=True",
            f"Build list for project {project!r}",
        )

        builds: list[dict[str, object]] = []
        data: object = result.get("results")
        if isinstance(data, list):
            for build in cast(_LIST_OBJECT_TYPE, data):
                if isinstance(build, dict):
                    builds.append(cast(_DICT_STR_OBJECT_TYPE, build))
        return builds

    def project_build_details(self, project: str, build_id: str) -> dict[str, object]:
        """Retrieve the details of a specific build.

        :param project: The project's slug
        :param build_id: The build id
        :return: {result}
        """
        return self._get_json(
            f"projects/{project}/builds/{build_id}/",
            f"Build {build_id!r} of project {project!r}",
        )

    def project_build_trigger(self, project: str, version: str) -> dict[str, object]:
        """Trigger a project build.

        :param project: The project's slug
        :param version: The version of the project to build
                        (must be an active version). Route branch names
                        through :func:`version_slug` first.
        :return: {result}
        """
        response: ApiResponse = self.post(f"projects/{project}/versions/{version}/builds/")
        _ = self._check(
            response,
            f"Build trigger for version {version!r} of project {project!r}",
        )
        return self._json_body(response)

    # -- Subprojects ---------------------------------------------------------

    def subproject_list(self, project: str) -> list[str]:
        """Return a list of subprojects.

        This returns the list of subprojects by their slug name ['slug'],
        not their pretty name ['name'].

        :param project: The top-level project's slug
        :return: [subprojects]
        """
        result = self._get_json(
            f"projects/{project}/subprojects/?limit=999",  # NOQA
            f"Subproject list for project {project!r}",
        )
        data: object = result.get("results")
        subproject_list: list[str] = []

        if isinstance(data, list):
            for subproject in cast(_LIST_OBJECT_TYPE, data):
                if isinstance(subproject, dict):
                    subproject_dict = cast(_DICT_STR_OBJECT_TYPE, subproject)
                    child: object = subproject_dict.get("child")
                    if isinstance(child, dict):
                        child_dict = cast(_DICT_STR_OBJECT_TYPE, child)
                        slug: object = child_dict.get("slug")
                        if isinstance(slug, str):
                            subproject_list.append(slug)

        return subproject_list

    def subproject_exists(self, project: str, subproject: str) -> bool:
        """Report whether a project/subproject relationship exists.

        :param project: The top-level project's slug
        :param subproject: The subordinated project's slug
        :return: True when the relationship exists.
        """
        return subproject in self.subproject_list(project)

    def subproject_details(self, project: str, subproject: str) -> dict[str, object]:
        """Retrieve the details of a specific subproject.

        :param project: The top-level project's slug
        :param subproject: The subordinated project's slug
        :return: {result}
        """
        return self._get_json(
            f"projects/{project}/subprojects/{subproject}/",
            f"Subproject {subproject!r} of project {project!r}",
        )

    def subproject_create(self, project: str, subproject: str, alias: str | None = None) -> dict[str, object]:
        """Create a subproject.

        Subprojects are actually just top-level projects that
        get subordinated to another project. Create the subproject
        using project_create, then make it a subproject with
        this function.

        :param project: The top-level project's slug
        :param subproject: The other project's slug that is to be subordinated
        :param alias: An alias (not required). (user-defined slug)
        :return: {status payload}
        """
        data: dict[str, str | None] = {"child": subproject, "alias": alias}
        json_data: str = json.dumps(data)
        result: ApiResponse = self.post(f"projects/{project}/subprojects/", data=json_data)
        resp = self._check(
            result,
            f"Creation of subproject {subproject!r} under project {project!r}",
        )

        return {
            "status": "success",
            "operation": "subproject-create",
            "project": project,
            "subproject": subproject,
            "alias": alias,
            "status_code": resp.status_code,
        }

    def subproject_delete(self, project: str, subproject: str) -> dict[str, object]:
        """Delete project/sub relationship.

        :param project: The top-level project's slug
        :param subproject: The subordinated project's slug
        :return: {status payload}
        """
        result: ApiResponse = self.delete(f"projects/{project}/subprojects/{subproject}/")
        resp = self._check(
            result,
            f"Deletion of subproject {subproject!r} from project {project!r}",
        )

        return {
            "status": "success",
            "operation": "subproject-delete",
            "project": project,
            "subproject": subproject,
            "status_code": resp.status_code,
        }
