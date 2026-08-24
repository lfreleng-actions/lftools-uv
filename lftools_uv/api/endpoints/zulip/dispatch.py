# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Late-bound access to names that callers rebind on the package.

Most operations in this package resolve a channel before acting on it.
While this package was a single module, rebinding
``lftools_uv.api.endpoints.zulip.resolve_channel`` — which both the CLI
layer and the test-suite do — changed the function that every one of
those callers saw. Importing :func:`~.channels.resolve_channel` straight
from its defining module would quietly break that, because each importer
would then hold its own reference.

Sibling modules therefore import channel resolution from here. The
wrapper looks the name up on the package at call time, so a rebound
``resolve_channel`` is honoured from anywhere in the package, exactly as
before the split. The import is deferred into the function body because
the package namespace is not complete until every submodule has been
imported.
"""

from __future__ import annotations

from typing import Any


def resolve_channel(
    client: Any,
    *,
    name: str | None = None,
    channel_id: int | None = None,
    include_archived: bool = False,
) -> dict[str, Any]:
    """Resolve a channel through the package namespace.

    Signature and behaviour match :func:`~.channels.resolve_channel`,
    which this delegates to unless the package attribute has been
    rebound.
    """
    from lftools_uv.api.endpoints import zulip

    return zulip.resolve_channel(
        client,
        name=name,
        channel_id=channel_id,
        include_archived=include_archived,
    )
