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

import json

import requests

# Type alias for parsed JSON response body.
# REST APIs return heterogeneous JSON; Any is unavoidable at
# this deserialization boundary.  Callers should narrow as needed.
ApiBody = dict[str, object] | list[object] | str | None

# Full API response: plain Response on certain status codes,
# or a (Response, body) tuple when a body was parsed.
ApiResponse = requests.Response | tuple[requests.Response, ApiBody]


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
                    "Accept": "application/json",
                }
            )

        if self.creds["authtype"] == "token":
            self.token: str = self.creds["token"]
            self.r = requests.Session()
            self.r.headers.update({"Authorization": f"Token {self.token}"})
            self.r.headers.update({"Content-Type": "application/json"})

    def _request(
        self,
        url: str,
        method: str,
        data: str | bytes | None = None,
        timeout: int = 30,
    ) -> ApiResponse:
        """Execute the request."""
        # Encode string data as UTF-8 to handle Unicode characters
        if isinstance(data, str):
            data = data.encode("utf-8")

        resp: requests.Response = self.r.request(method, self.endpoint + url, data=data, timeout=timeout)

        # Some massaging to make our gerrit python code work
        if resp.status_code == 409:
            return resp

        if resp.text:
            try:
                body: ApiBody
                if "application/json" in resp.headers["Content-Type"]:
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
