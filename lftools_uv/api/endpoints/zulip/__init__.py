# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Zulip REST API helpers for lftools-uv.

This package is the API/business-logic layer for the ``lftools-uv zulip``
command group. It is intentionally import-safe even when the optional
``zulip`` extra is not installed: the import of the upstream ``zulip``
Python package is wrapped so that callers can detect availability via
:func:`zulip_available` and surface a friendly install hint from the CLI
layer (FR-022).

Public surface:

* Configuration resolution — :class:`ZulipConfig`,
  :func:`resolve_config` (precedence per FR-011/FR-012).
* Client factory — :func:`get_client`.
* Feature-level detection — :func:`get_server_feature_level`,
  :func:`check_feature_level` (FR-019 canonical error format).
* Resolution helpers — :func:`resolve_channel`, :func:`resolve_users`,
  :func:`resolve_groups`.
* Domain exceptions — :class:`ZulipConfigError`, :class:`ZulipAPIError`,
  :class:`ZulipFeatureLevelError`, :class:`ZulipAmbiguityError`,
  :class:`ZulipLockoutError`, :class:`ZulipNotFoundError`,
  :class:`ZulipValidationError`.

The implementation is split across submodules by responsibility —
:mod:`~.config`, :mod:`~.features`, :mod:`~.channels`,
:mod:`~.channel_create`, :mod:`~.channel_update`,
:mod:`~.channel_archive`, :mod:`~.folders`, :mod:`~.subscriptions`,
:mod:`~.topics`, :mod:`~.users` and :mod:`~.groups` — and every name
they define is re-exported here. This module remains the single import
path for callers.

