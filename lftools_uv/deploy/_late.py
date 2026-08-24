# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Late-bound lookups of names exported by ``lftools_uv.deploy``.

While these helpers lived in one module they resolved each other through
that module's globals, so replacing an attribute on ``lftools_uv.deploy``
also changed what the other helpers called. Callers and tests rely on
that: they patch ``lftools_uv.deploy._log_error_and_exit`` and
``lftools_uv.deploy.copy_archives``. Looking those two names up on the
package at call time, rather than binding them at import time, keeps the
behaviour identical now that the helpers are spread over several modules.
"""

from __future__ import annotations

from typing import NoReturn


def _fail(*msg_list: object) -> NoReturn:
    """Call ``lftools_uv.deploy._log_error_and_exit``."""
    from lftools_uv import deploy

    deploy._log_error_and_exit(*msg_list)


def _copy_archives(workspace: str, pattern: list[str] | None = None) -> None:
    """Call ``lftools_uv.deploy.copy_archives``."""
    from lftools_uv import deploy

    deploy.copy_archives(workspace, pattern)
