# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Zulip REST API client wrapper for lftools-uv.

This module exposes the Zulip channel/user/group operations consumed by
the ``lftools_uv.typer_apps.zulip`` CLI layer. It is intentionally
import-safe even when the optional ``zulip`` extra is not installed: the
import of the ``zulip`` Python package is wrapped so that callers can
detect availability via :func:`zulip_available` and produce a friendly
error from the CLI layer (FR-022).

See ``specs/001-zulip-channel-mgmt/`` for the full feature design.
"""

from __future__ import annotations

try:  # pragma: no cover - import guard tested via integration
    import zulip as _zulip_module
except ImportError:  # pragma: no cover - exercised when extra not installed
    _zulip_module = None


def zulip_available() -> bool:
    """Return ``True`` when the optional ``zulip`` package is importable."""
    return _zulip_module is not None
