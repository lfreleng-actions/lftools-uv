# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2018 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Test nexus command."""

import json
import os
import re

import pytest
import requests

from lftools_uv import cli
from lftools_uv.nexus import Nexus, cmd, util

FIXTURE_DIR = os.path.join(os.path.dirname(os.path.realpath(__file__)), "fixtures")


@pytest.fixture
def mock_get_credentials(mocker):
    rtn = {"nexus": "http://nexus.localhost", "user": "user", "password": "password"}
    mocker.patch("lftools_uv.nexus.cmd.get_credentials", return_value=rtn)
    mocker.patch("time.sleep", return_value=True)


@pytest.fixture
def nexus2_obj_create(responses):
    """Create the proper responses for the init of a nexus object"""
    baseurl_endpoint = re.compile(".*nexus.*/service/local/repo_targets")
    responses.add(responses.GET, baseurl_endpoint, status=200)


@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_create_roles(datafiles, responses, nexus2_obj_create):
    """Test create_roles() method with good config."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local/"
    roles_url = baseurl + "roles"
    privs_url = baseurl + "privileges"
    role1_return = """{"data": {"id": "lf-deployment"}}"""
    role2_return = """{"data": {"id": "LF Deployment By Name"}}"""

    for _ in range(4):  # Add response for each expected "get_role" call
        with open("simplified_roles_list.json") as roles_return:
            responses.add(responses.GET, roles_url, roles_return.read())
    for _ in range(2):  # Add response for each expected "get_priv" call
        with open("simplified_privs_list.json") as privs_return:
            responses.add(responses.GET, privs_url, privs_return.read())
    responses.add(responses.POST, roles_url, role1_return, status=201)
    responses.add(responses.POST, roles_url, role2_return, status=201)

    cmd.create_roles("role_config-good.yaml", "settings.yaml")


@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_release_staging_repos(datafiles, responses, mocker, nexus2_obj_create, mock_get_credentials):
    """Test create_roles() method with good config."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local"
    repos = ["test-release-repo"]
    activity_url = f"{baseurl}/staging/repository/{repos[0]}/activity"
    request_url = f"{baseurl}/staging/bulk/promote"

    closed_return = open("staging_activities_closed.xml").read()
    releasing_return = open("staging_activities_releasing.xml").read()
    released_return = open("staging_activities_released.xml").read()

    mocker.patch.object(cmd, "sleep")

    responses.add(responses.GET, activity_url, closed_return, status=200)
    responses.add(responses.POST, request_url, status=201)
    # While checking for the "release" activity, we return once without it in
    # order to exercise the code for "if not released".
    responses.add(responses.GET, activity_url, releasing_return, status=200)
    responses.add(responses.GET, activity_url, released_return, status=200)

    cmd.release_staging_repos(tuple(repos), False)


@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_release_staging_repos_skips_released(datafiles, responses, mocker, nexus2_obj_create, mock_get_credentials):
    """A released repository is skipped and the rest are still promoted."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local"
    request_url = f"{baseurl}/staging/bulk/promote"
    released_return = open("staging_activities_released.xml").read()
    closed_return = open("staging_activities_closed.xml").read()

    mocker.patch.object(cmd, "sleep")

    responses.add(responses.GET, f"{baseurl}/staging/repository/A/activity", released_return, status=200)
    responses.add(responses.GET, f"{baseurl}/staging/repository/B/activity", closed_return, status=200)
    responses.add(responses.POST, request_url, status=201)
    responses.add(responses.GET, f"{baseurl}/staging/repository/B/activity", released_return, status=200)

    cmd.release_staging_repos(("A", "B"), False)

    promotes = [call.request for call in responses.calls if call.request.url == request_url]
    assert len(promotes) == 1
    assert json.loads(promotes[0].body) == {"data": {"stagedRepositoryIds": ["B"]}}


@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_release_staging_repos_all_released(datafiles, responses, mocker, nexus2_obj_create, mock_get_credentials):
    """With every repository already released, nothing is promoted."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local"
    released_return = open("staging_activities_released.xml").read()

    mocker.patch.object(cmd, "sleep")

    responses.add(responses.GET, f"{baseurl}/staging/repository/A/activity", released_return, status=200)
    responses.add(responses.GET, f"{baseurl}/staging/repository/B/activity", released_return, status=200)

    cmd.release_staging_repos(("A", "B"), False)

    assert not [call for call in responses.calls if call.request.method == "POST"]


def test_release_cli_requires_repos(cli_runner, mocker):
    """``nexus release`` with no repository IDs is a usage error."""
    release = mocker.patch("lftools_uv.nexus.cmd.release_staging_repos")
    result = cli_runner.invoke(cli.cli, ["nexus", "release", "-s", "https://nexus.example.org"], obj={})
    assert result.exit_code == 2
    release.assert_not_called()


