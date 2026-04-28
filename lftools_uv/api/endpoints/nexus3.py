# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Nexus3 REST API interface."""

from __future__ import annotations

__author__ = "DW Talton"

import json
import logging
from typing import cast

import lftools_uv.api.client as client
from lftools_uv import config, helpers
from lftools_uv.api.client import ApiResponse

log: logging.Logger = logging.getLogger(__name__)


class Nexus3(client.RestApi):
    """API endpoint wrapper for Nexus3."""

    def __init__(self, **params: str | dict[str, str]) -> None:
        """Initialize the class."""
        self.params: dict[str, str | dict[str, str]] = params
        fqdn_raw: str | dict[str, str] = self.params["fqdn"]
        if not isinstance(fqdn_raw, str):
            msg: str = "fqdn must be a string"
            raise TypeError(msg)
        self.fqdn: str = fqdn_raw
        if "creds" not in self.params:
            creds: dict[str, str] = {
                "authtype": "basic",
                "username": config.get_setting(self.fqdn, "username"),
                "password": config.get_setting(self.fqdn, "password"),
                "endpoint": config.get_setting(self.fqdn, "endpoint"),
            }
            params["creds"] = creds

        super().__init__(**params)

    # -----------------------------------------------------------------------
    # Helpers
    # -----------------------------------------------------------------------

    @staticmethod
    def _as_dict(obj: object) -> dict[str, object]:
        """Narrow an object to ``dict[str, object]``.

        Returns an empty dict when *obj* is not a dict.
        """
        if isinstance(obj, dict):
            return cast("dict[str, object]", obj)
        return {}

    def _items_from_response(self, response: ApiResponse) -> list[dict[str, object]]:
        """Extract the ``items`` list from a Nexus 3 paged response.

        Nexus 3 wraps paged collection responses in::

            {"items": [ ... ], "continuationToken": ...}

        Returns the inner list of dicts, or an empty list when the
        body cannot be parsed.
        """
        body: dict[str, object] = self._json_body(response)
        items: object = body.get("items", [])
        if isinstance(items, list):
            return [cast("dict[str, object]", item) for item in cast("list[object]", items) if isinstance(item, dict)]
        return []

    # -----------------------------------------------------------------------
    # Roles
    # -----------------------------------------------------------------------

    def create_role(self, name: str, description: str, privileges: str, roles: str) -> str:
        """Create a new role.

        :param name: the role name
        :param description: the role description
        :param privileges: privileges assigned to this role
        :param roles: other roles attached to this role
        """
        list_of_privileges: list[str] = privileges.split(",")
        list_of_roles: list[str] = roles.split(",")

        data: dict[str, object] = {
            "id": name,
            "name": name,
            "description": description,
            "privileges": list_of_privileges,
            "roles": list_of_roles,
        }

        json_data: str = json.dumps(data, indent=4)
        response: ApiResponse = self.post("service/rest/beta/security/roles", data=json_data)
        resp = self._response_of(response)

        if resp.status_code == 200:
            return f"Role {name} created"
        resp.raise_for_status()
        return "Failed to create role"

    # -----------------------------------------------------------------------
    # Scripts
    # -----------------------------------------------------------------------

    def create_script(self, name: str, content: str) -> str:
        """Create a new script.

        :param name: script name
        :param content: content of the script (groovy code)
        """
        data: dict[str, str] = {
            "name": name,
            "content": content,
            "type": "groovy",
        }

        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/rest/v1/script", data=json_data)
        resp = self._response_of(response)

        if resp.status_code == 204:
            return f"Script {name} successfully added."
        resp.raise_for_status()
        return f"Failed to create script {name}"

    def delete_script(self, name: str) -> str:
        """Delete a script from the server.

        :param name: the script name
        """
        response: ApiResponse = self.delete(f"service/rest/v1/script/{name}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return f"Successfully deleted {name}"
        resp.raise_for_status()
        return f"Failed to delete script {name}"

    def read_script(self, name: str) -> dict[str, object] | str:
        """Get the contents of a script.

        :param name: the script name
        """
        response: ApiResponse = self.get(f"service/rest/v1/script/{name}")
        resp = self._response_of(response)

        if resp.status_code == 200:
            if isinstance(response, tuple):
                body: client.ApiBody = response[1]
                if isinstance(body, dict):
                    return body
            return cast("dict[str, object]", resp.json())
        resp.raise_for_status()
        return f"Failed to read script {name}"

    def run_script(self, name: str) -> dict[str, object] | str:
        """Run a script on the server.

        :param name: the script name
        """
        response: ApiResponse = self.post(f"service/rest/v1/script/{name}/run")
        resp = self._response_of(response)

        if resp.status_code == 200:
            if isinstance(response, tuple):
                body: client.ApiBody = response[1]
                if isinstance(body, dict):
                    return body
            return cast("dict[str, object]", resp.json())
        resp.raise_for_status()
        return f"Failed to execute script {name}"

    def update_script(self, name: str, content: str) -> str:
        """Update an existing script on the server.

        :param name: script name
        :param content: new content for the script (groovy code)
        """
        data: dict[str, str] = {
            "name": name,
            "content": content,
            "type": "groovy",
        }

        json_data: str = json.dumps(data)
        response: ApiResponse = self.put(f"service/rest/v1/script/{name}", data=json_data)
        resp = self._response_of(response)

        if resp.status_code == 204:
            return f"Successfully updated {name}"
        resp.raise_for_status()
        return f"Failed to update script {name}"

    def list_scripts(self) -> list[str]:
        """List server scripts."""
        response: ApiResponse = self.get("service/rest/v1/script")
        result: list[object] = self._list_body(response)
        list_of_scripts: list[str] = []
        for raw_script in result:
            script: dict[str, object] = self._as_dict(raw_script)
            if script:
                list_of_scripts.append(str(script.get("name", "")))
        return list_of_scripts

    # -----------------------------------------------------------------------
    # Tags
    # -----------------------------------------------------------------------

    def create_tag(self, name: str, attributes: str | None) -> str:
        """Create a new tag.

        :param name: the tag name
        :param attributes: the tag's attributes
        """
        data: dict[str, object] = {
            "name": name,
        }

        if attributes is not None:
            data["attributes"] = attributes

        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/rest/v1/tags", data=json_data)
        resp = self._response_of(response)

        if resp.status_code == 200:
            return f"Tag {name} successfully added."
        resp.raise_for_status()
        return f"Failed to create tag {name}"

    def delete_tag(self, name: str) -> str:
        """Delete a tag from the server.

        :param name: the tag's name
        """
        response: ApiResponse = self.delete(f"service/rest/v1/tags/{name}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return f"Tag {name} successfully deleted."
        resp.raise_for_status()
        return f"Failed to delete tag {name}."

    def show_tag(self, name: str) -> dict[str, object]:
        """Get tag details.

        :param name: tag name
        """
        response: ApiResponse = self.get(f"service/rest/v1/tags/{name}")
        if isinstance(response, tuple):
            body: client.ApiBody = response[1]
            if isinstance(body, dict):
                return body
        return {}

    def list_tags(self) -> list[str] | str:
        """List all tags."""
        response: ApiResponse = self.get("service/rest/v1/tags")
        if not isinstance(response, tuple):
            response.raise_for_status()
            return "There are no tags"

        body: dict[str, object] = self._json_body(response)
        list_of_tags: list[str] = []
        token: object = body.get("continuationToken")

        if token is not None:
            result: dict[str, object] = body
            while token is not None:
                items: object = result.get("items", [])
                if isinstance(items, list):
                    for raw_tag in cast("list[object]", items):
                        tag: dict[str, object] = self._as_dict(raw_tag)
                        if tag:
                            list_of_tags.append(str(tag.get("name", "")))
                cont_token: object = result.get("continuationToken")
                next_response: ApiResponse = self.get(f"service/rest/v1/tags?continuationToken={str(cont_token)}")
                if isinstance(next_response, tuple):
                    result = self._json_body(next_response)
                    token = result.get("continuationToken")
                else:
                    break
        else:
            items_obj: object = body.get("items", [])
            if isinstance(items_obj, list):
                for raw_tag in cast("list[object]", items_obj):
                    tag_dict: dict[str, object] = self._as_dict(raw_tag)
                    if tag_dict:
                        list_of_tags.append(str(tag_dict.get("name", "")))

        if list_of_tags:
            return list_of_tags
        return "There are no tags"

    # -----------------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------------

    def create_user(
        self,
        username: str,
        first_name: str,
        last_name: str,
        email_address: str,
        roles: str,
        password: str | None = None,
    ) -> str | None:
        """Create a new user.

        @param username:
        @param first_name:
        @param last_name:
        @param email_address:
        @param roles:
        @param password:
        """
        list_of_roles: list[str] = roles.split(",")
        data: dict[str, object] = {
            "userId": username,
            "firstName": first_name,
            "lastName": last_name,
            "emailAddress": email_address,
            "status": "active",
            "roles": list_of_roles,
        }

        if password:
            data["password"] = password
        else:
            data["password"] = helpers.generate_password()

        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/rest/beta/security/users", data=json_data)
        resp = self._response_of(response)

        if resp.status_code == 200:
            return "User {} successfully created with password {}".format(username, data["password"])
        resp.raise_for_status()
        log.error("Failed to create user %s", username)
        return None

    def delete_user(self, username: str) -> str:
        """Delete a user.

        @param username:
        """
        response: ApiResponse = self.delete(f"service/rest/beta/security/users/{username}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return f"Successfully deleted user {username}"
        if isinstance(response, tuple):
            return f"Failed to delete user {username} with error: {response[1]}"
        resp.raise_for_status()
        return f"Failed to delete user {username}"

    def list_user(self, username: str) -> list[list[object]]:
        """Show user details.

        :param username: the user's username
        """
        response: ApiResponse = self.get(f"service/rest/beta/security/users?userId={username}")
        result: list[object] = self._list_body(response)
        user_info: list[list[object]] = []
        for raw_user in result:
            user: dict[str, object] = self._as_dict(raw_user)
            if user:
                user_info.append(
                    [
                        user.get("userId", ""),
                        user.get("firstName", ""),
                        user.get("lastName", ""),
                        user.get("emailAddress", ""),
                        user.get("status", ""),
                        user.get("roles", []),
                    ]
                )
        return user_info

    def list_users(self) -> list[list[object]]:
        """List all users."""
        response: ApiResponse = self.get("service/rest/beta/security/users")
        result: list[object] = self._list_body(response)
        list_of_users: list[list[object]] = []
        for raw_user in result:
            user: dict[str, object] = self._as_dict(raw_user)
            if user:
                list_of_users.append(
                    [
                        user.get("userId", ""),
                        user.get("firstName", ""),
                        user.get("lastName", ""),
                        user.get("emailAddress", ""),
                        user.get("status", ""),
                        user.get("roles", []),
                    ]
                )
        return list_of_users

    # -----------------------------------------------------------------------
    # Assets & Components
    # -----------------------------------------------------------------------

    def list_assets(self, repository: str) -> list[str] | str:
        """List the assets of a given repo.

        :param repository: repo name
        """
        response: ApiResponse = self.get(f"service/rest/v1/assets?repository={repository}")
        items: list[dict[str, object]] = self._items_from_response(response)
        if not items:
            return "This repository has no assets"

        item_list: list[str] = []
        for item in items:
            item_list.append(str(item.get("path", "")))
        return item_list

    def list_components(self, repository: str) -> list[dict[str, object]] | str:
        """List components from a repo.

        :param repository: the repo name
        """
        response: ApiResponse = self.get(f"service/rest/v1/components?repository={repository}")
        items: list[dict[str, object]] = self._items_from_response(response)
        if not items:
            return "This repository has no components"
        return items

    def search_asset(self, query: str, repository: str, details: bool = False) -> list[str] | str:
        """Search for an asset.

        :param query: querystring to use, eg myjar-1 to find myjar-1.2.3.jar
        :param repository: the repo to search in
        :param details: returns a fully-detailed json dump
        """
        data: dict[str, str] = {
            "q": query,
            "repository": repository,
        }
        json_data: str = json.dumps(data)
        response: ApiResponse = self.get(
            f"service/rest/v1/search/assets?q={query}&repository={repository}",
            data=json_data,
        )

        items: list[dict[str, object]] = self._items_from_response(response)

        if details:
            return json.dumps(items, indent=4)

        list_of_assets: list[str] = []
        for item in items:
            list_of_assets.append(str(item.get("path", "")))
        return list_of_assets

    # -----------------------------------------------------------------------
    # Blob stores
    # -----------------------------------------------------------------------

    def list_blobstores(self) -> list[str]:
        """List server blobstores."""
        response: ApiResponse = self.get("service/rest/beta/blobstores")
        result: list[object] = self._list_body(response)
        list_of_blobstores: list[str] = []
        for raw_blob in result:
            blob: dict[str, object] = self._as_dict(raw_blob)
            if blob:
                list_of_blobstores.append(str(blob.get("name", "")))
        return list_of_blobstores

    # -----------------------------------------------------------------------
    # Privileges
    # -----------------------------------------------------------------------

    def list_privileges(self) -> list[list[object]]:
        """List server-configured privileges."""
        response: ApiResponse = self.get("service/rest/beta/security/privileges")
        result: list[object] = self._list_body(response)
        list_of_privileges: list[list[object]] = []
        for raw_priv in result:
            priv: dict[str, object] = self._as_dict(raw_priv)
            if priv:
                list_of_privileges.append(
                    [
                        priv.get("type", ""),
                        priv.get("name", ""),
                        priv.get("description", ""),
                        priv.get("readOnly", False),
                    ]
                )
        return list_of_privileges

    # -----------------------------------------------------------------------
    # Repositories
    # -----------------------------------------------------------------------

    def list_repositories(self) -> list[str]:
        """List server repositories."""
        response: ApiResponse = self.get("service/rest/v1/repositories")
        result: list[object] = self._list_body(response)
        list_of_repositories: list[str] = []
        for raw_repo in result:
            repo: dict[str, object] = self._as_dict(raw_repo)
            if repo:
                list_of_repositories.append(str(repo.get("name", "")))
        return list_of_repositories

    # -----------------------------------------------------------------------
    # Roles (list)
    # -----------------------------------------------------------------------

    def list_roles(self) -> list[list[str]]:
        """List server roles."""
        response: ApiResponse = self.get("service/rest/beta/security/roles")
        result: list[object] = self._list_body(response)
        list_of_roles: list[list[str]] = []
        for raw_role in result:
            role: dict[str, object] = self._as_dict(raw_role)
            if role:
                list_of_roles.append([str(role.get("name", ""))])
        return list_of_roles

    # -----------------------------------------------------------------------
    # Tasks
    # -----------------------------------------------------------------------

    def list_tasks(self) -> list[list[object]]:
        """List all tasks."""
        response: ApiResponse = self.get("service/rest/v1/tasks")
        items: list[dict[str, object]] = self._items_from_response(response)
        list_of_tasks: list[list[object]] = []
        for task in items:
            list_of_tasks.append(
                [
                    task.get("name", ""),
                    task.get("message", ""),
                    task.get("currentState", ""),
                    task.get("lastRunResult", ""),
                ]
            )
        return list_of_tasks

    # -----------------------------------------------------------------------
    # Staging
    # -----------------------------------------------------------------------

    def staging_promotion(self, destination_repo: str, tag: str) -> ApiResponse:
        """Promote repo assets to a new location.

        :param destination_repo: the repo to promote into
        :param tag: the tag used to identify the assets
        """
        data: dict[str, str] = {"tag": tag}
        json_data: str = json.dumps(data)
        response: ApiResponse = self.post(
            f"service/rest/v1/staging/move/{destination_repo}",
            data=json_data,
        )
        return response
