# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Gerrit REST API interface."""

from __future__ import annotations

import json
import logging
import os
import time
from typing import cast
from urllib.parse import quote

import requests

import lftools_uv.api.client as client
from lftools_uv import config
from lftools_uv.api.client import ApiResponse

log: logging.Logger = logging.getLogger(__name__)


class Gerrit(client.RestApi):
    """API endpoint wrapper for Gerrit.

    Be sure to always include the trailing "/" when adding
    new methods.
    """

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
    def _str_val(obj: object) -> str:
        """Coerce an object value to str safely."""
        if isinstance(obj, str):
            return obj
        return str(obj) if obj is not None else ""

    # -----------------------------------------------------------------------
    # Changes
    # -----------------------------------------------------------------------

    def create_change(
        self,
        filename: str,
        gerrit_project: str,
        issue_id: str,
        signed_off_by: str,
    ) -> str:
        """Method to create a gerrit change."""
        if issue_id:
            subject: str = f"Automation adds {filename}\n\nIssue-ID: {issue_id}\n\nSigned-off-by: {signed_off_by}"
        else:
            subject = f"Automation adds {filename}\n\nSigned-off-by: {signed_off_by}"
        payload: str = json.dumps(
            {
                "project": f"{gerrit_project}",
                "subject": f"{subject}",
                "branch": "master",
            }
        )
        return payload

    def add_file(
        self,
        fqdn: str,
        gerrit_project: str,
        filename: str,
        issue_id: str,
        file_location: str,
    ) -> ApiResponse:
        """Add a file for review to a Project.

        File can be sourced from any location
        but only lands in the root of the repo.
        unless file_location is specified
        Example:

        gerrit_url gerrit.o-ran-sc.org
        gerrit_project test/test1
        filename /tmp/INFO.yaml
        file_location="somedir/example-INFO.yaml"
        """
        signed_off_by: str = config.get_setting(fqdn, "sob")
        basename: str = os.path.basename(filename)
        payload: str = self.create_change(basename, gerrit_project, issue_id, signed_off_by)

        if file_location:
            file_location = quote(file_location, safe="", encoding=None, errors=None)
            basename = file_location
        log.info(payload)

        access_str: str = "changes/"
        response: ApiResponse = self.post(access_str, data=payload)
        result: dict[str, object] = self._json_body(response)
        log.info(result.get("id"))
        changeid: str = self._str_val(result.get("id"))

        with open(filename) as my_file:  # noqa: PTH123
            file_content: str = my_file.read()
        my_file_size: os.stat_result = os.stat(filename)
        headers: dict[str, str] = {
            "Content-Type": "text/plain",
            "Content-length": f"{my_file_size}",
        }
        self.r.headers.update(headers)
        access_str = f"changes/{changeid}/edit/{basename}"
        edit_result: ApiResponse = self.put(access_str, data=file_content)
        log.info(edit_result)

        access_str = f"changes/{changeid}/edit:publish"
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        self.r.headers.update(headers)
        publish_payload: str = json.dumps(
            {
                "notify": "NONE",
            }
        )
        publish_result: ApiResponse = self.post(access_str, data=publish_payload)
        return publish_result

    def add_info_job(
        self,
        fqdn: str,
        gerrit_project: str,
        jjbrepo: str,
        reviewid: str,
        issue_id: str,
    ) -> ApiResponse:
        """Add an INFO job for a new Project.

        Adds info verify jenkins job for project.
        result['id'] can be used to amend a review
        so that multiple projects can have info jobs added
        in a single review

        Example:

        fqdn gerrit.o-ran-sc.org
        gerrit_project test/test1
        jjbrepo ci-mangement
        """
        ###############################################################
        # Setup
        signed_off_by: str = config.get_setting(fqdn, "sob")
        gerrit_project_dashed: str = gerrit_project.replace("/", "-")
        filename: str = f"{gerrit_project_dashed}.yaml"
        changeid: str

        if not reviewid:
            payload: str = self.create_change(filename, jjbrepo, issue_id, signed_off_by)
            log.info(payload)
            access_str: str = "changes/"
            response: ApiResponse = self.post(access_str, data=payload)
            result: dict[str, object] = self._json_body(response)
            log.info(result)
            log.info(result.get("id"))
            changeid = self._str_val(result.get("id"))
        else:
            changeid = reviewid

        buildnode: str
        if fqdn == "gerrit.o-ran-sc.org":
            buildnode = "centos7-builder-1c-1g"
        elif fqdn == "gerrit.onap.org":
            buildnode = "centos8-builder-2c-1g"
        else:
            buildnode = "centos7-builder-2c-1g"

        my_inline_file: str = f"""---
- project:
    name: {gerrit_project_dashed}-project-view
    project-name: {gerrit_project_dashed}
    views:
      - project-view\n
- project:
    name: {gerrit_project_dashed}-info
    project: {gerrit_project}
    project-name: {gerrit_project_dashed}
    build-node: {buildnode}
    jobs:
      - gerrit-info-yaml-verify\n"""
        my_inline_file_size: int = len(my_inline_file.encode("utf-8"))
        headers: dict[str, str] = {
            "Content-Type": "text/plain",
            "Content-length": f"{my_inline_file_size}",
        }
        self.r.headers.update(headers)
        access_str = f"changes/{changeid}/edit/jjb%2F{gerrit_project_dashed}%2F{gerrit_project_dashed}.yaml"
        inline_payload: str = my_inline_file
        log.info(access_str)
        edit_result: ApiResponse = self.put(access_str, data=inline_payload)
        log.info(edit_result)

        access_str = f"changes/{changeid}/edit:publish"
        headers = {"Content-Type": "application/json; charset=UTF-8"}
        self.r.headers.update(headers)
        publish_payload: str = json.dumps(
            {
                "notify": "NONE",
            }
        )
        publish_result: ApiResponse = self.post(access_str, data=publish_payload)
        log.info(publish_result)
        return publish_result

    def vote_on_change(
        self,
        fqdn: str,
        gerrit_project: str,
        changeid: str,
    ) -> ApiResponse:
        """Help that votes on a change.

        POST /changes/{change-id}/revisions/{revision-id}/review
        """
        log.info(
            "Voting on change: fqdn=%s, project=%s, changeid=%s",
            fqdn,
            gerrit_project,
            changeid,
        )
        access_str: str = f"changes/{changeid}/revisions/2/review"
        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=UTF-8",
        }
        self.r.headers.update(headers)
        payload: str = json.dumps(
            {
                "tag": "automation",
                "message": "Vote on file",
                "labels": {
                    "Verified": +1,
                    "Code-Review": +2,
                },
            }
        )

        result: ApiResponse = self.post(access_str, data=payload)
        # Code for projects that don't allow self merge.
        if config.get_setting(self.fqdn + ".second"):
            second_username: str = config.get_setting(self.fqdn + ".second", "username")
            second_password: str = config.get_setting(self.fqdn + ".second", "password")
            self.r.auth = (second_username, second_password)
            result = self.post(access_str, data=payload)
            self.r.auth = (self.username, self.password)
        return result

    def submit_change(
        self,
        _fqdn: str,
        _gerrit_project: str,
        changeid: str,
        payload: str,
    ) -> ApiResponse:
        """Submit a change."""
        # submit a change id
        access_str: str = f"changes/{changeid}/submit"
        log.info(access_str)
        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=UTF-8",
        }
        self.r.headers.update(headers)
        result: ApiResponse = self.post(access_str, data=payload)
        return result

    def abandon_changes(self, _fqdn: str, gerrit_project: str) -> dict[str, object] | None:
        """Abandon open changes for a project."""
        gerrit_project_encoded: str = quote(gerrit_project, safe="", encoding=None, errors=None)
        access_str: str = f"changes/?q=project:{gerrit_project_encoded}"
        log.info(access_str)
        headers: dict[str, str] = {
            "Content-Type": "application/json; charset=UTF-8",
        }
        self.r.headers.update(headers)
        response: ApiResponse = self.get(access_str)
        changes: list[object] = self._list_body(response)
        abandon_payload: str = json.dumps({"message": "Abandoned by automation"})
        for raw_change in changes:
            change: dict[str, object] = self._as_dict(raw_change)
            if not change:
                continue
            if self._str_val(change.get("status")) == "NEW":
                change_id: str = self._str_val(change.get("id"))
                access_str = f"changes/{change_id}/abandon"
                log.info(access_str)
                abandon_response: ApiResponse = self.post(access_str, data=abandon_payload)
                return self._json_body(abandon_response)
        return None

    # -----------------------------------------------------------------------
    # Sanity & review helpers
    # -----------------------------------------------------------------------

    def sanity_check(self, _fqdn: str, gerrit_project: str) -> dict[str, object]:
        """Perform a sanity check."""
        gerrit_project_encoded: str = quote(gerrit_project, safe="", encoding=None, errors=None)
        mylist: list[str] = [
            "projects/",
            f"projects/{gerrit_project_encoded}",
        ]
        result: dict[str, object] = {}
        for access_str in mylist:
            log.info(access_str)
            try:
                response: ApiResponse = self.get(access_str)
                result = self._json_body(response)
            except Exception:
                log.info("Not found %s", access_str)
                exit(1)
            log.info("found %s %s", access_str, mylist)
        return result

    def add_git_review(
        self,
        fqdn: str,
        gerrit_project: str,
        issue_id: str,
    ) -> None:
        """Add and Submit a .gitreview for a project.

        Example:

        fqdn gerrit.o-ran-sc.org
        gerrit_project test/test1
        issue_id: CIMAN-33
        """
        signed_off_by: str = config.get_setting(fqdn, "sob")
        _ = self.sanity_check(fqdn, gerrit_project)

        ###############################################################
        # Create A change set.
        filename: str = ".gitreview"
        payload: str = self.create_change(filename, gerrit_project, issue_id, signed_off_by)
        log.info(payload)

        access_str: str = "changes/"
        response: ApiResponse = self.post(access_str, data=payload)
        result: dict[str, object] = self._json_body(response)
        log.info(result)
        changeid: str = self._str_val(result.get("id"))

        ###############################################################
        # Add a file to a change set.
        my_inline_file: str = f"""
        [gerrit]
        host={fqdn}
        port=29418
        project={gerrit_project}
        defaultbranch=master
        """
        my_inline_file_size: int = len(my_inline_file.encode("utf-8"))
        headers: dict[str, str] = {
            "Content-Type": "text/plain",
            "Content-length": f"{my_inline_file_size}",
        }
        self.r.headers.update(headers)
        access_str = f"changes/{changeid}/edit/{filename}"
        edit_result: ApiResponse = self.put(access_str, data=my_inline_file)
        resp: requests.Response = self._response_of(edit_result)

        if resp.status_code == 409:
            log.info(edit_result)
            log.info("Conflict detected exiting")
            exit(0)

        else:
            access_str = f"changes/{changeid}/edit:publish"
            headers = {"Content-Type": "application/json; charset=UTF-8"}
            self.r.headers.update(headers)
            publish_payload: str = json.dumps(
                {
                    "notify": "NONE",
                }
            )
            publish_result: ApiResponse = self.post(access_str, data=publish_payload)
            log.info(publish_result)

            vote_result: ApiResponse = self.vote_on_change(fqdn, gerrit_project, changeid)
            log.info(vote_result)

            time.sleep(5)
            submit_result: ApiResponse = self.submit_change(fqdn, gerrit_project, changeid, publish_payload)
            log.info(submit_result)

    # -----------------------------------------------------------------------
    # Groups
    # -----------------------------------------------------------------------

    def create_saml_group(self, _fqdn: str, ldap_group: str) -> ApiResponse:
        """Create saml group from ldap group."""
        ###############################################################
        payload: str = json.dumps({"visible_to_all": "false"})
        saml_group: str = f"saml/{ldap_group}"
        saml_group_encoded: str = quote(saml_group, safe="", encoding=None, errors=None)
        access_str: str = f"groups/{saml_group_encoded}"
        log.info("Encoded SAML group name: %s", saml_group_encoded)
        result: ApiResponse = self.put(access_str, data=payload)
        return result

    def add_github_rights(self, _fqdn: str, gerrit_project: str) -> None:
        """Grant github read to a project."""
        ###############################################################
        # Github Rights

        gerrit_project_encoded: str = quote(gerrit_project, safe="", encoding=None, errors=None)
        # GET /groups/?m=test%2F HTTP/1.0
        access_str: str = "groups/?m=GitHub%20Replication"
        log.info(access_str)
        response: ApiResponse = self.get(access_str)
        body: dict[str, object] = self._json_body(response)
        time.sleep(5)

        # Navigate nested dict: body["GitHub Replication"]["id"]
        gh_repl: dict[str, object] = self._as_dict(body.get("GitHub Replication"))
        githubid: str = self._str_val(gh_repl.get("id"))
        log.info(githubid)

        # POST /projects/MyProject/access HTTP/1.0
        if githubid:
            payload: str = json.dumps(
                {
                    "add": {
                        "refs/*": {
                            "permissions": {
                                "read": {
                                    "rules": {
                                        f"{githubid}": {
                                            "action": "ALLOW",
                                        }
                                    }
                                }
                            }
                        }
                    }
                }
            )
            access_str = f"projects/{gerrit_project_encoded}/access"
            post_response: ApiResponse = self.post(access_str, data=payload)
            post_body: dict[str, object] = self._json_body(post_response)
            pretty: str = json.dumps(post_body, indent=4, sort_keys=True)
            log.info(pretty)
        else:
            log.info("Error no githubid found")

    # -----------------------------------------------------------------------
    # Projects
    # -----------------------------------------------------------------------

    def create_project(
        self,
        _fqdn: str,
        gerrit_project: str,
        ldap_group: str,
        description: str,
        check: bool,
    ) -> ApiResponse:
        """Create a project via the gerrit API.

        Creates a gerrit project.
        Converts ldap group to saml group and sets as owner.

        Example:

        gerrit_url gerrit.o-ran-sc.org/r
        gerrit_project test/test1
        ldap_group oran-gerrit-test-test1-committers
        --description="This is a demo project"

        """
        gerrit_project = quote(gerrit_project, safe="", encoding=None, errors=None)

        access_str: str = f"projects/?query=name:{gerrit_project}"
        response: ApiResponse = self.get(access_str)
        resp = self._response_of(response)
        json_text: str = resp.text.replace(")]}'\n", "").strip()

        results_dict: object = None
        try:
            results_dict = json.loads(json_text)  # pyright: ignore[reportAny]
        except json.decoder.JSONDecodeError:
            log.info(resp)
            log.info("A problem was encountered while querying the Gerrit API.")
            log.debug(resp.text)
            exit(resp.status_code)

        if results_dict:
            log.info("Project already exists")
            exit(1)
        if check:
            exit(0)

        saml_group: str = f"saml/{ldap_group}"
        log.info("SAML group name: %s", saml_group)

        access_str = f"projects/{gerrit_project}"
        payload: str = json.dumps(
            {
                "description": f"{description}",
                "submit_type": "INHERIT",
                "create_empty_commit": "True",
                "owners": [f"{saml_group}"],
            }
        )

        log.info(payload)
        result: ApiResponse = self.put(access_str, data=payload)
        return result

    def list_project_permissions(self, project: str) -> list[str]:
        """List a projects owners."""
        response: ApiResponse = self.get(f"access/?project={project}")
        body: dict[str, object] = self._json_body(response)

        # Navigate: body[project]["local"]
        project_obj: dict[str, object] = self._as_dict(body.get(project))
        local_obj: dict[str, object] = self._as_dict(project_obj.get("local"))

        group_list: list[str] = []
        for k in local_obj:
            ref_obj: dict[str, object] = self._as_dict(local_obj.get(k))
            perms_obj: dict[str, object] = self._as_dict(ref_obj.get("permissions"))
            owner_obj: dict[str, object] = self._as_dict(perms_obj.get("owner"))
            rules_obj: dict[str, object] = self._as_dict(owner_obj.get("rules"))
            for kk in rules_obj:
                group_list.append(kk.replace("ldap:cn=", "").replace(",ou=Groups,dc=freestandards,dc=org", ""))
        return group_list

    def list_project_inherits_from(self, gerrit_project: str) -> str:
        """List who a project inherits from."""
        gerrit_project = quote(gerrit_project, safe="", encoding=None, errors=None)
        response: ApiResponse = self.get(f"projects/{gerrit_project}/access")
        result: dict[str, object] = self._json_body(response)
        inherits_from: dict[str, object] = self._as_dict(result.get("inherits_from"))
        inherits: str = self._str_val(inherits_from.get("id"))
        return inherits
