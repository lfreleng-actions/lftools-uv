# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Zulip configuration resolution and client construction.

Implements the FR-011/FR-012 precedence chain over ``--zuliprc``,
``./zuliprc``, the ``[zulip]`` section of ``lftools.ini`` and
``~/.zuliprc``, and turns the result into a ``zulip.Client``.
"""

from __future__ import annotations

import configparser
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from lftools_uv import config as lf_config

from .errors import ZulipConfigError, ZulipValidationError


@dataclass(frozen=True)
class ZulipConfig:
    """Resolved Zulip API credentials.

    Either ``config_path`` (a path to a zuliprc-format file) OR the
    three credential fields will be populated, depending on which
    source produced the configuration. The :func:`get_client` factory
    handles both cases transparently.
    """

    email: str | None = None
    api_key: str | None = None
    site: str | None = None
    config_path: Path | None = None
    source: str = "unknown"


_ZULIPRC_API_SECTION = "api"
_LFTOOLS_ZULIP_SECTION = "zulip"


def _load_zuliprc(path: Path) -> ZulipConfig:
    """Validate a zuliprc-format file and return a :class:`ZulipConfig`.

    The file is not parsed here for credential extraction — the
    ``zulip.Client`` consumes the file directly. Parsing only validates
    that the file is readable and contains the expected ``[api]``
    section, producing a clear error otherwise.
    """
    parser = configparser.ConfigParser()
    try:
        with path.open("r", encoding="utf-8") as handle:
            parser.read_file(handle)
    except OSError as exc:
        raise ZulipConfigError(f"Cannot read Zulip config file {path}: {exc}") from exc
    except configparser.Error as exc:
        raise ZulipConfigError(f"Malformed Zulip config file {path}: {exc}") from exc

    if not parser.has_section(_ZULIPRC_API_SECTION):
        raise ZulipConfigError(f"Zulip config file {path} is missing required [api] section")
    return ZulipConfig(config_path=path, source=str(path))


def _load_lftools_ini() -> ZulipConfig | None:
    """Return a :class:`ZulipConfig` synthesized from ``lftools.ini``.

    Returns ``None`` when the ``[zulip]`` section is absent.
    """
    if not lf_config.has_section(_LFTOOLS_ZULIP_SECTION):
        return None
    try:
        email = lf_config.get_setting(_LFTOOLS_ZULIP_SECTION, "email")
        api_key = lf_config.get_setting(_LFTOOLS_ZULIP_SECTION, "key")
        site = lf_config.get_setting(_LFTOOLS_ZULIP_SECTION, "site")
    except (configparser.NoOptionError, configparser.NoSectionError) as exc:
        raise ZulipConfigError(f"lftools.ini [zulip] section is incomplete: {exc}") from exc
    if not (isinstance(email, str) and isinstance(api_key, str) and isinstance(site, str)):
        raise ZulipConfigError("lftools.ini [zulip] section must define email, key, site")
    return ZulipConfig(
        email=email,
        api_key=api_key,
        site=site,
        source="lftools.ini[zulip]",
    )


def resolve_config(
    zuliprc: Path | None = None,
    *,
    cwd: Path | None = None,
    home: Path | None = None,
) -> ZulipConfig:
    """Resolve Zulip configuration using the FR-011/FR-012 precedence chain.

    Precedence (first match wins):

    1. ``zuliprc`` argument (from ``--zuliprc`` CLI flag).
    2. ``./zuliprc`` in the current working directory.
    3. ``[zulip]`` section in ``lftools.ini``.
    4. ``~/.zuliprc``.

    Parameters ``cwd`` and ``home`` allow tests to inject filesystem
    locations; defaults are ``Path.cwd()`` and ``Path.home()``.

    Raises :class:`ZulipConfigError` when no source resolves.
    """
    cwd = cwd or Path.cwd()
    home = home or Path.home()

    if zuliprc is not None:
        path = Path(zuliprc)
        if not path.exists():
            raise ZulipConfigError(f"--zuliprc path does not exist: {path}")
        return _load_zuliprc(path)

    cwd_candidate = cwd / "zuliprc"
    if cwd_candidate.exists():
        return _load_zuliprc(cwd_candidate)

    ini_config = _load_lftools_ini()
    if ini_config is not None:
        return ini_config

    home_candidate = home / ".zuliprc"
    if home_candidate.exists():
        return _load_zuliprc(home_candidate)

    raise ZulipConfigError(
        "No Zulip configuration found. Searched: --zuliprc flag, ./zuliprc, lftools.ini [zulip] section, ~/.zuliprc"
    )


def get_client(zuliprc: Path | None = None, *, config: ZulipConfig | None = None) -> Any:
    """Instantiate a ``zulip.Client`` from the resolved configuration.

    ``zuliprc`` and ``config`` are mutually exclusive; supply at most one.
    When neither is given, configuration is resolved via
    :func:`resolve_config`.
    """
    # ``_require_zulip`` reads the optional-import guard that lives on
    # the package, so it is imported at call time rather than bound here.
    from lftools_uv.api.endpoints.zulip import _require_zulip

    if zuliprc is not None and config is not None:
        raise ZulipValidationError("Pass either 'zuliprc' or 'config', not both")
    resolved = config or resolve_config(zuliprc)
    if resolved.config_path is not None:
        zulip_module = _require_zulip()
        return zulip_module.Client(config_file=str(resolved.config_path))
    # No zuliprc file — all three credential fields must be populated.
    missing: list[str] = []
    if not (isinstance(resolved.email, str) and resolved.email.strip()):
        missing.append("email")
    if not (isinstance(resolved.api_key, str) and resolved.api_key.strip()):
        missing.append("api_key")
    if not (isinstance(resolved.site, str) and resolved.site.strip()):
        missing.append("site")
    if missing:
        raise ZulipConfigError(f"Incomplete Zulip credentials from {resolved.source}: missing {', '.join(missing)}")
    zulip_module = _require_zulip()
    return zulip_module.Client(
        email=resolved.email,
        api_key=resolved.api_key,
        site=resolved.site,
    )
