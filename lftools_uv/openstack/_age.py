# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Age checks for OpenStack resources."""

from datetime import UTC, datetime, timedelta


def created_within(created_at: str, days: int) -> bool:
    """Return whether a resource was created within the last ``days`` days.

    OpenStack reports ``created_at`` in UTC: Nova and Glance as
    ``...Z``, Cinder with no zone at all. Comparing either with naive
    local time moves the cutoff by the host's UTC offset, so parse the
    value as UTC and compare it with the current time in UTC.
    ``fromisoformat`` reads both forms on Python 3.11 and later.
    """
    created = datetime.fromisoformat(created_at)
    if created.tzinfo is None:
        created = created.replace(tzinfo=UTC)
    return created >= datetime.now(UTC) - timedelta(days=days)
