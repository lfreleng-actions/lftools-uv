# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2017 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""HTTP request helpers used to talk to Nexus."""

from __future__ import annotations

import errno
import os

import requests

from lftools_uv.deploy._common import log
from lftools_uv.deploy._late import _fail


def _request_post(url: str, data: str, headers: dict[str, str]) -> requests.Response:
    """Execute a request post, return the resp."""
    resp: requests.Response | None = None
    try:
        resp = requests.post(url, data=data, headers=headers, timeout=30)
    except requests.exceptions.MissingSchema as exc:
        log.debug("POST to %s failed with a missing URL scheme: %s", url, exc)
        _fail(f"Not valid URL: {url}")
    except requests.exceptions.ConnectionError as exc:
        log.debug("POST to %s could not connect: %s", url, exc)
        _fail(f"Could not connect to URL: {url}")
    except requests.exceptions.InvalidURL as exc:
        log.debug("POST to %s used an invalid URL: %s", url, exc)
        _fail(f"Invalid URL: {url}")
    assert resp is not None  # noqa: S101
    return resp


def _request_post_file(
    url: str,
    file_to_upload: str,
    parameters: dict[str, tuple[None, str]] | None = None,
) -> requests.Response:
    """Execute a request post, return the resp."""
    resp: requests.Response | None = None
    try:
        upload_file = open(file_to_upload, "rb")  # noqa: PTH123, SIM115
    except FileNotFoundError as err:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_to_upload) from err

    files: dict[str, object] = {"file": upload_file}
    try:
        if parameters:
            resp = requests.post(url, data=parameters, files=files, timeout=30)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        else:
            resp = requests.post(url, data=upload_file.read(), timeout=30)
    except requests.exceptions.MissingSchema as err:
        raise requests.HTTPError(f"Not valid URL: {url}") from err
    except requests.exceptions.ConnectionError as err:
        raise requests.HTTPError(f"Could not connect to URL: {url}") from err
    except requests.exceptions.InvalidURL as err:
        raise requests.HTTPError(f"Invalid URL: {url}") from err

    if resp.status_code == 400:
        raise requests.HTTPError("Repository is read only")
    elif resp.status_code == 404:
        raise requests.HTTPError("Did not find repository.")

    assert resp is not None  # noqa: S101
    if not str(resp.status_code).startswith("20"):
        raise requests.HTTPError(
            f"Failed to upload to Nexus with status code: {resp.status_code}.\n{resp.text}\n{file_to_upload}"
        )

    return resp


def _request_put_file(
    url: str,
    file_to_upload: str,
    parameters: dict[str, object] | None = None,
) -> None:
    """Execute a request put.

    Returns nothing on success. Raises ``requests.HTTPError`` (or
    ``FileNotFoundError`` if the local file is missing) on failure.
    """
    resp: requests.Response | None = None
    try:
        upload_file = open(file_to_upload, "rb")  # noqa: PTH123, SIM115
    except FileNotFoundError as err:
        raise FileNotFoundError(errno.ENOENT, os.strerror(errno.ENOENT), file_to_upload) from err

    files: dict[str, object] = {"file": upload_file}
    try:
        if parameters:
            resp = requests.put(url, data=parameters, files=files, timeout=30)  # type: ignore[arg-type]  # pyright: ignore[reportArgumentType]
        else:
            resp = requests.put(url, data=upload_file, timeout=30)
    except requests.exceptions.MissingSchema as err:
        raise requests.HTTPError(f"Not valid URL format. Check for https:// etc..: {url}") from err
    except requests.exceptions.ConnectTimeout as err:
        raise requests.HTTPError(f"Timed out connecting to {url}") from err
    except requests.exceptions.ReadTimeout as err:
        raise requests.HTTPError(f"Timed out waiting for the server to reply ({url})") from err
    except requests.exceptions.ConnectionError as err:
        raise requests.HTTPError(f"A connection error occurred ({url})") from err
    except requests.exceptions.InvalidURL as err:
        raise requests.HTTPError(f"Invalid URL format: {url}") from err
    except requests.RequestException as err:
        # Caller (deploy_nexus) logs the wrapped HTTPError once; avoid
        # duplicate logging here. The original exception is preserved as
        # the cause via 'raise ... from err' for diagnostics.
        raise requests.HTTPError(f"Request error during PUT to {url}: {err}") from err

    assert resp is not None  # noqa: S101
    if resp.status_code == 400:
        raise requests.HTTPError("Repository is read only")
    if resp.status_code == 401:
        raise requests.HTTPError("Invalid repository credentials")
    if resp.status_code == 404:
        raise requests.HTTPError("Did not find repository.")

    if not str(resp.status_code).startswith("20"):
        raise requests.HTTPError(
            f"Failed to upload to Nexus with status code: {resp.status_code}.\n{resp.text}\n{file_to_upload}"
        )
