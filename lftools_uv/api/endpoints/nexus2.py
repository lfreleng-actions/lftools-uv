# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Nexus2 REST API interface."""

from __future__ import annotations

__author__ = "DW Talton"

import json
import logging
import sys
from typing import cast

import lftools_uv.api.client as client
from lftools_uv import config
from lftools_uv.api.client import ApiResponse

log: logging.Logger = logging.getLogger(__name__)


class Nexus2(client.RestApi):
    """API endpoint wrapper for Nexus2."""

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

    @staticmethod
    def _data_items(response: ApiResponse) -> list[dict[str, object]]:
        """Extract the ``data`` list from a Nexus 2 JSON envelope.

        Nexus 2 wraps most collection responses in::

            {"data": [ ... ]}

        Returns the inner list of dicts, or an empty list when the
        body cannot be parsed.
        """
        if not isinstance(response, tuple):
            response.raise_for_status()
            return []
        body: client.ApiBody = response[1]
        if isinstance(body, dict):
            data: object = body.get("data", [])
            if isinstance(data, list):
                typed_data: list[object] = cast("list[object]", data)
                return [cast("dict[str, object]", item) for item in typed_data if isinstance(item, dict)]
        return []

    # -----------------------------------------------------------------------
    # Privileges
    # -----------------------------------------------------------------------

    def privilege_list(self) -> list[list[object]]:
        """List privileges."""
        response: ApiResponse = self.get("service/local/privileges")
        result: list[dict[str, object]] = self._data_items(response)

        privilege_list: list[list[object]] = []
        for privilege in result:
            privilege_list.append([privilege["name"], privilege["id"]])

        privilege_list.sort()
        return privilege_list

    def privilege_create(self, name: str, description: str, repo: str) -> str:
        """Create a new privilege.

        :param name: the privilege name
        :param description: the privilege description
        :param repo: the repo to attach to the privilege
        """
        data: dict[str, dict[str, object]] = {
            "data": {
                "name": name,
                "description": description,
                "type": "target",
                "repositoryTargetId": "any",
                "repositoryId": repo,
                "repositoryGroupId": "",
                "method": ["create", "read", "update", "delete"],
            }
        }

        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/local/privileges_target", data=json_data)

        if isinstance(response, tuple):
            if response[0].status_code == 201:
                return "Privilege successfully created."
        else:
            response.raise_for_status()
        return "Failed to create privilege."

    def privilege_delete(self, privilege_id: str) -> str:
        """Delete a privilege.

        :param privilege_id: the ID of the privilege (from privilege list)
        """
        response: ApiResponse = self.delete(f"service/local/privileges/{privilege_id}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return "Privilege successfully deleted."
        return f"Failed to delete privilege {privilege_id}."

    # -----------------------------------------------------------------------
    # Repositories
    # -----------------------------------------------------------------------

    def repo_list(self) -> list[list[object]]:
        """Get a list of repositories."""
        response: ApiResponse = self.get("service/local/repositories")
        result: list[dict[str, object]] = self._data_items(response)

        repo_list: list[list[object]] = []
        for repo in result:
            repo_list.append(
                [
                    repo["name"],
                    repo["repoType"],
                    repo["provider"],
                    repo["id"],
                ]
            )

        return repo_list

    def repo_create(
        self,
        repo_type: str,
        repo_id: str,
        repo_name: str,
        repo_provider: str,
        repo_policy: str,
        repo_upstream_url: str,
    ) -> str:
        """Add a new repo.

        :param repo_type: the type of repo ('proxy' or 'hosted')
        :param repo_id: the ID for the repository
        :param repo_name: the name for the repository
        :param repo_provider: the provider type ('maven2' or 'site')
        :param repo_policy: repo policy ('RELEASE', 'SNAPSHOT', 'MIXED')
        :param repo_upstream_url: URL to upstream repo (proxy only)
        """
        inner: dict[str, object] = {
            "browsable": True,
            "exposed": True,
            "id": repo_id,
            "indexable": True,
            "name": repo_name,
            "notFoundCacheTTL": 1440,
            "provider": repo_provider,
            "providerRole": "org.sonatype.nexus.proxy.repository.Repository",
            "repoPolicy": repo_policy,
            "repoType": repo_type,
        }

        if repo_type == "hosted":
            inner.update(
                {
                    "checksumPolicy": "IGNORE",
                    "downloadRemoteIndexes": False,
                    "writePolicy": "ALLOW_WRITE_ONCE",
                }
            )
            if repo_provider == "site":
                inner.update(
                    {
                        "repoPolicy": "MIXED",
                        "writePolicy": "ALLOW_WRITE",
                        "indexable": False,
                    }
                )

        if repo_type == "proxy":
            inner.update(
                {
                    "artifactMaxAge": -1,
                    "autoBlockActive": True,
                    "checksumPolicy": "WARN",
                    "downloadRemoteIndexes": True,
                    "fileTypeValidation": True,
                    "metadataMaxAge": 1440,
                    "remoteStorage": {
                        "authentication": None,
                        "connectionSettings": None,
                        "remoteStorageUrl": repo_upstream_url,
                    },
                }
            )

        data: dict[str, dict[str, object]] = {"data": inner}
        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/local/repositories", data=json_data)

        if isinstance(response, tuple):
            if response[0].status_code == 201:
                return "Repo successfully created."
            return "Failed to create new repository"
        response.raise_for_status()
        return "Failed to create new repository"

    def repo_delete(self, repo_id: str) -> str:
        """Permanently delete a repo.

        :param repo_id: the ID of the repo from repo list.
        """
        response: ApiResponse = self.delete(f"service/local/repositories/{repo_id}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return "Repo successfully deleted."
        log.error("Failed to delete repository %s", repo_id)
        sys.exit(1)

    # -----------------------------------------------------------------------
    # Roles
    # -----------------------------------------------------------------------

    def role_list(self) -> list[list[object]]:
        """List all roles."""
        response: ApiResponse = self.get("service/local/roles")
        if not isinstance(response, tuple):
            response.raise_for_status()
            return []

        body: client.ApiBody = response[1]
        if not isinstance(body, dict):
            return []

        data_val: object = body.get("data", [])
        if not isinstance(data_val, list):
            return []

        typed_data: list[object] = cast("list[object]", data_val)
        role_list: list[list[object]] = []
        for raw_role in typed_data:
            role: dict[str, object] = self._as_dict(raw_role)
            if not role:
                continue
            # Build multiline strings for tabulate display
            roles_string: str = ""
            privs_string: str = ""
            roles_obj: object = role.get("roles")
            if isinstance(roles_obj, list):
                for r in cast("list[object]", roles_obj):
                    roles_string += str(r) + "\n"

            privs_obj: object = role.get("privileges")
            if isinstance(privs_obj, list):
                for p in cast("list[object]", privs_obj):
                    privs_string += str(p) + "\n"

            role_list.append([role["id"], role["name"], roles_string, privs_string])

        return role_list

    def role_create(
        self,
        role_id: str,
        role_name: str,
        role_description: str,
        roles_list: str | None = None,
        privs_list: str | None = None,
    ) -> str | ApiResponse:
        """Create a new role.

        :param role_id: the ID name of the role (string)
        :param role_name: the actual name of the role
        :param role_description: the description of the role
        :param roles_list: comma-separated existing roles to attach
        :param privs_list: comma-separated existing privs to attach
        """
        inner: dict[str, object] = {
            "id": role_id,
            "name": role_name,
            "description": role_description,
            "sessionTimeout": 0,
            "userManaged": True,
        }

        if roles_list:
            inner["roles"] = roles_list.split(",")

        if privs_list:
            inner["privileges"] = privs_list.split(",")

        data: dict[str, dict[str, object]] = {"data": inner}
        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/local/roles", data=json_data)

        if isinstance(response, tuple):
            if response[0].status_code == 201:
                return "Role successfully created."
            return response
        response.raise_for_status()
        return "Failed to create role."

    def role_delete(self, role_id: str) -> str:
        """Permanently delete a role.

        :param role_id: The ID of the role to delete (from role list)
        """
        response: ApiResponse = self.delete(f"service/local/roles/{role_id}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return "Role successfully deleted."
        return f"Failed to delete role {role_id}."

    # -----------------------------------------------------------------------
    # Users
    # -----------------------------------------------------------------------

    def user_list(self) -> list[list[object]]:
        """List all users."""
        response: ApiResponse = self.get("service/local/plexus_users/allConfigured")
        result: list[dict[str, object]] = self._data_items(response)

        user_list: list[list[object]] = []
        for user in result:
            role_list: list[list[object]] = []
            roles_obj: object = user.get("roles", [])
            if isinstance(roles_obj, list):
                for raw_role in cast("list[object]", roles_obj):
                    role: dict[str, object] = self._as_dict(raw_role)
                    if role:
                        role_list.append([role["roleId"]])

            user_list.append(
                [
                    user.get("userId", "N/A"),
                    user.get("firstName", "N/A"),
                    user.get("lastName", "N/A"),
                    user.get("status", "N/A"),
                    role_list,
                ]
            )

        return user_list

    def user_create(
        self,
        username: str,
        firstname: str,
        lastname: str,
        email: str,
        roles: str,
        password: str | None = None,
    ) -> str:
        """Add a new user.

        :param username: the username
        :param firstname: the user's first name
        :param lastname: the user's last name
        :param email: the user's email address
        :param roles: a comma-separated list of roles to add the user to
        :param password: optional password
        """
        role_list: list[str] = roles.split(",")
        inner: dict[str, object] = {
            "userId": username,
            "firstName": firstname,
            "lastName": lastname,
            "status": "active",
            "email": email,
            "roles": role_list,
        }

        if password:
            inner["password"] = password

        data: dict[str, dict[str, object]] = {"data": inner}
        json_data: str = json.dumps(data)
        response: ApiResponse = self.post("service/local/users", data=json_data)

        if isinstance(response, tuple):
            if response[0].status_code == 201:
                return "User successfully created."
            return "Failed to create new user"
        response.raise_for_status()
        return "Failed to create new user"

    def user_delete(self, username: str) -> str:
        """Permanently delete a user.

        :param username: The username to delete (from user list)
        """
        response: ApiResponse = self.delete(f"service/local/users/{username}")
        resp = self._response_of(response)

        if resp.status_code == 204:
            return "User successfully deleted."
        return f"Failed to delete user {username}."
