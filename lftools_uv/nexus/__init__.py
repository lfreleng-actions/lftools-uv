# -*- code: utf-8 -*-
# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
# vim: sw=4 ts=4 sts=4 et :


"""Library for working with Sonatype Nexus REST API."""

from __future__ import annotations

__author__ = "Andrew Grimberg"
__license__ = "Apache 2.0"
__copyright__ = "Copyright 2017 Andrew Grimberg"

import json
import logging
import os
import sys

import requests
from requests.auth import HTTPBasicAuth

log = logging.getLogger(__name__)


class Nexus:
    """Nexus class to handle communicating with Nexus over a rest api."""

    def __init__(
        self,
        baseurl: str | None = None,
        username: str | None = None,
        password: str | None = None,
    ) -> None:
        """Initialize Nexus instance."""
        if baseurl is None:
            raise ValueError("baseurl is required")
        self.baseurl: str = baseurl
        self.set_full_baseurl()
        if self.baseurl.find("local") < 0:
            self.version: int = 3
        else:
            self.version = 2

        if username and password:
            self.add_credentials(username, password)
        else:
            self.auth: HTTPBasicAuth | None = None

        self.headers: dict[str, str] = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def set_full_baseurl(self) -> None:
        """Find the correct REST API endpoint for this version of Nexus."""
        endpoints = [
            "service/local/repo_targets",
            "service/siesta/rest/beta/read-only",
            "service/rest/beta/read-only",
            "service/rest/v1/read-only",
        ]
        for endpoint in endpoints:
            url = os.path.join(self.baseurl, endpoint)
            response = requests.get(url)
            if response.status_code != 404:
                self.baseurl = os.path.dirname(url)
                return
        raise LookupError("Could not determine Nexus version")

    def add_credentials(self, username: str, password: str) -> None:
        """Create an authentication object to be used."""
        self.auth = HTTPBasicAuth(username, password)

    def add_baseurl(self, url: str) -> None:
        """Set the base URL for nexus."""
        self.baseurl = url

    def get_target(self, name: str) -> str:
        """Get the ID of a given target name."""
        url = os.path.join(self.baseurl, "repo_targets")
        targets = requests.get(url, auth=self.auth, headers=self.headers).json()

        for priv in targets["data"]:
            if priv["name"] == name:
                return str(priv["id"])
        raise LookupError(f"No target found named '{name}'")

    def create_target(self, name: str, patterns: list[str]) -> str:
        """Create a target with the given patterns."""
        url = os.path.join(self.baseurl, "repo_targets")

        target = {
            "data": {
                "contentClass": "any",
                "patterns": patterns,
                "name": name,
            }
        }

        json_data = json.dumps(target).encode(encoding="utf-8")

        r = requests.post(url, auth=self.auth, headers=self.headers, data=json_data)

        if r.status_code != 201:
            raise Exception(f"Target not created for '{name}', code '{r.status_code}'")

        resp = r.json()
        return str(resp["data"]["id"])

    def get_priv(self, name: str, priv: str) -> str:
        """Get the ID for the privilege with the given name and privilege type."""
        search_name = f"{name} - ({priv})"
        return self.get_priv_by_name(search_name)

    def get_priv_by_name(self, name: str) -> str:
        """Get the ID for the privilege with the given name."""
        url = os.path.join(self.baseurl, "privileges")

        privileges = requests.get(url, auth=self.auth, headers=self.headers).json()

        for priv in privileges["data"]:
            if priv["name"] == name:
                return str(priv["id"])

        raise LookupError(f"No privilege found named '{name}'")

    def create_priv(self, name: str, target_id: str, priv: str) -> str:
        """Create a given privilege.

        Privilege must be one of the following:

        create
        read
        delete
        update
        """
        url = os.path.join(self.baseurl, "privileges_target")

        priv_payload = {
            "data": {
                "name": name,
                "description": name,
                "method": [
                    priv,
                ],
                "repositoryGroupId": "",
                "repositoryId": "",
                "repositoryTargetId": target_id,
                "type": "target",
            }
        }

        json_data = json.dumps(priv_payload).encode(encoding="utf-8")
        r = requests.post(url, auth=self.auth, headers=self.headers, data=json_data)
        result = r.json()

        if r.status_code != 201:
            raise Exception(f"Privilege not created for '{name}', code '{r.status_code}'")

        return str(result["data"][0]["id"])

    def get_role(self, name: str) -> str:
        """Get the id of a role with a given name."""
        url = os.path.join(self.baseurl, "roles")
        roles = requests.get(url, auth=self.auth, headers=self.headers).json()

        for role in roles["data"]:
            if role["name"] == name:
                return str(role["id"])

        # If name is not found in names, check ids
        for role in roles["data"]:
            if role["id"] == name:
                return str(role["id"])

        raise LookupError(f"No role with name '{name}'")

    def create_role(
        self,
        name: str,
        privs: list[str],
        role_id: str = "",
        description: str = "",
        roles: list[str] | None = None,
    ) -> str:
        """Create a role with the given privileges."""
        if roles is None:
            roles = []
        url = os.path.join(self.baseurl, "roles")

        role = {
            "data": {
                "id": role_id if role_id else name,
                "name": name,
                "description": description if description else name,
                "privileges": privs,
                "roles": ["repository-any-read"] + roles,
                "sessionTimeout": 60,
            }
        }

        json_data = json.dumps(role).encode(encoding="utf-8")
        log.debug(f"Sending role {json_data.decode('utf-8')} to Nexus")

        r = requests.post(url, auth=self.auth, headers=self.headers, data=json_data)

        if r.status_code != 201:
            resp_err = r.json()
            if r.status_code == 400 and "errors" in resp_err:
                error_msgs: str = ""
                for error in resp_err["errors"]:
                    error_msgs += str(error["msg"]) + "\n"
                raise Exception(
                    f"Role not created for '{name}', code '{r.status_code}', failed "
                    + f"with the following errors: {error_msgs}"
                )
            else:
                raise Exception(f"Role not created for '{role_id}', code '{r.status_code}'")

        resp_ok = r.json()
        return str(resp_ok["data"]["id"])

    def get_user(self, user_id: str) -> None:
        """Determine if a user with a given userId exists."""
        url = os.path.join(self.baseurl, "users")
        users = requests.get(url, auth=self.auth, headers=self.headers).json()

        for user in users["data"]:
            if user["userId"] == user_id:
                return

        raise LookupError(f"No user with id '{user_id}'")

    def create_user(
        self,
        name: str,
        domain: str,
        role_id: str,
        password: str,
        extra_roles: list[str] | None = None,
    ) -> None:
        """Create a Deployment user with a specific role_id and extra roles.

        User is created with the nx-deployment role attached.
        """
        if extra_roles is None:
            extra_roles = []
        url = os.path.join(self.baseurl, "users")

        roles_list: list[str] = [role_id, "nx-deployment"]
        for role in extra_roles:
            roles_list.append(self.get_role(role))

        user_payload = {
            "data": {
                "userId": name,
                "email": f"{name}-deploy@{domain}",
                "firstName": name,
                "lastName": "Deployment",
                "roles": roles_list,
                "password": password,
                "status": "active",
            }
        }

        json_data = json.dumps(user_payload).encode(encoding="utf-8")

        response = requests.post(url, auth=self.auth, headers=self.headers, data=json_data)

        if response.status_code != 201:
            raise Exception(f"User not created for '{name}', code '{response.status_code}'")

    def get_repo_group(self, name: str) -> str:
        """Get the repository ID for a repo group that has a specific name."""
        url = os.path.join(self.baseurl, "repo_groups")

        response = requests.get(url, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        repos = response.json()

        for repo in repos["data"]:
            if repo["name"] == name:
                return str(repo["id"])

        raise LookupError(f"No repository group named '{name}'")

    def get_repo_group_details(self, repoId: str) -> object:
        """Get the current configuration of a given repo group with a specific ID."""
        url = os.path.join(self.baseurl, "repo_groups", repoId)

        response = requests.get(url, auth=self.auth, headers=self.headers)
        response.raise_for_status()
        return response.json()["data"]

    def update_repo_group_details(self, repoId: str, data: object) -> None:
        """Update the given repo group with new configuration."""
        url = os.path.join(self.baseurl, "repo_groups", repoId)

        repo = {"data": data}

        json_data = json.dumps(repo).encode(encoding="utf-8")

        response = requests.put(url, auth=self.auth, headers=self.headers, data=json_data)
        response.raise_for_status()

    def get_all_images(self, repo: str) -> list[object]:
        """Get a list of all images in the given repository."""
        url = f"{self.baseurl}/search?repository={repo}"
        url_attr = requests.get(url)
        if url_attr:
            result = url_attr.json()
            items = result["items"]
            cont_token = result["continuationToken"]
        else:
            log.error(
                "Image listing for repo '%s' failed (HTTP %s)",
                repo,
                url_attr.status_code,
            )
            sys.exit(1)

        # Check if there are multiple pages of data
        while cont_token:
            continue_url = f"{url}&continuationToken={cont_token}"
            url_attr = requests.get(continue_url)
            result = url_attr.json()
            items += result["items"]
            cont_token = result["continuationToken"]

        return list(items)

    def search_images(self, repo: str, pattern: str) -> list[object]:
        """Find all images in the given repository matching the pattern."""
        url = f"{self.baseurl}/search?q={pattern}&repository={repo}"
        url_attr = requests.get(url)
        if url_attr:
            result = url_attr.json()
            items = result["items"]
            cont_token = result["continuationToken"]
        else:
            log.error(
                "Image search for pattern '%s' in repo '%s' failed (HTTP %s)",
                pattern,
                repo,
                url_attr.status_code,
            )
            sys.exit(1)

        # Check if there are multiple pages of data
        while cont_token:
            continue_url = f"{url}&continuationToken={cont_token}"
            url_attr = requests.get(continue_url)
            result = url_attr.json()
            items += result["items"]
            cont_token = result["continuationToken"]

        return list(items)

    def delete_image(self, image: dict[str, object]) -> None:
        """Delete an image from the repo, using the id field."""
        url = os.path.join(self.baseurl, "components", str(image["id"]))
        # Log sanitized message at info level, detailed metadata at debug level
        log.info("Deleting image from Nexus")
        log.debug(f"Image details: {image['name']}:{image['version']}")
        url_attr = requests.delete(url, auth=self.auth)
        if url_attr.status_code != 204:
            log.error(
                "Failed to delete image '%s' (id=%s, version=%s) (HTTP %s)",
                image.get("name", "unknown"),
                image.get("id", "unknown"),
                image.get("version", "unknown"),
                url_attr.status_code,
            )
            sys.exit(1)
