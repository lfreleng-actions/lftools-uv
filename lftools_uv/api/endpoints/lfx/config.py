# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Base URL and bearer token resolution for the LFX v2 API.

The base URL comes from ``LFX_API_URL``, then ``url`` in the ``[lfx]``
section of ``lftools.ini``, then :data:`DEFAULT_API_URL`. It must use
``https``, so the token never travels in clear, and carry no query or
fragment, which would swallow the endpoint path appended to it.

The token comes from ``LFX_TOKEN``, then from ``lfx auth token`` when the
LFX CLI is on ``PATH``. It is never read from a command-line option or
from ``lftools.ini``, and never printed.
"""

from __future__ import annotations

import base64
import binascii
import configparser
import datetime
import json
import os
import shutil
import subprocess
import time
from urllib.parse import urlsplit, urlunsplit

from lftools_uv import config as lf_config

from .errors import LfxConfigError

# aislop-ignore-next-line hardcoded-url -- the production fallback after LFX_API_URL and lftools.ini
DEFAULT_API_URL = "https://lfx-api.v2.cluster.lfx.dev"
URL_ENV = "LFX_API_URL"
TOKEN_ENV = "LFX_TOKEN"
INI_SECTION = "lfx"
LFX_CLI = "lfx"
UNPARSABLE_URL = "<a URL that cannot be parsed>"
NO_TOKEN_MESSAGE = (
    f"no LFX token: set {TOKEN_ENV}, or install the LFX CLI and run "
    f"'{LFX_CLI} auth login' so that '{LFX_CLI} auth token' can supply one"
)

#: Seconds to wait for ``lfx auth token``, which may refresh the token.
TOKEN_COMMAND_TIMEOUT = 60


def resolve_base_url() -> str:
    """Return the API base URL, without a trailing slash.

    :raises LfxConfigError: The URL is not an ``https`` URL with a host,
        or ``lftools.ini`` cannot be parsed.
    """
    url = os.environ.get(URL_ENV, "").strip()
    source = URL_ENV
    if not url:
        try:
            url = lf_config.get_setting(INI_SECTION, "url").strip()
            source = "lftools.ini [lfx] url"
        except (configparser.NoSectionError, configparser.NoOptionError):
            url = ""
        except configparser.Error:
            # Parser errors quote the offending line, section or option,
            # any of which may hold the token, so none of it is shown.
            msg = f"lftools.ini cannot be parsed; fix it or set {URL_ENV}"
            raise LfxConfigError(msg) from None
    if not url:
        return DEFAULT_API_URL
    return validate_base_url(url, source)


def validate_base_url(url: str, source: str = "base_url") -> str:
    """Return ``url`` without a trailing slash, refusing anything but https.

    :arg source: Where the URL came from, named in the error.
    :raises LfxConfigError: The URL cannot be parsed, has a malformed
        port, is not an ``https`` URL with a host, or carries a query or
        fragment. The message names ``source`` but never the URL, any
        part of which may hold the token.
    """
    # The refused URL stays out of the message: it is checked before a
    # client exists to redact the token from it, and its host or path
    # may hold the token as well as its userinfo, query or fragment.
    https_msg = f"{source} must be an https:// URL with a host, so the token is never sent in clear"
    try:
        parts = urlsplit(url)
        hostname = parts.hostname
        _ = parts.port
    except ValueError:
        msg = f"{source} cannot be parsed as a URL; it must be an https:// URL with a host"
        raise LfxConfigError(msg) from None
    if parts.scheme.lower() != "https" or not hostname:
        raise LfxConfigError(https_msg)
    # The client appends endpoint paths to the base, so a query or
    # fragment, even an empty one, would swallow them.
    if "?" in url or "#" in url:
        msg = f"{source} must not carry a query or fragment"
        raise LfxConfigError(msg)
    return url.rstrip("/")


def redact_url(url: str) -> str:
    """Return ``url`` without what could carry a secret: userinfo, query and fragment.

    A URL that cannot be parsed, such as one with a malformed port, is
    replaced whole, since none of it can be shown safely.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return UNPARSABLE_URL
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    return urlunsplit((parts.scheme, netloc, parts.path, "", ""))


