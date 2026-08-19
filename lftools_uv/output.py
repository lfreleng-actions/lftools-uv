# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Console output helpers.

lftools-uv writes two different kinds of text, and they have different
contracts with the caller.

*Diagnostics* describe what a command is doing: progress, warnings and
failures. They belong to the logging system, which gives them a level, a
logger name and a timestamp when one is configured, and lets an operator
raise or lower the verbosity without changing the code. Modules emit these
through ``logging.getLogger(__name__)`` directly. The package configures a
handler in ``lftools_uv/__init__.py`` that renders ``INFO`` records as a bare
message and higher levels as ``LEVEL: message``.

*Results* are the answer the caller asked for: the names of the servers that
were listed, the total cost of a stack. CI pipelines parse this text, so it
must reach stdout whatever the log level, and must not gain a level prefix.
:func:`echo` exists to write it.

Keeping the two apart means the verbosity of a command can be changed without
silencing its output, and the output can be captured without also capturing
the commentary.
"""

from __future__ import annotations

__all__ = ["echo"]


def echo(message: object = "") -> None:
    """Write one line of command output to stdout.

    Use this for text the caller asked for and may parse. Use a module
    logger instead for anything describing how the command is getting on.

    :arg message: Value to write. Rendered with :func:`str`.
    """
    # aislop-ignore-next-line python-print-debug -- deliberate result output; see module docstring
    print(message)  # noqa: T201
