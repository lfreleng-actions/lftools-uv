# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Typer CLI for the LFX v2 API.

:mod:`.apps` owns the Typer objects and each command module registers its
commands on them. The API layer lives in
:mod:`lftools_uv.api.endpoints.lfx`.
"""

from __future__ import annotations

from lftools_uv.typer_apps.lfx.apps import committee_app, lfx_app
from lftools_uv.typer_apps.lfx.committee import (
    EXIT_ERROR,
    EXIT_NOT_FOUND,
    committee_create,
    committee_list,
    committee_members,
    committee_show,
    handle_lfx_error,
)

__all__ = [
    "EXIT_ERROR",
    "EXIT_NOT_FOUND",
    "committee_app",
    "committee_create",
    "committee_list",
    "committee_members",
    "committee_show",
    "handle_lfx_error",
    "lfx_app",
]
