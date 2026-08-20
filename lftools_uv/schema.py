# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Verify YAML Schema."""

from __future__ import annotations

import logging
from typing import Any

import jsonschema
import yaml


def check_schema_file(yamlfile: str, schemafile: str) -> None:
    """Verify YAML Schema.

    YAMLFILE: Release YAML file to be validated.

    SCHEMAFILE: SCHEMA file to validate against.
    """
    with open(yamlfile) as _:
        yaml_file: dict[str, Any] = yaml.safe_load(_)  # pyright: ignore[reportExplicitAny,reportAny]

    with open(schemafile) as _:
        schema_file: dict[str, Any] = yaml.safe_load(_)  # pyright: ignore[reportExplicitAny,reportAny]

    validation: jsonschema.Draft4Validator = jsonschema.Draft4Validator(
        schema_file, format_checker=jsonschema.FormatChecker()
    )

    # Look for errors
    errors: int = 0
    for error in validation.iter_errors(yaml_file):  # pyright: ignore[reportUnknownMemberType,reportAny]
        errors += 1
        logging.error(error)  # pyright: ignore[reportAny]
    if errors > 0:
        raise RuntimeError(f"{errors:d} issues invalidate the release schema")