def _token_from_cli(executable: str) -> str:
    """Run ``lfx auth token`` and return its standard output."""
    try:
        result = subprocess.run(  # noqa: S603
            [executable, "auth", "token"],
            capture_output=True,
            text=True,
            timeout=TOKEN_COMMAND_TIMEOUT,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        msg = f"'{LFX_CLI} auth token' could not run: {type(exc).__name__}"
        raise LfxConfigError(msg) from None
    if result.returncode != 0:
        # Its stderr stays unreported: it may carry the token, which only
        # a successful run hands over for redaction.
        msg = (
            f"'{LFX_CLI} auth token' failed with exit status {result.returncode}; "
            f"run '{LFX_CLI} auth login' or set {TOKEN_ENV}"
        )
        raise LfxConfigError(msg)
    token = result.stdout.strip()
    if not token:
        msg = f"'{LFX_CLI} auth token' printed no token; run '{LFX_CLI} auth login' or set {TOKEN_ENV}"
        raise LfxConfigError(msg)
    return token


def _jwt_expiry(token: str) -> float | None:
    """Return the numeric ``exp`` claim of a JWT, or ``None``.

    Reads the payload without verifying the signature: the API verifies
    it. Anything that is not a JWT with a numeric ``exp`` yields ``None``.
    """
    parts = token.split(".")
    if len(parts) != 3:
        return None
    payload = parts[1]
    try:
        decoded = base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4))
        claims = json.loads(decoded)
    except (binascii.Error, ValueError):
        return None
    if not isinstance(claims, dict):
        return None
    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        return None
    return float(exp)


def check_token_chars(token: str) -> None:
    """Refuse a token that cannot travel in an HTTP header as it is.

    A bearer token is printable ASCII without spaces. Anything else, such
    as a pasted token with a newline and more text after it, would make
    header serialization fail with an error quoting the token.

    :raises LfxConfigError: The token holds whitespace, a control
        character or a non-ASCII character. The message never carries it.
    """
    if not all("!" <= char <= "~" for char in token):
        msg = (
            "the LFX token holds whitespace, a control character or a non-ASCII character, "
            f"so it cannot be sent; check {TOKEN_ENV} or the output of '{LFX_CLI} auth token'"
        )
        raise LfxConfigError(msg)


def check_token(token: str) -> None:
    """Refuse a token that is empty, cannot be sent or has expired.

    An empty token would go out as ``Bearer`` with nothing after it,
    which the API serves as anonymous.

    :raises LfxConfigError: The token is empty, or as
        :func:`check_token_chars` or :func:`check_token_expiry`.
    """
    if not token:
        raise LfxConfigError(NO_TOKEN_MESSAGE)
    check_token_chars(token)
    check_token_expiry(token)


def check_token_expiry(token: str, now: float | None = None) -> None:
    """Refuse a JWT whose ``exp`` claim lies in the past.

    The API serves a request with an expired token as anonymous rather
    than rejecting it, so an expired token would otherwise surface as a
    committee that seems not to exist.

    :raises LfxConfigError: The token has expired.
    """
    exp = _jwt_expiry(token)
    if exp is None:
        return
    current = time.time() if now is None else now
    if exp <= current:
        try:
            when = datetime.datetime.fromtimestamp(exp, tz=datetime.UTC).isoformat()
        except (OverflowError, OSError, ValueError):
            when = str(exp)
        msg = f"the LFX token expired at {when}; run '{LFX_CLI} auth login' or set a fresh {TOKEN_ENV}"
        raise LfxConfigError(msg)


def resolve_token() -> str:
    """Return the bearer token, refusing an unsendable token or an expired JWT.

    :raises LfxConfigError: No token is available, ``lfx auth token``
        failed, or the token cannot be sent or has expired.
    """
    token = os.environ.get(TOKEN_ENV, "").strip()
    if not token:
        executable = shutil.which(LFX_CLI)
        if executable is None:
            raise LfxConfigError(NO_TOKEN_MESSAGE)
        token = _token_from_cli(executable)
    check_token(token)
    return token
