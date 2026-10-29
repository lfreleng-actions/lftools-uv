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
from jsonschema.exceptions import SchemaError
from jsonschema.validators import validator_for


def check_schema_file(yamlfile: str, schemafile: str) -> None:
    """Verify YAML Schema.

    YAMLFILE: Release YAML file to be validated.

    SCHEMAFILE: SCHEMA file to validate against.

    The validator follows the draft the schema names in ``$schema``,
    falling back to Draft 4 when it names none that ``jsonschema``
    recognises, such as ``http://json-schema.org/schema#``. The schema is
    checked against its draft's meta-schema first, since a malformed
    schema can otherwise let an invalid document pass.

    Raises:
        RuntimeError: The schema is not valid for its draft, or the
            document fails validation.
    """
    with open(yamlfile) as _:
        yaml_file: dict[str, Any] = yaml.safe_load(_)  # pyright: ignore[reportExplicitAny,reportAny]

    with open(schemafile) as _:
        schema_file: dict[str, Any] = yaml.safe_load(_)  # pyright: ignore[reportExplicitAny,reportAny]

    validator_class = validator_for(schema_file, default=jsonschema.Draft4Validator)
    try:
        validator_class.check_schema(schema_file)
    except SchemaError as exc:
        raise RuntimeError(f"{schemafile} is not a valid schema: {exc.message}") from exc

    validation = validator_class(schema_file, format_checker=jsonschema.FormatChecker())

    # Look for errors
    errors: int = 0
    for error in validation.iter_errors(yaml_file):  # pyright: ignore[reportUnknownMemberType,reportAny]
        errors += 1
        logging.error(error)  # pyright: ignore[reportAny]
    if errors > 0:
        raise RuntimeError(f"{errors:d} issues invalidate the release schema")
