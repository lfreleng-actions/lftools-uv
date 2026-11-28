# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Bearer-token HTTP client for the LFX v2 API.

Every request carries ``Authorization: Bearer <token>``, ``Accept:
application/json`` and ``v=1``, has a timeout, and follows no redirect.
A redirect or a status outside 2xx raises :class:`LfxAPIError`, whose
message never carries the token; callers pass anything else they print
through :meth:`LfxClient.redact` or :meth:`LfxClient.redact_data`.
"""

from __future__ import annotations

import contextlib
import functools
import json
import logging
import re
import threading
from typing import TYPE_CHECKING, Any
from urllib.parse import quote, quote_plus, urlsplit

import requests
from requests.auth import AuthBase

from .config import check_token, check_token_expiry, redact_url, resolve_base_url, resolve_token, validate_base_url
from .errors import LfxAPIError

if TYPE_CHECKING:
    from collections.abc import Iterable, Mapping

log = logging.getLogger(__name__)

#: Seconds to wait to connect and for each read.
DEFAULT_TIMEOUT = 30.0

API_VERSION = "1"

REDACTED = "<redacted>"

#: A query value in free text: what follows ``key=`` after ``?`` or ``&``.
_QUERY_VALUE = re.compile(r"([?&][^=&\s#?]*=)[^&\s#'\"]*")


def _hide_query_values(text: str) -> str:
    """Return ``text`` with every URL query value replaced, keeping the keys."""
    return _QUERY_VALUE.sub(rf"\g<1>{REDACTED}", text)


def _token_forms(token: str) -> set[str]:
    """Return ``token`` as written and in each URL-encoded form it may travel in."""
    return {token, quote(token), quote(token, safe=""), quote_plus(token)}


def _mask_spans(text: str, needles: Iterable[str]) -> str:
    """Return ``text`` with every span any of ``needles`` covers replaced.

    Masking the union of all matches, rather than replacing one needle
    after another, leaves no part of one behind when two overlap.
    """
    covered = [False] * len(text)
    for needle in needles:
        if not needle:
            continue
        start = text.find(needle)
        while start != -1:
            covered[start : start + len(needle)] = [True] * len(needle)
            start = text.find(needle, start + 1)
    if not any(covered):
        return text
    parts: list[str] = []
    index = 0
    while index < len(text):
        end = index
        while end < len(text) and covered[end] == covered[index]:
            end += 1
        parts.append(REDACTED if covered[index] else text[index:end])
        index = end
    return "".join(parts)


class _TransportLogFilter(logging.Filter):
    """Hide LFX query values and tokens from urllib3's request log.

    urllib3 logs each request's path and query string at DEBUG, which
    ``--debug`` enables, and a query value such as a ``page_token`` is
    the API's to choose.

    Every client registers its hosts and tokens here, from any thread,
    while records pass through :meth:`filter`. Each registration swaps
    in a new frozen set under a lock, so a record never iterates a set
    another thread is growing.
    """

    def __init__(self) -> None:
        super().__init__()
        self._lock: threading.Lock = threading.Lock()
        self.hosts: frozenset[str] = frozenset()
        self.tokens: frozenset[str] = frozenset()

    def register(self, hosts: set[str], tokens: set[str]) -> None:
        """Add ``hosts`` and ``tokens`` to what the filter hides."""
        with self._lock:
            self.hosts = self.hosts | hosts
            self.tokens = self.tokens | tokens

    def _hide_tokens(self, text: str) -> str:
        """Return ``text`` with every span any registered token covers replaced."""
        return _mask_spans(text, self.tokens)

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args if isinstance(record.args, tuple) else ()
        lfx_record = any(isinstance(arg, str) and arg in self.hosts for arg in args)
        # Redact the message as it will be shown: a token that matched
        # part of a format placeholder would otherwise break formatting.
        if not record.args and isinstance(record.msg, str):
            message = record.msg
        else:
            try:
                message = record.getMessage()
            except (TypeError, ValueError):
                message = " ".join(str(part) for part in (record.msg, *args))
        if lfx_record:
            message = _hide_query_values(message)
        record.msg = self._hide_tokens(message)
        record.args = None
        return True


_TRANSPORT_LOG_FILTER = _TransportLogFilter()
logging.getLogger("urllib3.connectionpool").addFilter(_TRANSPORT_LOG_FILTER)


def _transport_hosts(base_url: str) -> set[str]:
    """Return the host names urllib3 may log for ``base_url``.

    That is the host as written and as requests sends it: lowercased,
    and IDNA-encoded when it is not ASCII.
    """
    hosts = {urlsplit(base_url).hostname or ""}
    # A host that fails IDNA encoding fails the request before urllib3 logs it.
    with contextlib.suppress(requests.RequestException, ValueError):
        prepared = requests.Request("GET", base_url).prepare().url or ""
        hosts.add(urlsplit(prepared).hostname or "")
    hosts.discard("")
    return hosts


class _BearerAuth(AuthBase):
    """Attach the bearer token to a request.

    Passing the token as an auth object, not a bare header, also stops
    ``requests`` replacing it with credentials from ``~/.netrc``.
    """

    def __init__(self, token: str) -> None:
        self._token: str = token

    def __call__(self, r: requests.PreparedRequest) -> requests.PreparedRequest:
        r.headers["Authorization"] = f"Bearer {self._token}"
        return r

    def __repr__(self) -> str:
        return "_BearerAuth(<redacted>)"


def _error_message(response: requests.Response) -> str | None:
    """Return the ``message`` of a JSON error body, if it has one."""
    try:
        body = response.json()
    except ValueError:
        return None
    if isinstance(body, dict):
        message = body.get("message")
        if isinstance(message, str) and message.strip():
            return message.strip()
    return None


class LfxClient:
    """Minimal client for the LFX v2 API.

    :arg base_url: API base URL; resolved by :func:`resolve_base_url`
        when omitted, and refused unless it is ``https`` either way.
    :arg token: Bearer token; resolved by :func:`resolve_token` when
        omitted. A token that cannot travel in a header, or an expired
        JWT, is refused either way, and expiry is checked again before
        every request.
    :arg timeout: Seconds to wait to connect and for each read.
    :raises LfxConfigError: The URL is not ``https``, no token is
        available, or the token cannot be sent or has expired.
    """

    def __init__(
        self,
        base_url: str | None = None,
        token: str | None = None,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self.base_url: str = resolve_base_url() if base_url is None else validate_base_url(base_url)
        if token is None:
            token = resolve_token()
        else:
            check_token(token)
        self._token: str = token
        self._token_forms: frozenset[str] = frozenset(_token_forms(token))
        self.timeout: float = timeout
        self._session: requests.Session = requests.Session()
        self._session.auth = _BearerAuth(token)
        self._session.headers["Accept"] = "application/json"
        # requests URL-encodes query values and the committee read
        # encodes its UID, so a token echoed back by the API in either
        # reaches the logs and errors encoded.
        _TRANSPORT_LOG_FILTER.register(_transport_hosts(self.base_url), set(self._token_forms))

    def __repr__(self) -> str:
        # Redact before repr(), which would escape a backslash in the token.
        return f"LfxClient(base_url={self.redact(self.base_url)!r})"

    def redact(self, text: str) -> str:
        """Return ``text`` with the token and base URL secrets replaced, for any output.

        The token is also replaced in its URL-encoded forms, which a
        request path built from an API-supplied UID may carry.
        """
        text = text.replace(self.base_url, redact_url(self.base_url))
        return _mask_spans(text, self._token_forms)

    def redact_data(self, value: Any) -> Any:
        """Return a copy of decoded JSON with :meth:`redact` applied to every string.

        Keys and values are both redacted, so the result still encodes as
        valid JSON. A number, boolean or null whose JSON text holds the
        token, such as ``12345`` for a token ``123``, becomes that text
        redacted, a string; any other keeps its type.
        """
        if isinstance(value, str):
            return self.redact(value)
        if value is None or isinstance(value, bool | int | float):
            text = json.dumps(value)
            redacted = self.redact(text)
            return value if redacted == text else redacted
        if isinstance(value, dict):
            return {self.redact(str(key)): self.redact_data(item) for key, item in value.items()}
        if isinstance(value, list):
            return [self.redact_data(item) for item in value]
        return value

    def _refuse_redirect(
        self, method: str, path: str, response: requests.Response, *_args: Any, **_kwargs: Any
    ) -> None:
        """Raise on a redirect, as a response hook.

        requests runs response hooks before it parses a redirect's
        ``Location``, even with ``allow_redirects=False``, so a malformed
        target cannot raise past this refusal.
        """
        if not (response.is_redirect or 300 <= response.status_code < 400):
            return
        location = response.headers.get("Location")
        location = redact_url(location) if location else "an unnamed location"
        # Raising here skips requests reading the body and releasing the
        # connection, so do both now; a body that fails to read must not
        # replace the refusal.
        with contextlib.suppress(requests.RequestException, RuntimeError):
            _ = response.content
        response.close()
        msg = self.redact(
            f"{method} {path} answered HTTP {response.status_code}, a redirect to {location}; refusing to follow it"
        )
        raise LfxAPIError(msg, status=response.status_code)

    def get_response(self, path: str, params: Mapping[str, str] | None = None) -> requests.Response:
        """Send ``GET`` to ``path`` and return the 2xx response.

        :raises LfxConfigError: The token expired since the client was
            built; nothing was sent.
        :raises LfxAPIError: The request failed, was redirected, or
            answered outside 2xx.
        """
        return self._send("GET", path, params)

    def _send(
        self,
        method: str,
        path: str,
        params: Mapping[str, str] | None = None,
        json_body: Any = None,
        headers: Mapping[str, str] | None = None,
    ) -> requests.Response:
        """Send ``method`` to ``path``, with ``json_body`` and ``headers`` when given, and return the 2xx response."""
        # The API serves an expired token as anonymous, so a token that
        # expires mid-lookup would silently hide what it could see.
        check_token_expiry(self._token)
        query = {**(params or {}), "v": API_VERSION}
        url = f"{self.base_url}/{path.lstrip('/')}"
        log_path = self.redact(_hide_query_values(path))
        log.debug("LFX %s %s with parameters %s", method, log_path, sorted(query))
        try:
            response = self._session.request(
                method,
                url,
                params=query,
                json=json_body,
                headers=dict(headers) if headers else None,
                timeout=self.timeout,
                allow_redirects=False,
                hooks={"response": functools.partial(self._refuse_redirect, method, path)},
            )
        except requests.RequestException as exc:
            msg = self.redact(_hide_query_values(f"{method} {path} failed: {type(exc).__name__}: {exc}"))
            raise LfxAPIError(msg) from None
        log.debug("LFX %s %s answered %s", method, log_path, response.status_code)

        if not 200 <= response.status_code < 300:
            message = _error_message(response)
            detail = f": {message}" if message else ""
            msg = self.redact(f"{method} {path} answered HTTP {response.status_code}{detail}")
            raise LfxAPIError(msg, status=response.status_code)
        return response

    def get_json(self, path: str, params: Mapping[str, str] | None = None) -> Any:
        """Send ``GET`` to ``path`` and return the decoded JSON body.

        :raises LfxAPIError: As :meth:`get_response`, or the body is not
            JSON.
        """
        return self._decode("GET", path, self.get_response(path, params))

    def post_json(self, path: str, body: Any, headers: Mapping[str, str] | None = None) -> Any:
        """Send ``POST`` to ``path`` with ``body`` as JSON and return the decoded JSON answer.

        ``headers`` are sent with the request, besides the client's own.

        :raises LfxConfigError: The token expired since the client was
            built; nothing was sent.
        :raises LfxAPIError: The request failed, was redirected, answered
            outside 2xx, or answered a body that is not JSON.
        """
        return self._decode("POST", path, self._send("POST", path, json_body=body, headers=headers))

    def delete(self, path: str, headers: Mapping[str, str] | None = None) -> requests.Response:
        """Send ``DELETE`` to ``path`` with ``headers`` and return the 2xx response.

        :raises LfxConfigError: The token expired since the client was
            built; nothing was sent.
        :raises LfxAPIError: The request failed, was redirected, or
            answered outside 2xx.
        """
        return self._send("DELETE", path, headers=headers)

    def _decode(self, method: str, path: str, response: requests.Response) -> Any:
        """Return the decoded JSON body of ``response``, or raise :class:`LfxAPIError`."""
        try:
            return response.json()
        except ValueError:
            msg = self.redact(f"{method} {path} answered HTTP {response.status_code} with a body that is not JSON")
            raise LfxAPIError(msg, status=response.status_code) from None
