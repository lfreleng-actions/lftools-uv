# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Groovy that the jenkins commands run in the Jenkins script console."""

from __future__ import annotations

import secrets
from typing import TYPE_CHECKING

from lftools_uv.output import echo

if TYPE_CHECKING:
    import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package

# python-jenkins' run_script appends a line printing an end marker, then cuts
# its answer at the last newline. Printing a newline first makes that cut fall
# exactly at the end of the script's own output, however that output ends.
# print("\n") prints the same character on every platform; println() need not.
_END_OUTPUT = '\nprint("\\n")'

# Runs after lines defining `marker`, `field`, `credentialType` and `banner`.
# A credential without `field` is skipped. One whose `field` cannot be read is
# reported on a line starting with `marker`, a random string no value holds.
CREDENTIALS_SCRIPT = """
println(banner)
def creds = com.cloudbees.plugins.credentials.CredentialsProvider.lookupCredentials(
    credentialType, jenkins.model.Jenkins.instance, null, null)
for (c in creds) {
    if (!c.hasProperty(field)) {
        continue
    }
    try {
        println(c.id + " : " + c."${field}")
    } catch (Exception e) {
        println(marker + " " + c.id + ": " + e.toString().readLines().join(" "))
    }
}
"""

# The credential type and banner of each field ``read_credentials`` reads.
_CREDENTIALS = {
    "password": (
        "com.cloudbees.plugins.credentials.common.StandardUsernameCredentials",
        "Printing all the credentials and passwords...",
    ),
    "secret": (
        "com.cloudbees.plugins.credentials.common.StandardCredentials",
        "Printing all secrets...",
    ),
}

REMOVE_OFFLINE_NODES_SCRIPT = """
def numberOfflineNodes = 0
def numberNodes = 0

slaveNodes = hudson.model.Hudson.instance

for (slave in slaveNodes.nodes) {
    def node = slave.computer
    numberNodes ++
    println ""
    println "Checking node ${node.name}:"
    println "\tcomputer.isOffline: ${slave.getComputer().isOffline()}"
    println "\tcomputer.offline: ${node.offline}"

    if (node.offline) {
        numberOfflineNodes ++
        println "\tRemoving node ${node.name}"
        slaveNodes.removeNode(slave)
    }
}

println "Number of Offline Nodes: " + numberOfflineNodes
println "Number of Nodes: " + numberNodes
"""

FORCE_REMOVE_OFFLINE_NODES_SCRIPT = """
for (node in jenkins.model.Jenkins.instance.computers) {
    try {
        println "Checking node: ${node.name}"
        println "\tdisplay-name: ${node.properties.displayName}"
        println "\toffline: ${node.properties.offline}"
        println "\ttemporarily-offline: ${node.properties.temporarilyOffline}"
        if (node.properties.offline) {
            println "Removing bad node: ${node.name}"
            jenkins.model.Jenkins.instance.removeComputer(node)
        }
        println ""
    }
    catch (NullPointerException nullPointer) {
        println "NullPointerException caught"
        println ""
    }
}
"""


def run_groovy(server: jenkins.Jenkins, script: str) -> str:
    """Run *script* in the Jenkins script console.

    Returns:
        Everything *script* printed, exactly.
    """
    output: str = server.run_script(script + _END_OUTPUT)
    return output


def echo_output(output: str) -> None:
    """Print a script's *output*, ending it with one newline; print nothing for none."""
    if output:
        echo(output.removesuffix("\n"))


def read_credentials(server: jenkins.Jenkins, field: str) -> tuple[str, list[str]]:
    """Read *field*, ``password`` or ``secret``, of every credential that has it.

    Returns:
        The output to print: a banner, then an ``id : value`` line for each
        credential read. Then, for each credential whose *field* could not
        be read, its id and the error.
    """
    credential_type, banner = _CREDENTIALS[field]
    marker = secrets.token_hex(16)
    header = (
        f'def marker = "{marker}"\n'
        f'def field = "{field}"\n'
        f"def credentialType = {credential_type}.class\n"
        f'def banner = "{banner}"\n'
    )
    shown: list[str] = []
    unreadable: list[str] = []
    for line in run_groovy(server, header + CREDENTIALS_SCRIPT).splitlines(keepends=True):
        if line.startswith(f"{marker} "):
            unreadable.append(line.removeprefix(f"{marker} ").rstrip("\r\n"))
        else:
            shown.append(line)
    return "".join(shown), unreadable
