# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Exceptions raised by the LFX v2 API client.

No message built here carries the bearer token: every error reaches a
terminal, and ``--debug`` must not change that.
"""

from __future__ import annotations


class LfxError(Exception):
    """Base class for every LFX failure."""


class LfxConfigError(LfxError):
    """The base URL or the token cannot be used, so nothing was sent."""


class LfxAPIError(LfxError):
    """A request failed or the API answered outside 2xx.

    :arg message: Description of the failure.
    :arg status: HTTP status, or ``None`` when no response arrived.
    """

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status: int | None = status


class LfxNotFoundError(LfxError):
    """No committee or project matched the name, or the API answered 404."""


class LfxAmbiguityError(LfxError):
    """More than one committee carries the requested SSO group name."""
