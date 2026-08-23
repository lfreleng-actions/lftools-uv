# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Domain exceptions raised by the Zulip endpoint package.

Every error raised by this package derives from :class:`ZulipError`,
so the CLI layer can catch a single base class and still branch on
the specific subclasses where the presentation differs.
"""

from __future__ import annotations

from typing import Any


class ZulipError(Exception):
    """Base class for all Zulip-related errors raised by this module."""


class ZulipConfigError(ZulipError):
    """Raised when Zulip configuration cannot be located or parsed."""


class ZulipAPIError(ZulipError):
    """Raised when the Zulip server returns an error response."""


class ZulipFeatureLevelError(ZulipError):
    """Raised when the server lacks the required Zulip feature level.

    The string form follows the FR-019 canonical format
    ``This operation requires Zulip feature level X (server has Y)``.
    """

    def __init__(self, required: int, actual: int, feature_name: str = "") -> None:
        self.required = required
        self.actual = actual
        self.feature_name = feature_name
        message = f"This operation requires Zulip feature level {required} (server has {actual})"
        super().__init__(message)


class ZulipAmbiguityError(ZulipError):
    """Raised when a name lookup matches more than one entity."""

    def __init__(self, message: str, matches: list[dict[str, Any]] | None = None) -> None:
        super().__init__(message)
        self.matches = matches or []


class ZulipNotFoundError(ZulipError):
    """Raised when a channel/user/group cannot be located by name or id."""


class ZulipLockoutError(ZulipError):
    """Raised when an operation would lock all users out of a channel."""


class ZulipValidationError(ZulipError):
    """Raised for client-side validation failures (e.g. mutex flags)."""
