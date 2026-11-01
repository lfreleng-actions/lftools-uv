# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for how the shared REST client follows redirects.

requests follows a 302 or 303, or a 301 answering a POST, by resending
the request as a GET without its body; a 301 answering any other method
keeps the method but drops the body. A write redirected either way never
reaches the new location, yet the reply to what was resent comes back as
the write's. The client must refuse such a redirect, before following it,
and still follow every other: GET and HEAD, a write without a body behind
a 301, and 307 and 308, which keep the method and body.

``responses`` answers every request, so no test reaches a server.
"""

import pytest
import requests
import responses

import lftools_uv.api.client as client

ORIGIN = "https://api.example.org/v3/projects/foo/"
TARGET = "https://api.example.org/moved/v3/projects/foo/"
BODY = '{"default_branch": "release"}'
WRITES = pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE"])


def _api() -> client.RestApi:
    return client.RestApi(creds={"authtype": "token", "endpoint": "", "token": "xyz"})


def _send(method: str, body: str | None = BODY) -> client.ApiResponse:
    api = _api()
    writes = {"POST": api.post, "PUT": api.put, "PATCH": api.patch, "DELETE": api.delete}
    return writes[method](ORIGIN, data=body)


def _serve_redirect(method: str, status: int, location: str = TARGET) -> None:
    """Redirect *method* at ORIGIN to *location*; answer anything resent there with 200."""
    responses.add(method, ORIGIN, status=status, headers={"Location": location})
    for resent in {"GET", method}:
        responses.add(resent, TARGET, json={"slug": "foo"}, status=200)


@WRITES
@pytest.mark.parametrize("status", [301, 302, 303])
@responses.activate
def test_write_redirect_losing_body_is_refused(method: str, status: int) -> None:
    _serve_redirect(method, status)

    with pytest.raises(requests.RequestException) as raised:
        _send(method)

    assert type(raised.value).__name__ == "RedirectRefusedError"
    assert all(part in str(raised.value) for part in (method, ORIGIN, TARGET, f"HTTP {status}"))
    assert raised.value.response is not None
    assert raised.value.response.status_code == status
    assert [call.request.url for call in responses.calls] == [ORIGIN]


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
@pytest.mark.parametrize("status", [302, 303])
@responses.activate
def test_bodyless_write_turned_into_get_is_refused(method: str, status: int) -> None:
    _serve_redirect(method, status)

    with pytest.raises(requests.RequestException):
        _send(method, body=None)

    assert [call.request.url for call in responses.calls] == [ORIGIN]


@responses.activate
def test_bodyless_post_behind_301_is_refused() -> None:
    """A 301 turns a POST into a GET, body or not."""
    _serve_redirect("POST", 301)

    with pytest.raises(requests.RequestException):
        _send("POST", body=None)

    assert [call.request.url for call in responses.calls] == [ORIGIN]


@responses.activate
def test_relative_location_is_named_in_full() -> None:
    _serve_redirect("PATCH", 302, location="/moved/v3/projects/foo/")

    with pytest.raises(requests.RequestException, match="https://api.example.org/moved/v3/projects/foo/"):
        _send("PATCH")


@pytest.mark.parametrize(
    ("origin", "location", "secrets"),
    [
        ("https://user:s3cret@api.example.org/v3/x/", TARGET, ["user", "s3cret"]),
        (ORIGIN, "https://api.example.org/moved/?token=T0KEN&sig=S1G#frag", ["T0KEN", "S1G", "frag"]),
    ],
    ids=["userinfo", "query-and-fragment"],
)
@responses.activate
def test_refusal_keeps_url_secrets_out_of_message(origin: str, location: str, secrets: list[str]) -> None:
    """Credentials in either URL never reach the error message, but the hosts and paths do."""
    responses.add(responses.POST, origin, status=302, headers={"Location": location})

    with pytest.raises(requests.RequestException) as raised:
        _api().post(origin, data=BODY)

    message = str(raised.value)
    assert not [secret for secret in secrets if secret in message]
    assert "https://api.example.org/" in message


@responses.activate
def test_session_response_hooks_still_run() -> None:
    """The refusal sits beside hooks registered on the session, never in place of them."""
    responses.add(responses.GET, ORIGIN, json={"slug": "foo"}, status=200)
    _serve_redirect("PATCH", 302)
    seen: list[int] = []
    api = _api()
    api.r.hooks["response"].append(lambda response, *args, **kwargs: seen.append(response.status_code))

    _ = api.get(ORIGIN)
    with pytest.raises(requests.RequestException):
        _ = api.patch(ORIGIN, data=BODY)

    assert seen == [200, 302]


@pytest.mark.parametrize("location", ["https://api.example.org:70000/moved/", "https://[api.example.org/moved/"])
@responses.activate
def test_malformed_location_is_still_refused(location: str) -> None:
    """A target that cannot be parsed still raises the refusal, so request-error handlers catch it."""
    responses.add(responses.POST, ORIGIN, status=302, headers={"Location": location})

    with pytest.raises(requests.RequestException) as raised:
        _api().post(ORIGIN, data=BODY)

    assert type(raised.value).__name__ == "RedirectRefusedError"
    assert ORIGIN in str(raised.value)
    assert [call.request.url for call in responses.calls] == [ORIGIN]


@responses.activate
def test_refused_response_is_closed() -> None:
    """The refused redirect's response is read and closed, releasing its connection."""
    responses.add(responses.POST, ORIGIN, status=302, headers={"Location": TARGET}, body="moved")

    with pytest.raises(requests.RequestException) as raised:
        _api().post(ORIGIN, data=BODY)

    response = raised.value.response
    assert response is not None
    assert response.raw.closed
    assert response.content == b"moved"


