# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Enable or disable the Jenkins jobs whose full name matches a regex."""

from __future__ import annotations

import base64
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package

# Runs after two lines defining `patternB64` and `disable`. Every line is
# printed with println: python-jenkins drops a final line without a newline.
SET_DISABLED_SCRIPT = """
def pattern = java.util.regex.Pattern.compile(new String(patternB64.decodeBase64(), "UTF-8"))
def matched = 0
jenkins.model.Jenkins.instance.getAllItems(jenkins.model.ParameterizedJobMixIn.ParameterizedJob.class).each { job ->
    if (!pattern.matcher(job.fullName).find()) {
        return
    }
    matched++
    if (job.isDisabled() == disable) {
        return
    }
    job.makeDisabled(disable)
    println((job.isDisabled() == disable ? "CHANGED " : "FAILED ") + job.fullName)
}
println("MATCHED=" + matched)
"""

_CHANGED = "CHANGED "
_FAILED = "FAILED "
_MATCHED = "MATCHED="


class JobsError(Exception):
    """No job matched, or Jenkins gave no usable answer."""


def set_jobs_disabled(server: jenkins.Jenkins, regex: str, disable: bool) -> tuple[list[str], list[str]]:
    """Disable, or enable, every job whose full name matches *regex*.

    *regex* is a Java regular expression, found anywhere in the name. It
    reaches Jenkins base64-encoded, so it never becomes script source.

    Returns:
        The names of the jobs changed, and of those that did not change.

    Raises:
        JobsError: If no job matched, or the answer carries no match count.
    """
    pattern_b64 = base64.b64encode(regex.encode("utf-8")).decode("ascii")
    header = f'def patternB64 = "{pattern_b64}"\ndef disable = {"true" if disable else "false"}\n'
    output: str = server.run_script(header + SET_DISABLED_SCRIPT)

    changed: list[str] = []
    failed: list[str] = []
    matched: int | None = None
    for line in output.splitlines():
        if line.startswith(_CHANGED):
            changed.append(line.removeprefix(_CHANGED))
        elif line.startswith(_FAILED):
            failed.append(line.removeprefix(_FAILED))
        elif line.startswith(_MATCHED) and line.removeprefix(_MATCHED).isdecimal():
            matched = int(line.removeprefix(_MATCHED))

    if matched is None:
        msg = f"Jenkins did not report how many jobs match '{regex}': {output!r}"
        raise JobsError(msg)
    if matched == 0:
        msg = f"No Jenkins jobs match '{regex}'"
        raise JobsError(msg)
    return changed, failed
