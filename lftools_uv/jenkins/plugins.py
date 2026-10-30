# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Installed Jenkins plugins that a published security advisory applies to."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any
from urllib.parse import urljoin, urlsplit

import requests

if TYPE_CHECKING:
    import jenkins  # aislop-ignore-line hallucinated-import -- the declared python-jenkins dependency provides the `jenkins` package

# The Jenkins update center's feed, which lists every published advisory.
UPDATE_CENTER_URL = "https://updates.jenkins.io/update-center.actual.json"
_TIMEOUT = 60
# Shown as the last affected version when an advisory's range names none.
UNKNOWN_VERSION = "unknown"


class AdvisoriesError(Exception):
    """The advisory feed could not be fetched or read."""


@dataclass(frozen=True)
class Advisory:
    """A published advisory that applies to an installed plugin."""

    plugin: str
    installed: str
    last_affected: str
    url: str


def _well_formed(warning: Any) -> bool:
    """Whether *warning* holds what ``vulnerable_plugins`` reads.

    That is a string ``type``, ``name`` and ``url``, and, unless
    ``versions`` is absent, a list of ranges that each have a string
    ``pattern``. Jenkins core reads the same fields.
    """
    if not isinstance(warning, dict) or not all(isinstance(warning.get(key), str) for key in ("type", "name", "url")):
        return False
    ranges = warning.get("versions", [])
    return isinstance(ranges, list) and all(
        isinstance(version_range, dict) and isinstance(version_range.get("pattern"), str) for version_range in ranges
    )


def _refuse_redirect_off_https(response: requests.Response, *_args: Any, **_kwargs: Any) -> None:
    """Raise before *response* is followed to a URL that is not HTTPS.

    requests runs response hooks on each response before following its
    redirect, so the target is checked before anything is sent to it.
    """
    if response.is_redirect:
        target = urljoin(response.url, response.headers["Location"])
        if urlsplit(target).scheme != "https":
            msg = f"{UPDATE_CENTER_URL} redirected to {target}, which is not HTTPS"
            raise AdvisoriesError(msg)


def fetch_warnings() -> list[dict[str, Any]]:
    """Return the advisories published in the Jenkins update center.

    Raises:
        AdvisoriesError: If the feed cannot be fetched over HTTPS, or does
            not list its warnings in the expected form.
    """
    try:
        # The feed is served from a mirror the URL redirects to.
        response = requests.get(UPDATE_CENTER_URL, timeout=_TIMEOUT, hooks={"response": _refuse_redirect_off_https})
        response.raise_for_status()
    except requests.RequestException as exc:
        raise AdvisoriesError(f"Could not fetch {UPDATE_CENTER_URL}: {exc}") from exc
    try:
        data = response.json()
    except ValueError as exc:
        raise AdvisoriesError(f"{UPDATE_CENTER_URL} is not JSON: {exc}") from exc
    warnings = data.get("warnings") if isinstance(data, dict) else None
    if not isinstance(warnings, list) or not all(_well_formed(warning) for warning in warnings):
        raise AdvisoriesError(f"{UPDATE_CENTER_URL} does not list its warnings in the expected form")
    return warnings


def _matches(pattern: str, version: str) -> bool:
    """Whether *pattern* matches all of *version*, as Jenkins decides a range holds it."""
    try:
        return re.fullmatch(pattern, version) is not None
    except re.error:
        # Jenkins treats a pattern it cannot compile as matching every version.
        return True


def _last_affected(warning: dict[str, Any], version: str) -> str | None:
    """Return the last affected version of *warning*'s range holding *version*, or None.

    A warning without ranges applies to every version.
    """
    ranges: list[dict[str, Any]] = warning.get("versions") or []
    if not ranges:
        return UNKNOWN_VERSION
    for version_range in ranges:
        if _matches(version_range["pattern"], version):
            return str(version_range.get("lastVersion") or UNKNOWN_VERSION)
    return None


def vulnerable_plugins(server: jenkins.Jenkins, warnings: list[dict[str, Any]]) -> list[Advisory]:
    """Return each advisory in *warnings* that applies to an active plugin on *server*.

    An advisory applies, as it does in Jenkins itself, when its plugin is
    installed and the installed version matches one of the advisory's
    version patterns, or the advisory has none. Results are sorted by
    plugin, then kept in the feed's order.
    """
    by_plugin: dict[str, list[dict[str, Any]]] = {}
    for warning in warnings:
        if warning.get("type") == "plugin":
            by_plugin.setdefault(warning["name"], []).append(warning)
    installed = {
        str(plugin["shortName"]): str(plugin["version"])
        for plugin in server.get_plugins().values()
        if plugin.get("active")
    }
    found: list[Advisory] = []
    for name in sorted(installed):
        version = installed[name]
        for warning in by_plugin.get(name, []):
            last = _last_affected(warning, version)
            if last is not None:
                found.append(Advisory(name, version, last, warning["url"]))
    return found
