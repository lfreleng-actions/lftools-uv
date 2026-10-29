# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Configuration subsystem for lftools-uv."""

from __future__ import annotations

import logging
import shutil
import sys
from configparser import ConfigParser, InterpolationError, NoOptionError, NoSectionError
from pathlib import Path
from typing import overload

import platformdirs

log: logging.Logger = logging.getLogger(__name__)


def get_lftools_config_dir() -> Path:
    """Get lftools config directory with backward compatibility migration.

    This function handles migration from the old xdg-based config location
    to the new platformdirs-based location, ensuring existing configurations
    are preserved.

    Returns:
        Path to the lftools configuration directory.
    """
    # New platformdirs-based location (preferred)
    new_config_dir = Path(platformdirs.user_config_dir("lftools"))

    # Old xdg-based location (for backward compatibility)
    old_config_dir = Path.home() / ".config" / "lftools"

    # If new location doesn't exist but old one does, migrate
    if not new_config_dir.exists() and old_config_dir.exists():
        log.info(f"Migrating lftools config from {old_config_dir} to {new_config_dir}")
        try:
            # Create parent directory if needed
            new_config_dir.parent.mkdir(parents=True, exist_ok=True)
            # Copy entire directory structure
            _ = shutil.copytree(old_config_dir, new_config_dir)
            log.info(f"Successfully migrated config to {new_config_dir}")
        except (OSError, PermissionError) as e:
            log.warning(f"Failed to migrate config directory: {e}")
            log.info(f"Continuing to use legacy location: {old_config_dir}")
            return old_config_dir

    # Ensure the config directory exists
    new_config_dir.mkdir(parents=True, exist_ok=True)
    return new_config_dir


def get_lftools_config_file() -> str:
    """Get the path to the lftools configuration file.

    Returns:
        String path to lftools.ini configuration file.
    """
    config_dir = get_lftools_config_dir()
    return str(config_dir / "lftools.ini")


LFTOOLS_CONFIG_FILE: str = get_lftools_config_file()


def get_config() -> ConfigParser:
    """Get the config object."""
    config: ConfigParser = ConfigParser()  # noqa
    _ = config.read(LFTOOLS_CONFIG_FILE)
    return config


def has_section(section: str) -> bool:
    """Get a configuration from a section."""
    config = get_config()
    return config.has_section(section)


@overload
def get_setting(section: str, option: str) -> str: ...


@overload
def get_setting(section: str, option: None = None) -> list[str]: ...


def get_setting(section: str, option: str | None = None) -> str | list[str]:
    """Get a configuration from a section.

    A value that interpolates cleanly, ``%%`` escapes included, reads as
    before. A value that cannot be interpolated, such as a password
    holding a literal ``%``, is returned exactly as written instead of
    raising.
    """
    sys.tracebacklimit = 0
    config: ConfigParser = get_config()

    if option:
        try:
            return config.get(section, option)
        except InterpolationError:
            return config.get(section, option, raw=True)
        except (NoOptionError, NoSectionError) as e:
            raise e

    else:
        try:
            return config.options(section)
        except NoSectionError as e:
            raise e


def set_setting(section: str, option: str, value: str) -> None:
    """Save a configuration setting to config file.

    Each ``%`` in the value is stored as ``%%``, so that ``get_setting``
    reads the value back unchanged.
    """
    config: ConfigParser = get_config()
    config.set(section, option, value.replace("%", "%%"))

    with open(LFTOOLS_CONFIG_FILE, "w") as configfile:
        config.write(configfile)
