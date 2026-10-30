# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Groovy that the jenkins commands run in the Jenkins script console."""

from __future__ import annotations

from typing import TYPE_CHECKING

from lftools_uv.output import echo

if TYPE_CHECKING:
    import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package

# python-jenkins' run_script appends a line printing an end marker, then cuts
# its answer at the last newline. Printing a newline first makes that cut fall
# exactly at the end of the script's own output, however that output ends.
# print("\n") prints the same character on every platform; println() need not.
_END_OUTPUT = '\nprint("\\n")'


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
