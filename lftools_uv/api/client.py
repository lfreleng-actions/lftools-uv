# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2019, 2023 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""REST API interface using Requests."""

from __future__ import annotations

import contextlib
import json
import logging
from typing import Any
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests

_CONTENT_TYPE_JSON = "application/json"

# requests resends a request redirected with one of these without its body:
# as a GET after a 302 or 303, or after a 301 answering a POST, and with its
# method otherwise. 307 and 308 keep both, and are followed as usual.
_BODY_DROPPING_REDIRECTS = frozenset({301, 302, 303})
_SAFE_METHODS = frozenset({"GET", "HEAD"})

log: logging.Logger = logging.getLogger(__name__)


# Type alias for parsed JSON response body.
# REST APIs return heterogeneous JSON; Any is unavoidable at
# this deserialization boundary.  Callers should narrow as needed.
ApiBody = dict[str, object] | list[object] | str | None

# Full API response: plain Response on certain status codes,
# or a (Response, body) tuple when a body was parsed.
ApiResponse = requests.Response | tuple[requests.Response, ApiBody]


class RedirectRefusedError(requests.RequestException):
    """A redirect that would lose a request's method or body was not followed."""


_UNPARSABLE_URL = "<a URL that cannot be parsed>"


def _redacted(url: str) -> str:
    """Return *url* without what could carry a secret: userinfo, query values and fragment.

    Query keys stay, so the message still shows the URL's shape. A URL
    that cannot be parsed, such as one with a port out of range, is
    replaced whole, since none of it can be shown safely.
    """
    try:
        parts = urlsplit(url)
        host = parts.hostname or ""
        port = parts.port
    except ValueError:
        return _UNPARSABLE_URL
    if ":" in host:
        host = f"[{host}]"
    netloc = host if port is None else f"{host}:{port}"
    query = urlencode([(key, "REDACTED") for key, _ in parse_qsl(parts.query, keep_blank_values=True)], safe="")
    return urlunsplit((parts.scheme, netloc, parts.path, query, ""))


def _lost_by_redirect(response: requests.Response) -> str | None:
    """Return what following *response*'s redirect would lose, or None if nothing.

    Losing the method means the request would be resent as a GET; losing
    the body means it would be resent without the body it carries.
    """
    request = response.request
    method = (request.method or "").upper()
    if method in _SAFE_METHODS or response.status_code not in _BODY_DROPPING_REDIRECTS:
        return None
    if response.status_code != 301 or method == "POST":
        return "its method, resending it as a GET"
    if request.body:
        return "its body"
    return None


def _refuse_redirect_losing_request(response: requests.Response, *_args: Any, **_kwargs: Any) -> None:
    """Raise before requests follows a redirect that would lose part of a request.

    requests runs response hooks on each response before following its
    redirect, so nothing is sent to the new location.

    Raises:
        RedirectRefusedError: If following the redirect would lose the
            request's method or body.
    """
    if not response.is_redirect:
        return
    lost = _lost_by_redirect(response)
    if lost is None:
        return
    try:
        target = _redacted(urljoin(response.url, response.headers["Location"]))
    except ValueError:
        target = _UNPARSABLE_URL
    # requests reads a redirect's body and releases its connection before
    # following it. Raising here skips that, so do it now: reading the body
    # first lets the connection be reused rather than dropped. A body that
    # fails to read must not replace the refusal, so the response is then
    # only closed.
    with contextlib.suppress(requests.RequestException, RuntimeError):
        _ = response.content
    response.close()
    msg = (
        f"{response.request.method} {_redacted(response.url)} was redirected to {target} with HTTP "
        f"{response.status_code}, which would lose {lost}; not following it. "
        "Use the URL it redirects to."
    )
    raise RedirectRefusedError(msg, response=response)