See ``specs/001-zulip-channel-mgmt/`` for the full feature design.
"""

from __future__ import annotations

# ``configparser``, ``json`` and the typing names below are not used by
# this module itself: they are re-exported so that every attribute the
# single-module version exposed still resolves through this import path.
# ``lf_config`` in particular is patched as
# ``lftools_uv.api.endpoints.zulip.lf_config`` by the config tests.
import configparser
import json
import logging
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType
from typing import Any, Literal

from lftools_uv import config as lf_config

from .channel_archive import archive_channel, unarchive_channel
from .channel_create import create_channel
from .channel_update import _subscriber_count, update_channel
from .channels import (
    ChannelType,
    _fetch_streams,
    _normalize_channel,
    list_channels,
    resolve_channel,
)
from .config import (
    _LFTOOLS_ZULIP_SECTION,
    _ZULIPRC_API_SECTION,
    ZulipConfig,
    _load_lftools_ini,
    _load_zuliprc,
    get_client,
    resolve_config,
)
from .errors import (
    ZulipAmbiguityError,
    ZulipAPIError,
    ZulipConfigError,
    ZulipError,
    ZulipFeatureLevelError,
    ZulipLockoutError,
    ZulipNotFoundError,
    ZulipValidationError,
)
from .features import FEATURE_LEVELS, check_feature_level, get_server_feature_level
from .folders import (
    _fetch_channel_folders,
    _folder_mutation_result,
    _get_channel_folder_limits,
    _normalize_channel_folder,
    _resolve_single_channel_folder_token,
    _validate_channel_folder_assignment_id,
    _validate_channel_folder_values,
    archive_channel_folder,
    create_channel_folder,
    list_channel_folders,
    plan_folder_move,
    reorder_channel_folders,
    resolve_channel_folder_reference,
    resolve_channel_folder_token,
    unarchive_channel_folder,
    update_channel_folder,
)
from .groups import (
    SYSTEM_ROLE_DISPLAY_NAMES,
    SYSTEM_ROLE_GROUPS,
    GroupSettingValue,
    _build_group_setting_value,
    _build_system_role_display_names,
    _fetch_groups,
    _normalize_group,
    _resolve_single_group_token,
    list_groups,
    resolve_groups,
)
from .logger import log
from .subscriptions import (
    MAX_SUBSCRIBE_USERS,
    list_subscribers,
    subscribe_users,
    unsubscribe_users,
)
from .topics import (
    TOPIC_POLICY_MAP,
    TOPIC_POLICY_REVERSE_MAP,
    VALID_TOPIC_POLICIES,
    TopicPolicy,
    _normalize_topic_policy,
    _resolve_topic_policy_channel,
    get_topic_policy,
    set_topic_policy,
)
from .users import (
    IdMode,
    _fetch_users,
    _normalize_user,
    _resolve_single_user,
    list_users,
    resolve_users,
)

_zulip_module: ModuleType | None
try:  # pragma: no cover - import guard exercised by integration tests
    import zulip as _imported_zulip
except ImportError:  # pragma: no cover - exercised when extra not installed
    _zulip_module = None
else:
    _zulip_module = _imported_zulip


def zulip_available() -> bool:
    """Return ``True`` when the optional ``zulip`` package is importable."""
    return _zulip_module is not None


def _require_zulip() -> Any:
    """Return the imported ``zulip`` module or raise :class:`ZulipConfigError`.

    The CLI layer normally short-circuits before this is reached (it
    presents the canonical FR-022 install hint when the extra is
    missing); ``_require_zulip`` exists so that the API layer can be
    consumed programmatically with a clear error when the extra is not
    installed.

    The optional-import guard, and therefore this function, lives on the
    package rather than in :mod:`~.config` so that rebinding
    ``lftools_uv.api.endpoints.zulip._zulip_module`` — which the tests
    do — is still observed.
    """
    if _zulip_module is None:  # pragma: no cover - defensive
        raise ZulipConfigError(
            "The 'zulip' Python package is not installed. Install with: pip install \"lftools-uv[zulip]\""
        )
    return _zulip_module


#: Everything the single-module version of this endpoint exposed, and
#: therefore everything this package re-exports. Private helpers are
#: listed too: the CLI layer and the test-suite both reach for them
#: through this import path.
__all__ = [
    "Any",
    "ChannelType",
    "FEATURE_LEVELS",
    "GroupSettingValue",
    "IdMode",
    "Iterable",
    "Literal",
    "MAX_SUBSCRIBE_USERS",
    "ModuleType",
    "Path",
    "SYSTEM_ROLE_DISPLAY_NAMES",
    "SYSTEM_ROLE_GROUPS",
    "TOPIC_POLICY_MAP",
    "TOPIC_POLICY_REVERSE_MAP",
    "TopicPolicy",
    "VALID_TOPIC_POLICIES",
    "ZulipAPIError",
    "ZulipAmbiguityError",
    "ZulipConfig",
    "ZulipConfigError",
    "ZulipError",
    "ZulipFeatureLevelError",
    "ZulipLockoutError",
    "ZulipNotFoundError",
    "ZulipValidationError",
    "_LFTOOLS_ZULIP_SECTION",
    "_ZULIPRC_API_SECTION",
    "_build_group_setting_value",
    "_build_system_role_display_names",
    "_fetch_channel_folders",
    "_fetch_groups",
    "_fetch_streams",
    "_fetch_users",
    "_folder_mutation_result",
    "_get_channel_folder_limits",
    "_load_lftools_ini",
    "_load_zuliprc",
    "_normalize_channel",
    "_normalize_channel_folder",
    "_normalize_group",
    "_normalize_topic_policy",
    "_normalize_user",
    "_require_zulip",
    "_resolve_single_channel_folder_token",
    "_resolve_single_group_token",
    "_resolve_single_user",
    "_resolve_topic_policy_channel",
    "_subscriber_count",
    "_validate_channel_folder_assignment_id",
    "_validate_channel_folder_values",
    "_zulip_module",
    "archive_channel",
    "archive_channel_folder",
    "check_feature_level",
    "configparser",
    "create_channel",
    "create_channel_folder",
    "dataclass",
    "get_client",
    "get_server_feature_level",
    "get_topic_policy",
    "json",
    "lf_config",
    "list_channel_folders",
    "list_channels",
    "list_groups",
    "list_subscribers",
    "list_users",
    "log",
    "logging",
    "plan_folder_move",
    "reorder_channel_folders",
    "resolve_channel",
    "resolve_channel_folder_reference",
    "resolve_channel_folder_token",
    "resolve_config",
    "resolve_groups",
    "resolve_users",
    "set_topic_policy",
    "subscribe_users",
    "unarchive_channel",
    "unarchive_channel_folder",
    "unsubscribe_users",
    "update_channel",
    "update_channel_folder",
    "zulip_available",
]