@pytest.mark.xfail(strict=True, reason="#845: nexus release waits for ever")
@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_release_staging_repos_gives_up(datafiles, responses, mocker, nexus2_obj_create, mock_get_credentials):
    """A release Nexus never finishes raises ``TimeoutError`` after ``max_wait``."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local"
    activity_url = f"{baseurl}/staging/repository/A/activity"
    responses.assert_all_requests_are_fired = False

    sleep = mocker.patch.object(cmd, "sleep")

    responses.add(responses.GET, activity_url, open("staging_activities_closed.xml").read(), status=200)
    responses.add(responses.POST, f"{baseurl}/staging/bulk/promote", status=201)
    responses.add(responses.GET, activity_url, open("staging_activities_releasing.xml").read(), status=200)

    with pytest.raises(TimeoutError, match="A"):
        cmd.release_staging_repos(("A",), False, max_wait=1)  # type: ignore[call-arg]
    assert sleep.call_count <= 5


@pytest.mark.xfail(strict=True, reason="#845: nexus release requests have no timeout")
@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_release_staging_repos_requests_time_out(datafiles, responses, mocker, nexus2_obj_create, mock_get_credentials):
    """Every staging request made during a release carries a timeout."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local"
    activity_url = f"{baseurl}/staging/repository/A/activity"

    mocker.patch.object(cmd, "sleep")
    get = mocker.patch.object(cmd.requests, "get", wraps=requests.get)
    post = mocker.patch.object(cmd.requests, "post", wraps=requests.post)

    responses.add(responses.GET, activity_url, open("staging_activities_closed.xml").read(), status=200)
    responses.add(responses.POST, f"{baseurl}/staging/bulk/promote", status=201)
    responses.add(responses.GET, activity_url, open("staging_activities_released.xml").read(), status=200)

    cmd.release_staging_repos(("A",), False)

    staging_calls = [call for call in get.call_args_list + post.call_args_list if "/staging/" in call.args[0]]
    assert len(staging_calls) == 3
    assert all(call.kwargs.get("timeout") for call in staging_calls)


@pytest.mark.xfail(strict=True, reason="#845: a slow poll ends the release wait")
@pytest.mark.datafiles(os.path.join(FIXTURE_DIR, "nexus"))
def test_release_staging_repos_retries_slow_poll(datafiles, responses, mocker, nexus2_obj_create, mock_get_credentials):
    """A poll that times out is retried like a connection error."""
    os.chdir(str(datafiles))
    baseurl = "http://nexus.localhost/service/local"
    activity_url = f"{baseurl}/staging/repository/A/activity"
    responses.assert_all_requests_are_fired = False

    mocker.patch.object(cmd, "sleep")

    responses.add(responses.GET, activity_url, open("staging_activities_closed.xml").read(), status=200)
    responses.add(responses.POST, f"{baseurl}/staging/bulk/promote", status=201)
    responses.add(responses.GET, activity_url, body=requests.exceptions.ReadTimeout("slow"))
    responses.add(responses.GET, activity_url, open("staging_activities_released.xml").read(), status=200)

    cmd.release_staging_repos(("A",), False)

    assert len([call for call in responses.calls if call.request.url == activity_url]) == 3


@pytest.mark.xfail(strict=True, reason="#845: nexus release has no --max-wait option")
def test_release_cli_passes_max_wait(cli_runner, mocker):
    """``nexus release --max-wait`` passes the limit on."""
    release = mocker.patch("lftools_uv.nexus.cmd.release_staging_repos")
    result = cli_runner.invoke(
        cli.cli, ["nexus", "release", "-s", "https://nexus.example.org", "--max-wait", "5", "A"], obj={}
    )
    assert result.exit_code == 0
    assert release.call_args.kwargs["max_wait"] == 5


def _http_response(status, body=None):
    """Build a ``requests.Response`` with the given status and JSON body."""
    resp = requests.Response()
    resp.status_code = status
    resp.url = "https://nexus.example.org/"
    resp._content = json.dumps(body).encode("utf-8") if body is not None else b""
    return resp


@pytest.fixture
def repo_group_nexus(mocker):
    """A legacy ``Nexus`` whose ``requests`` calls are mocked."""
    mock_requests = mocker.patch("lftools_uv.nexus.requests")
    mock_requests.get.return_value = _http_response(200)
    nexus = Nexus("https://nexus.example.org", "user", "password")
    mock_requests.reset_mock()
    return nexus, mock_requests


def test_update_repo_group_details_raises_on_error(repo_group_nexus):
    """A rejected repo group update raises ``HTTPError``."""
    nexus, mock_requests = repo_group_nexus
    mock_requests.put.return_value = _http_response(500, {"errors": ["boom"]})
    with pytest.raises(requests.HTTPError):
        nexus.update_repo_group_details("staging", {"repositories": []})