class RestApi:
    """A generic REST API interface."""

    # -- Type-safe response helpers ------------------------------------------

    @staticmethod
    def _json_body(response: ApiResponse) -> dict[str, object]:
        """Extract a JSON dict body from an API response.

        Raises:
            ValueError: If the response has no dict body.
        """
        if isinstance(response, tuple):
            body: ApiBody = response[1]
            if isinstance(body, dict):
                return body
        msg: str = "Expected JSON dict body in API response"
        raise ValueError(msg)

    @staticmethod
    def _list_body(response: ApiResponse) -> list[object]:
        """Extract a JSON list body from an API response.

        Raises:
            ValueError: If the response has no list body.
        """
        if isinstance(response, tuple):
            body: ApiBody = response[1]
            if isinstance(body, list):
                return body
        msg: str = "Expected JSON list body in API response"
        raise ValueError(msg)

    @staticmethod
    def _response_of(response: ApiResponse) -> requests.Response:
        """Extract the Response object from an API response."""
        if isinstance(response, tuple):
            return response[0]
        return response

    @staticmethod
    def _require_status(response: ApiResponse, action: str, *expected: int) -> requests.Response:
        """Return the Response if its status is one of *expected*.

        With no *expected* codes, any 2xx status succeeds. Otherwise log
        the server's response text and raise.

        Raises:
            requests.HTTPError: If the status is not one expected.
        """
        resp: requests.Response = RestApi._response_of(response)
        status: int = resp.status_code
        if status in expected or (not expected and 200 <= status < 300):
            return resp
        log.error("%s failed: HTTP %s: %s", action, status, resp.text.strip())
        msg: str = f"{action} failed: HTTP {status}"
        raise requests.HTTPError(msg, response=resp)

    def __init__(self, **kwargs: str | dict[str, str]) -> None:
        """Initialize the REST API class."""
        self.params: dict[str, str | dict[str, str]] = kwargs

        creds_raw: str | dict[str, str] = kwargs["creds"]
        if not isinstance(creds_raw, dict):
            msg: str = "creds must be a dict"
            raise TypeError(msg)
        self.creds: dict[str, str] = creds_raw

        if "timeout" not in self.params:
            self.timeout: int | None = None

        self.endpoint: str = self.creds["endpoint"]

        if self.creds["authtype"] == "basic":
            self.username: str = self.creds["username"]
            self.password: str = self.creds["password"]
            self.r: requests.Session = requests.Session()
            self.r.auth = (self.username, self.password)
            self.r.headers.update(
                {
                    "Content-Type": "application/json; charset=UTF-8",
                    "Accept": _CONTENT_TYPE_JSON,
                }
            )

        if self.creds["authtype"] == "token":
            self.token: str = self.creds["token"]
            self.r = requests.Session()
            self.r.headers.update({"Authorization": f"Token {self.token}"})
            self.r.headers.update({"Content-Type": _CONTENT_TYPE_JSON})

    def _request(
        self,
        url: str,
        method: str,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """Execute the request.

        Redirects are followed, except a 301, 302 or 303 that requests
        would follow by resending a write as a GET, or without its body:
        the reply to that would come back as the write's.

        Raises:
            RedirectRefusedError: On such a redirect, before it is followed.
        """
        # Encode string data as UTF-8 to handle Unicode characters
        if isinstance(data, str):
            data = data.encode("utf-8")

        # requests runs per-request response hooks instead of the session's,
        # so pass the session's first: they still see every response, the
        # refused redirect included.
        session_hooks: list[Any] = self.r.hooks["response"]
        resp: requests.Response = self.r.request(
            method,
            self.endpoint + url,
            data=data,
            timeout=timeout,
            hooks={"response": [*session_hooks, _refuse_redirect_losing_request]},
        )

        # Some massaging to make our gerrit python code work
        if resp.status_code == 409:
            return resp

        if resp.text:
            try:
                body: ApiBody
                if _CONTENT_TYPE_JSON in resp.headers.get("Content-Type", ""):
                    remove_xssi_magic: str = resp.text.replace(")]}'", "")
                    body = json.loads(remove_xssi_magic)  # pyright: ignore[reportAny]
                else:
                    body = resp.text
            except ValueError:
                body = None
        else:
            body = None
            return resp

        return resp, body

    def get(
        self,
        url: str,
        *,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """HTTP GET request."""
        return self._request(url, "GET", data=data, timeout=timeout)

    def patch(
        self,
        url: str,
        *,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """HTTP PATCH request."""
        return self._request(url, "PATCH", data=data, timeout=timeout)

    def post(
        self,
        url: str,
        *,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """HTTP POST request."""
        return self._request(url, "POST", data=data, timeout=timeout)

    def put(
        self,
        url: str,
        *,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """HTTP PUT request."""
        return self._request(url, "PUT", data=data, timeout=timeout)

    def delete(
        self,
        url: str,
        *,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """HTTP DELETE request."""
        return self._request(url, "DELETE", data=data, timeout=timeout)
