# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Read the Docs REST API interface."""

from __future__ import annotations

__author__ = "DW Talton"

import json
from typing import cast

import lftools_uv.api.client as client
from lftools_uv import config
from lftools_uv.api.client import ApiResponse


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

    def project_list(self) -> list[str]:
        """Return a list of projects.

        This returns the list of projects by their slug name ['slug'],
        not their pretty name ['name']. Since we use these for getting
        details, triggering builds, etc., the pretty name is useless.

        :param kwargs:
        :return: [projects]
        """
        response: ApiResponse = self.get("projects/?limit=999")  # NOQA
        result: dict[str, object] = self._json_body(response)
        data: object = result["results"]
        project_list: list[str] = []

        if isinstance(data, list):
            for project in cast("list[object]", data):
                if isinstance(project, dict):
                    project_dict = cast("dict[str, object]", project)
                    if "slug" in project_dict:
                        slug: object = project_dict["slug"]
                        if isinstance(slug, str):
                            project_list.append(slug)
        return project_list

    def project_details(self, project: str) -> dict[str, object]:
        """Retrieve the details of a specific project.

        :param project: The project's slug
        :param kwargs:
        :return: {result}
        """
        response: ApiResponse = self.get(f"projects/{project}/?expand=active_versions")
        result: dict[str, object] = self._json_body(response)
        return result

    def project_version_list(self, project: str) -> list[str]:
        """Retrieve a list of all ACTIVE versions of a project.

        :param project: The project's slug
        :return: {result}
        """
        response: ApiResponse = self.get(f"projects/{project}/versions/?active=True")
        result: dict[str, object] = self._json_body(response)
        more_results: str | None = None
        versions: list[str] = []

        # I feel like there must be a better way...but, this works. -DWTalton
        initial_versions: object = result["results"]
        if isinstance(initial_versions, list):
            for version in cast("list[object]", initial_versions):
                if isinstance(version, dict):
                    version_dict = cast("dict[str, object]", version)
                    slug: object = version_dict["slug"]
                    if isinstance(slug, str):
                        versions.append(slug)

        next_val: object = result["next"]
        if isinstance(next_val, str):
            more_results = next_val.rsplit("/", 1)[-1]

        if more_results:
            while more_results is not None:
                next_response: ApiResponse = self.get(f"projects/{project}/versions/" + more_results)
                get_more_results: dict[str, object] = self._json_body(next_response)
                raw_next: object = get_more_results["next"]
                more_results = raw_next if isinstance(raw_next, str) else None

                results_data: object = get_more_results["results"]
                if isinstance(results_data, list):
                    for version in cast("list[object]", results_data):
                        if isinstance(version, dict):
                            version_dict = cast("dict[str, object]", version)
                            slug = version_dict["slug"]
                            if isinstance(slug, str):
                                versions.append(slug)

                if more_results is not None:
                    more_results = more_results.rsplit("/", 1)[-1]

        return versions

    def project_version_details(self, project: str, version: str) -> str:
        """Retrieve details of a single version.

        :param project: The project's slug
        :param version: The version's slug
        :return: {result}
        """
        response: ApiResponse = self.get(f"projects/{project}/versions/{version}/")
        result: dict[str, object] = self._json_body(response)
        return json.dumps(result, indent=2)

    def project_version_update(self, project: str, version: str, active: bool) -> ApiResponse:
        """Edit version activity.

        :param project: The project slug
        :param version: The version slug
        :param active: 'true' or 'false'
        :return: {result}
        """
        data: dict[str, bool] = {"active": active}

        json_data: str = json.dumps(data)
        result: ApiResponse = self.patch(f"projects/{project}/versions/{version}/", data=json_data)
        return result

    def project_update(self, project: str, *args: object) -> tuple[bool, int]:
        """Update any project details.

        :param project: Project's name (slug).
        :param args: Any of the JSON keys allows by RTD API.
        :return: Bool
        """
        data: object = args[0]
        json_data: str = json.dumps(data)
        result: ApiResponse = self.patch(f"projects/{project}/", data=json_data)
        resp = self._response_of(result)

        if resp.status_code == 204:
            return True, resp.status_code
        else:
            return False, resp.status_code

    def project_create(
        self,
        name: str,
        repository_url: str,
        repository_type: str,
        homepage: str,
        programming_language: str,
        language: str,
    ) -> ApiResponse:
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
        :param kwargs:
        :return: {results}
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
        return result

    def project_build_list(self, project: str) -> str:
        """Retrieve the project's running build list.

        For future expansion, the statuses are cloning,
        installing, building.

        :param project: The project's slug
        :param kwargs:
        :return: {result}
        """
        response: ApiResponse = self.get(f"projects/{project}/builds/?running=True")
        result: dict[str, object] = self._json_body(response)

        count: object = result["count"]
        if isinstance(count, int) and count > 0:
            return json.dumps(result, indent=2)
        else:
            return "There are no active builds."

    def project_build_details(self, project: str, build_id: str) -> str:
        """Retrieve the details of a specific build.

        :param project: The project's slug
        :param build_id: The build id
        :param kwargs:
        :return: {result}
        """
        response: ApiResponse = self.get(f"projects/{project}/builds/{build_id}/")
        result: dict[str, object] = self._json_body(response)
        return json.dumps(result, indent=2)

    def project_build_trigger(self, project: str, version: str) -> str:
        """Trigger a project build.

        :param project: The project's slug
        :param version: The version of the project to build
                        (must be an active version)
        :return: {result}
        """
        response: ApiResponse = self.post(f"projects/{project}/versions/{version}/builds/")
        result: dict[str, object] = self._json_body(response)
        return json.dumps(result, indent=2)

    def subproject_list(self, project: str) -> list[str]:
        """Return a list of subprojects.

        This returns the list of subprojects by their slug name ['slug'],
        not their pretty name ['name'].

        :param kwargs:
        :return: [subprojects]
        """
        response: ApiResponse = self.get(f"projects/{project}/subprojects/?limit=999")  # NOQA
        result: dict[str, object] = self._json_body(response)
        data: object = result["results"]
        subproject_list: list[str] = []

        if isinstance(data, list):
            for subproject in cast("list[object]", data):
                if isinstance(subproject, dict):
                    subproject_dict = cast("dict[str, object]", subproject)
                    child: object = subproject_dict.get("child")
                    if isinstance(child, dict):
                        child_dict = cast("dict[str, object]", child)
                        slug: object = child_dict.get("slug")
                        if isinstance(slug, str):
                            subproject_list.append(slug)

        return subproject_list

    def subproject_details(self, project: str, subproject: str) -> dict[str, object]:
        """Retrieve the details of a specific subproject.

        :param project:
        :param subproject:
        :return:
        """
        response: ApiResponse = self.get(f"projects/{project}/subprojects/{subproject}/")
        result: dict[str, object] = self._json_body(response)
        return result

    def subproject_create(self, project: str, subproject: str, alias: str | None = None) -> ApiResponse:
        """Create a subproject.

        Subprojects are actually just top-level projects that
        get subordinated to another project. Create the subproject
        using project_create, then make it a subproject with
        this function.

        :param project: The top-level project's slug
        :param subproject: The other project's slug that is to be subordinated
        :param alias: An alias (not required). (user-defined slug)
        :return:
        """
        data: dict[str, str | None] = {"child": subproject, "alias": alias}
        json_data: str = json.dumps(data)
        result: ApiResponse = self.post(f"projects/{project}/subprojects/", data=json_data)
        return result

    def subproject_delete(self, project: str, subproject: str) -> bool | tuple[bool, int]:
        """Delete project/sub relationship.

        :param project:
        :param subproject:
        :return:
        """
        result: ApiResponse = self.delete(f"projects/{project}/subprojects/{subproject}/")
        resp = self._response_of(result)

        if resp.status_code == 204:
            return True
        else:
            return False, resp.status_code
