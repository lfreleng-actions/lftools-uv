# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2021 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################

"""Gerrit git interface."""

from __future__ import annotations

import configparser
import json
import logging
import os
import tempfile
import urllib.parse
from typing import Any

import requests
from git import Remote, Repo
from jinja2 import Environment, PackageLoader, select_autoescape

from lftools_uv import config

log = logging.getLogger(__name__)


class Gerrit:
    """Wrapper for Gerrit-specific git methods."""

    def __init__(self, **params: Any) -> None:
        """Initialize the class."""
        self.params: dict[str, Any] = params
        self.fqdn: str = self.params["fqdn"]
        self.project: str = self.params["project"]
        if "creds" not in self.params:
            creds = {
                "authtype": "basic",
                "username": config.get_setting(self.fqdn, "username"),
                "password": config.get_setting(self.fqdn, "password"),
                "endpoint": config.get_setting(self.fqdn, "endpoint"),
                "email": config.get_setting(self.fqdn, "email"),
            }
            params["creds"] = creds

        working_dir = tempfile.mkdtemp()
        log.debug(f"Temporary working directory for git repo: {working_dir}")
        os.chdir(working_dir)

        short_endpoint = self.params["creds"]["endpoint"].split("://")[-1]
        project_endpoint = urllib.parse.urljoin(short_endpoint, self.project)
        remote = "https://{}:{}@{}".format(
            self.params["creds"]["username"], self.params["creds"]["password"], project_endpoint
        )
        Repo.clone_from(remote, working_dir)
        self.repo: Repo = Repo.init(working_dir)
        self.get_commit_hook(self.params["creds"]["endpoint"], working_dir)

        with self.repo.config_writer() as git_config:
            git_config.set_value("user", "name", self.params["creds"]["username"])
            git_config.set_value("user", "email", self.params["creds"]["email"])
        self.origin: Remote = self.repo.remote(name="origin")

        # Get the default branch from the repo
        default_ref = self.repo.git.rev_parse("origin/HEAD", abbrev_ref=True)
        self.default_branch: str = default_ref.split("/")[-1]

    def get_commit_hook(self, endpoint: str, working_dir: str) -> None:
        """Pulls in the Gerrit server's commit hook to add a changeId."""
        hook_url = urllib.parse.urljoin(endpoint, "tools/hooks/commit-msg")
        # The hook url does not include the /a that is typically part of a
        # gerrit url for cloning.
        hook_url = hook_url.replace("/a/", "/", 1)
        local_hooks_path = os.path.join(working_dir, ".git/hooks")
        commit_msg_hook_path = f"{local_hooks_path}/commit-msg"

        try:
            os.mkdir(local_hooks_path)
        except FileExistsError:
            log.debug(f"Directory {local_hooks_path} already exists")
        with requests.get(hook_url) as hook:
            hook.raise_for_status()
            with open(commit_msg_hook_path, "w") as file:
                file.write(hook.text)
            os.chmod(commit_msg_hook_path, 0o755)

    def add_file(self, filepath: str, content: str) -> None:
        """Add a file to the current git repo."""
        if filepath.find("/") >= 0:
            try:
                log.debug(f"Making directories for {filepath[0]}")
                os.makedirs(os.path.split(filepath)[0])
            except FileExistsError:
                log.debug("Directories already exist, skipping")
        with open(filepath, "w") as newfile:
            newfile.write(content)
        self.repo.git.add(filepath)
        log.debug(self.repo.git.status())

    def add_symlink(self, filepath: str, target: str) -> None:
        """Add a symlink to the current git repo."""
        try:
            os.symlink(target, filepath)
        except FileExistsError:
            if not os.path.islink(filepath):
                log.error(f"{filepath} exists and is not a symlink")
                return
        self.repo.git.add(filepath)

    def commit(self, commit_msg: str, issue_id: str | None, push: bool = False) -> None:
        """Commit staged changes.

        This will commit all currently-staged changes, using the provided commit
        message. This can be a single line, or a multi-line header-and-body
        format. The footer is then added with optional Issue-ID, and signed-
        off-by line. If push=True, the change will then be pushed to the
        default branch's change creation link.

        Example:

        commit_msg "Chore: Add arbitrary files"
        issue_id "EX-1234"

        Commit message will read:

        Chore: Add arbitrary files

        Issue-ID: EX-1234
        Signed-off-by: lf-automation <example@example.com>
        """
        sob = config.get_setting(self.fqdn, "sob")
        # Add known \n\n gap to end of commit message by stripping, then adding
        # exactly two newlines.
        commit_msg = f"{commit_msg.strip()}\n\n"
        if issue_id:
            commit_msg += f"Issue-ID: {issue_id}\n"
        commit_msg += f"Signed-off-by: {sob}"
        self.repo.git.commit(f"-m{commit_msg}")
        if push:
            self.repo.git.push(self.origin, f"HEAD:refs/for/{self.default_branch}")

    def add_info_job(self, fqdn: str, gerrit_project: str, issue_id: str | None, agent: str | None) -> None:
        """Add info-verify jenkins job for the new project.

        Example:

        fqdn gerrit.o-ran-sc.org
        gerrit_project test/test1
        jjbrepo ci-mangement
        """
        gerrit_project_dashed = gerrit_project.replace("/", "-")
        filename = f"{gerrit_project_dashed}.yaml"

        buildnode = agent if agent else ""
        if not agent:
            if fqdn == "gerrit.o-ran-sc.org":
                buildnode = "centos7-builder-1c-1g"
            elif fqdn == "gerrit.onap.org":
                buildnode = "centos8-builder-2c-1g"
            else:
                buildnode = "centos7-builder-2c-1g"

        jinja_env = Environment(
            loader=PackageLoader("lftools_uv.git"), autoescape=select_autoescape(), keep_trailing_newline=True
        )
        template = jinja_env.get_template("project.yaml")
        content = template.render(
            project_name_dashed=gerrit_project_dashed,
            project_name=gerrit_project,
            buildnode=buildnode,
            default_branch=self.default_branch,
        )
        log.debug(f"File contents:\n{content}")

        filepath = f"jjb/{gerrit_project_dashed}/{gerrit_project_dashed}.yaml"
        self.add_file(filepath, content)
        commit_msg = f"Chore: Automation adds {filename}"
        self.commit(commit_msg, issue_id, push=True)

    def add_git_review(self, fqdn: str, gerrit_project: str, issue_id: str | None) -> None:
        """Add and push a .gitreview for a project.

        Example:

        fqdn gerrit.o-ran-sc.org
        gerrit_project test/test1
        issue_id: CIMAN-33
        """
        filename = ".gitreview"

        jinja_env = Environment(
            loader=PackageLoader("lftools_uv.git"), autoescape=select_autoescape(), keep_trailing_newline=True
        )
        template = jinja_env.get_template("gitreview")
        content = template.render(fqdn=fqdn, project_name=gerrit_project, default_branch=self.default_branch)
        log.debug(f".gitreview contents:\n{content}")

        self.add_file(filename, content)
        commit_msg = f"Chore: Automation adds {filename}"
        self.commit(commit_msg, issue_id, push=True)

    def add_maven_config(
        self, fqdn: str, gerrit_project: str, issue_id: str | None, nexus3_url: str = "", nexus3_ports: str = ""
    ) -> None:
        """Add the four required JCasC files to create settings for a new project."""
        project_dashed = gerrit_project.replace("/", "-")
        params_path = "config-params.yaml"
        creds_path = "serverCredentialMappings.yaml"
        content_path = "content"
        sb_creds_path = "serverCredentialMappings.sandbox.yaml"

        try:
            default_servers_str = config.get_setting(self.fqdn, "default_servers")
            default_servers = default_servers_str.split(",")
        except configparser.NoOptionError:
            default_servers = ["releases", "snapshots", "staging", "site"]

        additional_credentials = ""
        try:
            credential_json = config.get_setting(self.fqdn, "additional_credentials")
            additional_credentials = json.loads(credential_json)
        except configparser.NoOptionError:
            log.debug("No additional credentials found")
        except json.decoder.JSONDecodeError:
            log.error(
                'Improperly formatted JSON in "additional_credentials". '
                + "Please ensure that all credentials are on a single line, and are not quoted."
            )

        if not nexus3_url:
            try:
                nexus3_url = config.get_setting(self.fqdn, "nexus3")
            except configparser.NoOptionError:
                pass  # If no url is passed in or present in lftools.ini, skip it.

        nexus3_port_list: list[str] = []
        if nexus3_url and not nexus3_ports:
            try:
                nexus3_ports = config.get_setting(self.fqdn, "nexus3_ports")
                nexus3_port_list = nexus3_ports.split(",")
            except configparser.NoOptionError:
                nexus3_port_list = ["10001", "10002", "10003", "10004"]
        elif nexus3_ports:
            try:
                nexus3_port_list = nexus3_ports.split(",")
            except AttributeError:
                log.error("Invalid nexus3_ports designated.")

        jinja_env = Environment(
            loader=PackageLoader("lftools_uv.git"), autoescape=select_autoescape(), keep_trailing_newline=True
        )
        template = jinja_env.get_template(params_path)
        config_params_content = template.render(project_dashed=project_dashed)
        log.debug(f"config-params.yaml contents:\n{config_params_content}")

        template = jinja_env.get_template(creds_path)
        server_creds_content = template.render(
            project_dashed=project_dashed,
            default_servers=default_servers,
            nexus3_url=nexus3_url,
            nexus3_ports=nexus3_port_list,
            additional_credentials=additional_credentials,
        )
        log.debug(f"config-params.yaml contents:\n{server_creds_content}")

        config_path = f"jenkins-config/managed-config-files/mavenSettings/{project_dashed}-settings"
        try:
            os.makedirs(config_path)
        except FileExistsError:
            pass

        self.add_symlink(
            os.path.join(config_path, content_path), "../../../managed-config-templates/mavenSettings-content"
        )
        self.add_symlink(
            os.path.join(config_path, sb_creds_path),
            "../../../managed-config-templates/mavenSettings-serverCredentialMappings.sandbox.yaml",
        )
        self.add_file(os.path.join(config_path, params_path), config_params_content)
        self.add_file(os.path.join(config_path, creds_path), server_creds_content)

        commit_msg = f"Chore: Automation adds {gerrit_project} config files"
        self.commit(commit_msg, issue_id, push=True)
