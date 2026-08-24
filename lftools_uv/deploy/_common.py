# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Constants and logger shared by the deploy helpers."""

from __future__ import annotations

import logging

_CONTENT_TYPE_TEXT = "text/plain"
_CONTENT_TYPE_XML = "application/xml"
_BANNER_HASHES = "#######################################################"


# Named for the package rather than derived from __name__, so that every
# module keeps emitting records under "lftools_uv.deploy" as they did when
# these helpers all lived in a single module.
log: logging.Logger = logging.getLogger("lftools_uv.deploy")

# Scheme assumed for Nexus URLs supplied without one, preserving the historical
# behaviour of the shell scripts these helpers replaced.
_DEFAULT_URL_SCHEME = "http://"
logging.getLogger("botocore").setLevel(logging.CRITICAL)
