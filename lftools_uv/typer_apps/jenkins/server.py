# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2017 The Linux Foundation
"""The Jenkins command group and its server-wide commands."""

import logging
from urllib.error import HTTPError

import typer

from lftools_uv.jenkins import Jenkins
from lftools_uv.output import echo

log = logging.getLogger(__name__)

jenkins_app = typer.Typer(help="Query information about the Jenkins Server.")


# Global callback for jenkins app to initialize Jenkins client
@jenkins_app.callback()
def jenkins_callback(
    ctx: typer.Context,
    conf: str | None = typer.Option(None, "--conf", "-c", help="Path to jenkins_jobs.ini config."),
    server: str = typer.Option(
        "jenkins",
        "--server",
        "-s",
        envvar="JENKINS_URL",
        help="The URL to a Jenkins server. Alternatively the jenkins_jobs.ini section to parse for url/user/password configuration if available.",
    ),
    user: str = typer.Option("admin", "--user", "-u", envvar="JENKINS_USER"),
    password: str | None = typer.Option(None, "--password", "-p", envvar="JENKINS_PASSWORD"),
) -> None:
    """Query information about the Jenkins Server."""
    # Skip initialization if we're just showing help
    if ctx.resilient_parsing:
        return

    try:
        jenkins_client = Jenkins(server, user, password, config_file=conf)
        if ctx.obj is None:
            ctx.obj = {}
        ctx.obj["jenkins"] = jenkins_client

        # Also store credentials for compatibility
        ctx.obj["username"] = user
        ctx.obj["password"] = password

        # Register in AppState if available
        state = ctx.obj.get("state")
        if state:
            state.jenkins = jenkins_client
    except Exception:
        log.exception("Failed to initialize Jenkins client")
        # For help requests, don't fail - just continue without initializing client
        if ctx.obj is None:
            ctx.obj = {}


@jenkins_app.command("get-credentials")
def get_credentials(ctx: typer.Context) -> None:
    """Print all available Credentials."""
    try:
        jenkins = ctx.obj["jenkins"]
        groovy_script = """
import com.cloudbees.plugins.credentials.*

println "Printing all the credentials and passwords..."
def creds = com.cloudbees.plugins.credentials.CredentialsProvider.lookupCredentials(
    com.cloudbees.plugins.credentials.common.StandardUsernameCredentials.class,
    Jenkins.instance,
    null,
    null
);

for (c in creds) {
    try {
        println(c.id + " : " + c.password )
    } catch (MissingPropertyException) {}
}
"""
        result = jenkins.server.run_script(groovy_script)
        echo(result)
    except Exception:
        log.exception("Failed to get credentials")
        raise typer.Exit(1) from None


@jenkins_app.command("get-secrets")
def get_secrets(ctx: typer.Context) -> None:
    """Print all available secrets."""
    try:
        jenkins = ctx.obj["jenkins"]
        groovy_script = """
import com.cloudbees.plugins.credentials.*

println "Printing all secrets..."
def creds = com.cloudbees.plugins.credentials.CredentialsProvider.lookupCredentials(
    com.cloudbees.plugins.credentials.common.StandardCredentials.class,
    Jenkins.instance,
    null,
    null
);

for (c in creds) {
    try {
        println(c.id + " : " + c.secret )
    } catch (MissingPropertyException) {}
}
"""
        result = jenkins.server.run_script(groovy_script)
        echo(result)
    except Exception:
        log.exception("Failed to get secrets")
        raise typer.Exit(1) from None


@jenkins_app.command("get-private-keys")
def get_private_keys(ctx: typer.Context) -> None:
    """Print all available SSH User Private Keys."""
    try:
        jenkins = ctx.obj["jenkins"]
        groovy_script = """
import com.cloudbees.plugins.credentials.*
import com.cloudbees.jenkins.plugins.sshcredentials.impl.BasicSSHUserPrivateKey

println "Printing all SSH User Private keys ..."
def creds = com.cloudbees.plugins.credentials.CredentialsProvider.lookupCredentials(
    com.cloudbees.plugins.credentials.Credentials.class,
    Jenkins.instance,
    null,
    null
);

for (c in creds) {
    if(c instanceof BasicSSHUserPrivateKey) {
        println("SSH Private key ID: " + c.getId())
        println("SSH User name: " + c.getUsername())
        println("SSH Private key passphrase: " + c.getPassphrase())
        println("SSH Private key: " + c.getPrivateKey())
    }
}
"""
        result = jenkins.server.run_script(groovy_script)
        echo(result)
    except Exception:
        log.exception("Failed to get private keys")
        raise typer.Exit(1) from None