@pytest.mark.parametrize(
    "call",
    [
        lambda nexus: nexus.get_repo_group("Staging Repositories"),
        lambda nexus: nexus.get_repo_group_details("staging"),
    ],
    ids=["get_repo_group", "get_repo_group_details"],
)
def test_repo_group_get_raises_on_error(repo_group_nexus, call):
    """A failed repo group lookup raises ``HTTPError``."""
    nexus, mock_requests = repo_group_nexus
    mock_requests.get.return_value = _http_response(500, {"data": [{"name": "Staging Repositories", "id": "s"}]})
    with pytest.raises(requests.HTTPError):
        call(nexus)


def test_repo_group_success(repo_group_nexus):
    """Successful repo group calls return their data."""
    nexus, mock_requests = repo_group_nexus
    mock_requests.get.side_effect = [
        _http_response(200, {"data": [{"name": "Staging Repositories", "id": "staging"}]}),
        _http_response(200, {"data": {"repositories": []}}),
    ]
    mock_requests.put.return_value = _http_response(200)

    assert nexus.get_repo_group("Staging Repositories") == "staging"
    assert nexus.get_repo_group_details("staging") == {"repositories": []}
    nexus.update_repo_group_details("staging", {"repositories": []})
    mock_requests.put.assert_called_once()


def test_create_repo_target_regex():
    """Test create_repo_target_regex() command."""

    test_url_3_par = [
        [False, "org.o-ran-sc.org", "/org/o/ran/sc/org/"],
        [
            False,
            "org.opendaylight.odlparent",
            "/org/opendaylight/odlparent/odlparent/4.0.0-SNAPSHOT/odlparent-4.0.0-20180424.132124-69.pom",
        ],
        [
            False,
            "org.opendaylight.honeycomb.vbd",
            "/org/opendaylight/honeycomb/vbd/odl-vbd/1.4.0-SNAPSHOT/odl-vbd-1.4.0-20180422.024456-12-features.xml",
        ],
        [False, "org.openecomp.mso", "/org/openecomp/mso/1.1.0-SNAPSHOT/mso-1.1.0-20170606.171056-26.pom"],
        [False, "org.onap.dcaegen2", "/org/onap.dcaegen2/1.2.0-SNAPSHOT/dcaegen2-1.2.0-20180403.182529-10.pom"],
        [False, "io.fd.vpp", "/io/fd/vpp/jvpp/16.06/jvpp-16.06.jar"],
        [True, "org.o-ran-sc.org", "/org/o-ran-sc/org/"],
        [True, "org.o-ran-sc.org", "/org/o-ran-sc/org/ric-plt-lib-rmr"],
        [
            True,
            "org.opendaylight.odlparent",
            "/org/opendaylight/odlparent/odlparent/4.0.0-SNAPSHOT/odlparent-4.0.0-20180424.132124-69.pom",
        ],
        [
            True,
            "org.opendaylight.honeycomb.vbd",
            "/org/opendaylight/honeycomb/vbd/odl-vbd/1.4.0-SNAPSHOT/odl-vbd-1.4.0-20180422.024456-12-features.xml",
        ],
        [True, "org.openecomp.mso", "/org/openecomp/mso/1.1.0-SNAPSHOT/mso-1.1.0-20170606.171056-26.pom"],
        [True, "org.onap.dcaegen2", "/org/onap/dcaegen2/1.2.0-SNAPSHOT/dcaegen2-1.2.0-20180403.182529-10.pom"],
        [True, "io.fd.vpp", "/io/fd/vpp/jvpp/16.06/jvpp-16.06.jar"],
    ]

    for url in test_url_3_par:
        strict = bool(url[0])
        group_id = str(url[1])
        match_term = str(url[2])
        a = util.create_repo_target_regex(group_id, strict)
        a_regex = re.compile(a)
        assert a_regex.match(match_term) is not None

    test_url_2_par = [
        ["org.o-ran-sc.org", "/org/o-ran-sc/org/"],
        [
            "org.opendaylight.odlparent",
            "/org/opendaylight/odlparent/odlparent/4.0.0-SNAPSHOT/odlparent-4.0.0-20180424.132124-69.pom",
        ],
        [
            "org.opendaylight.honeycomb.vbd",
            "/org/opendaylight/honeycomb/vbd/odl-vbd/1.4.0-SNAPSHOT/odl-vbd-1.4.0-20180422.024456-12-features.xml",
        ],
        ["org.openecomp.mso", "/org/openecomp/mso/1.1.0-SNAPSHOT/mso-1.1.0-20170606.171056-26.pom"],
        ["org.onap.dcaegen2", "/org/onap/dcaegen2/1.2.0-SNAPSHOT/dcaegen2-1.2.0-20180403.182529-10.pom"],
        ["io.fd.vpp", "/io/fd/vpp/jvpp/16.06/jvpp-16.06.jar"],
    ]

    for entry in test_url_2_par:
        a = util.create_repo_target_regex(entry[0])
        a_regex = re.compile(a)
        assert a_regex.match(entry[1]) is not None
