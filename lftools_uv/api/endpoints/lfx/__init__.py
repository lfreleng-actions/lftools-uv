# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""LFX v2 API client for lftools-uv.

This package is the API layer for the ``lftools-uv lfx`` command group:

* :mod:`~.config` resolves the base URL and the bearer token, and refuses
  an expired JWT before anything is sent.
* :mod:`~.client` holds :class:`LfxClient`, which sends every request with
  the token, ``Accept: application/json``, ``v=1`` and a timeout, and
  follows no redirect.
* :mod:`~.committees` resolves a committee named by UID or SSO group name,
  reads it, lists a project's committees, and creates one.
* :mod:`~.members` reads a committee's members and formats them as
  text, CSV or INFO.yaml committers, adds and removes a member, and
  invites an email address.

The API serves a missing, invalid or expired token as anonymous, and
answers 403 both for a committee the caller may not read and for a UID
that does not exist; the error messages say so.
"""

from __future__ import annotations

from .client import DEFAULT_TIMEOUT, LfxClient
from .committees import (
    COMMITTEE_CATEGORIES,
    INVISIBLE_NOTE,
    JOIN_MODES,
    create_committee,
    find_committee_uids,
    find_project_uid,
    get_committee,
    is_uuid,
    list_project_committees,
    query_resources,
    resolve_committee_uid,
    show_committee,
)
from .config import (
    DEFAULT_API_URL,
    TOKEN_ENV,
    URL_ENV,
    check_token,
    check_token_expiry,
    resolve_base_url,
    resolve_token,
    validate_base_url,
)
from .errors import LfxAmbiguityError, LfxAPIError, LfxConfigError, LfxError, LfxNotFoundError
from .members import (
    NO_USERNAME,
    add_committee_member,
    count_without_username,
    find_members,
    format_csv,
    format_info_yaml,
    format_text,
    get_committee_members,
    hide_emails,
    invite_to_committee,
    remove_committee_member,
    sort_members,
)

__all__ = [
    "COMMITTEE_CATEGORIES",
    "DEFAULT_API_URL",
    "DEFAULT_TIMEOUT",
    "INVISIBLE_NOTE",
    "JOIN_MODES",
    "NO_USERNAME",
    "TOKEN_ENV",
    "URL_ENV",
    "LfxAPIError",
    "LfxAmbiguityError",
    "LfxClient",
    "LfxConfigError",
    "LfxError",
    "LfxNotFoundError",
    "add_committee_member",
    "check_token",
    "check_token_expiry",
    "count_without_username",
    "create_committee",
    "find_committee_uids",
    "find_members",
    "find_project_uid",
    "format_csv",
    "format_info_yaml",
    "format_text",
    "get_committee",
    "get_committee_members",
    "hide_emails",
    "invite_to_committee",
    "is_uuid",
    "list_project_committees",
    "query_resources",
    "remove_committee_member",
    "resolve_base_url",
    "resolve_committee_uid",
    "resolve_token",
    "show_committee",
    "sort_members",
    "validate_base_url",
]