@pytest.mark.parametrize(
    "failure",
    [requests.exceptions.ChunkedEncodingError("connection broken"), RuntimeError("content already consumed")],
    ids=["request-error", "runtime-error"],
)
@responses.activate
def test_refusal_survives_failed_body_read(failure: Exception, monkeypatch: pytest.MonkeyPatch) -> None:
    """A refused response whose body fails to read is still refused, and still closed."""
    responses.add(responses.POST, ORIGIN, status=302, headers={"Location": TARGET}, body="moved")

    def fail(*_args: object, **_kwargs: object) -> None:
        raise failure

    monkeypatch.setattr(requests.Response, "iter_content", fail)

    with pytest.raises(requests.RequestException) as raised:
        _api().post(ORIGIN, data=BODY)

    assert type(raised.value).__name__ == "RedirectRefusedError"
    response = raised.value.response
    assert response is not None
    assert response.raw.closed
    assert [call.request.url for call in responses.calls] == [ORIGIN]


@pytest.mark.parametrize("method", ["PUT", "PATCH", "DELETE"])
@responses.activate
def test_bodyless_write_behind_301_is_followed(method: str) -> None:
    """A 301 keeps every method but POST, so a write without a body loses nothing."""
    _serve_redirect(method, 301)

    response = _send(method, body=None)

    assert isinstance(response, tuple)
    assert [(call.request.method, call.request.url) for call in responses.calls] == [(method, ORIGIN), (method, TARGET)]


@WRITES
@pytest.mark.parametrize("status", [307, 308])
@responses.activate
def test_write_redirect_keeping_body_is_followed(method: str, status: int) -> None:
    _serve_redirect(method, status)

    response = _send(method)

    assert isinstance(response, tuple)
    assert response[1] == {"slug": "foo"}
    assert [(call.request.method, call.request.url) for call in responses.calls] == [(method, ORIGIN), (method, TARGET)]
    assert responses.calls[1].request.body == BODY.encode()


@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
@responses.activate
def test_get_redirect_is_followed(status: int) -> None:
    _serve_redirect("GET", status)

    response = _api().get(ORIGIN)

    assert isinstance(response, tuple)
    assert response[1] == {"slug": "foo"}
    assert [call.request.url for call in responses.calls] == [ORIGIN, TARGET]
