# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Helper for INFO file generation."""

import logging

from lftools_uv.api.endpoints.lfx import (
    LfxClient,
    count_without_username,
    format_info_yaml,
    get_committee_members,
    resolve_committee_uid,
)

log = logging.getLogger(__name__)


def helper_yaml4info(group: str) -> str:
    """Build yaml of committers for your INFO.yaml.

    Returns one INFO.yaml committer entry per member of the LFX committee
    whose SSO group name is ``group``, read with the token and API URL the
    ``lfx`` commands use. A committee UID works in place of the name.
    Members without a username are left out, with a warning.

    Raises:
        LfxError: If the token or URL is missing or refused, no committee
            or more than one has the name, or the API request fails,
            a 403 for a token without the ``auditor`` relation included.
    """
    client = LfxClient()
    members = get_committee_members(client, resolve_committee_uid(client, group))
    left_out = count_without_username(members)
    if left_out:
        noun = "member" if left_out == 1 else "members"
        log.warning("Left out %d %s without a username", left_out, noun)
    return format_info_yaml(members, client.redact)
