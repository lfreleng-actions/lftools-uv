# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Console output helpers.

lftools-uv writes two different kinds of text on two different streams, and
the split matters to anything parsing the output.

*Results* are the answer the caller asked for: the names of the servers that
were listed, the total cost of a stack, a ``--json`` payload. These go to
**stdout**, whatever the log level, and carry no level prefix. :func:`echo`
writes them.

*Diagnostics* describe what a command is doing: progress, warnings and
failures. These go to **stderr** through the logging system, which gives them
a level and a logger name and lets an operator raise or lower the verbosity
without silencing the result. Modules emit them through
``logging.getLogger(__name__)`` directly; the handler configured in
``lftools_uv/__init__.py`` renders ``INFO`` records as a bare message and
higher levels as ``LEVEL: message``.

Keeping the two on separate streams is what lets a caller run
``lftools-uv ... --json | jq`` without a warning corrupting the payload. It is
required by Principle VI of the project constitution and documented for
callers in ``docs/commands/rtd.rst``.
"""

from __future__ import annotations

__all__ = ["echo"]


def echo(message: object = "") -> None:
    """Write one line of command output to stdout.

    Use this for text the caller asked for and may parse. Use a module
    logger instead for anything describing how the command is getting on;
    that reaches stderr.

    :arg message: Value to write. Rendered with :func:`str`.
    """
    # aislop-ignore-next-line python-print-debug -- deliberate result output; see module docstring
    print(message)  # noqa: T201
