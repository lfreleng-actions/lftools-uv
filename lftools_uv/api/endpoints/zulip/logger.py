# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2026 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Shared logger for the Zulip endpoint package."""

from __future__ import annotations

import logging

#: Every module in this package logs through this one logger, so records
#: keep the ``lftools_uv.api.endpoints.zulip`` identity they carried when
#: the package was a single module. The name is derived from this
#: module's own name rather than hardcoded, so it follows the package if
#: it is ever moved.
log: logging.Logger = logging.getLogger(__name__.rpartition(".")[0])
