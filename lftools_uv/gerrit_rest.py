# SPDX-License-Identifier: EPL-1.0 AND MIT
# SPDX-FileCopyrightText: 2026 The Linux Foundation
# SPDX-FileCopyrightText: 2013 Sony Mobile Communications
#
# _decode_response, the URL handling and the retry policy below are
# adapted from pygerrit2 2.0.15 (pygerrit2/rest/__init__.py), which
# carries this notice:
#
# The MIT License
#
# Copyright 2013 Sony Mobile Communications. All rights reserved.
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in
# all copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.
"""Minimal Gerrit REST client built on requests.

It covers the GET requests lftools-uv makes to Gerrit: authenticated
requests go to Gerrit's ``/a/`` URLs, credentials fall back to
``~/.netrc``, the ``)]}'`` prefix Gerrit puts before JSON is stripped,
error statuses raise ``requests.HTTPError``, requests time out after 10
seconds, and 500, 502 and 504 responses are retried, raising
``requests.HTTPError`` too once the retries run out.
"""

from __future__ import annotations

import json
from typing import Any

import requests
from requests.adapters import HTTPAdapter
from requests.auth import AuthBase, HTTPBasicAuth
from requests.utils import get_netrc_auth
from urllib3.util.retry import Retry

GERRIT_MAGIC_JSON_PREFIX = ")]}'\n"
GERRIT_AUTH_SUFFIX = "/a"
DEFAULT_HEADERS = {"Accept": "application/json", "Accept-Encoding": "gzip"}
DEFAULT_TIMEOUT = 10
RETRY_STATUSES = (500, 502, 504)


def _decode_response(response: requests.Response) -> Any:
    """Return the decoded JSON body, or its text when it is not JSON.

    Raises requests.HTTPError when the response carries an error status.
    """
    response.raise_for_status()
    content = response.content.strip().decode(response.encoding or "utf-8")
    if not content:
        return content
    if response.headers.get("content-type", "").split(";")[0] != "application/json":
        return content
    if content.startswith(GERRIT_MAGIC_JSON_PREFIX):
        content = content[len(GERRIT_MAGIC_JSON_PREFIX) :]
    return json.loads(content)


class GerritRestAPI:
    """Send GET requests to one Gerrit server's REST API.

    url is the server's base URL, including the scheme. Without auth the
    credentials ``~/.netrc`` holds for the host are used, if any. Whenever
    there are credentials the requests go to the ``/a/`` URLs.
    """

    def __init__(self, url: str, auth: AuthBase | None = None) -> None:
        """Set up the session, its retries and the base URL."""
        self.url = url.rstrip("/")
        self.session = requests.Session()
        # raise_on_status=False hands the last 5xx response back, so
        # _decode_response raises HTTPError rather than urllib3's RetryError.
        retry = Retry(
            total=5,
            read=5,
            connect=5,
            backoff_factor=0.3,
            status_forcelist=RETRY_STATUSES,
            raise_on_status=False,
        )
        adapter = HTTPAdapter(max_retries=retry)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        if auth is None:
            netrc_auth = get_netrc_auth(url)
            if netrc_auth:
                auth = HTTPBasicAuth(*netrc_auth)
        self.auth = auth

        if auth is not None:
            if not self.url.endswith(GERRIT_AUTH_SUFFIX):
                self.url += GERRIT_AUTH_SUFFIX
        elif self.url.endswith(GERRIT_AUTH_SUFFIX):
            self.url = self.url[: -len(GERRIT_AUTH_SUFFIX)]
        self.url += "/"

    def get(self, endpoint: str, headers: dict[str, str] | None = None) -> Any:
        """GET endpoint, relative to the base URL, and return the decoded body."""
        request_headers = {**DEFAULT_HEADERS, **(headers or {})}
        response = self.session.get(
            self.url + endpoint.lstrip("/"),
            auth=self.auth,
            headers=request_headers,
            timeout=DEFAULT_TIMEOUT,
        )
        return _decode_response(response)