@jenkins_app.command("groovy")
def groovy(ctx: typer.Context, groovy_file: str = typer.Argument(..., help="Path to groovy script file")) -> None:
    """Run a groovy script."""
    try:
        with open(groovy_file) as f:
            data = f.read()

        jenkins = ctx.obj["jenkins"]
        result = jenkins.server.run_script(data)
        echo(result)
    except FileNotFoundError:
        log.error(f"Groovy file not found: {groovy_file}")
        raise typer.Exit(1) from None
    except Exception:
        log.exception("Failed to run groovy script")
        raise typer.Exit(1) from None


@jenkins_app.command("quiet-down")
def quiet_down(
    ctx: typer.Context,
    yes: bool = typer.Option(False, "--yes", "-y", help="Proceed without confirmation"),
) -> None:
    """Put Jenkins into 'Quiet Down' mode."""
    version = "unknown"
    try:
        jenkins = ctx.obj["jenkins"]
        version = jenkins.server.get_version()

        # Ask permission first if not auto-confirmed
        if not yes:
            confirmed = typer.confirm("Quiet down Jenkins?")
            if not confirmed:
                log.info("Operation cancelled.")
                return

        jenkins.server.quiet_down()
    except HTTPError as m:
        if m.code == 405:
            log.exception(
                f"\n[{m}]\nJenkins {version} does not support Quiet Down without a CSRF Token. (CVE-2017-04-26)\nPlease file a bug with 'python-jenkins'"
            )
            raise typer.Exit(1) from None
        else:
            log.exception("HTTP error: %s", m)
            raise typer.Exit(1) from None
    except Exception:
        log.exception("Failed to quiet down Jenkins")
        raise typer.Exit(1) from None


@jenkins_app.command("remove-offline-nodes")
def remove_offline_nodes(
    ctx: typer.Context,
    force: bool = typer.Option(
        False, "--force", help="Forcibly remove nodes, use only if the non-force version fails."
    ),
) -> None:
    """Remove any offline nodes."""
    try:
        jenkins = ctx.obj["jenkins"]

        groovy_script = """
import hudson.model.*

def numberOfflineNodes = 0
def numberNodes = 0

slaveNodes = hudson.model.Hudson.instance

for (slave in slaveNodes.nodes) {
    def node = slave.computer
    numberNodes ++
    println ""
    println "Checking node ${node.name}:"
    println '\tcomputer.isOffline: ${slave.getComputer().isOffline()}'
    println '\tcomputer.offline: ${node.offline}'

    if (node.offline) {
        numberOfflineNodes ++
        println '\tRemoving node ${node.name}'
        slaveNodes.removeNode(slave)
    }
}

println "Number of Offline Nodes: " + numberOfflineNodes
println "Number of Nodes: " + numberNodes
"""

        force_script = """
import jenkins.*
import jenkins.model.*
import hudson.*
import hudson.model.*

for (node in Jenkins.instance.computers) {
    try {
        println "Checking node: ${node.name}"
        println "\tdisplay-name: ${node.properties.displayName}"
        println "\toffline: ${node.properties.offline}"
        println "\ttemporarily-offline: ${node.properties.temporarilyOffline}"
        if (node.properties.offline) {
            println "Removing bad node: ${node.name}"
            Jenkins.instance.removeComputer(node)
        }
        println ""
    }
    catch (NullPointerException nullPointer) {
        println "NullPointerException caught"
        println ""
    }
}
"""

        if force:
            result = jenkins.server.run_script(force_script)
        else:
            result = jenkins.server.run_script(groovy_script)
        echo(result)
    except Exception:
        log.exception("Failed to remove offline nodes")
        raise typer.Exit(1) from None
