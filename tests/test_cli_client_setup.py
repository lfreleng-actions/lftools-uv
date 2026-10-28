# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Tests for how the jenkins, nexus2 and nexus3 groups set up their clients."""

import configparser
import contextlib
import importlib
from unittest import mock

import multi_key_dict
import pytest
from click.testing import CliRunner as ClickRunner
from typer.testing import CliRunner as TyperRunner

import lftools_uv.cli
import lftools_uv.typer_apps.root
from lftools_uv.jenkins import Jenkins

click_token_module = importlib.import_module("lftools_uv.cli.jenkins.token")
typer_token_module = importlib.import_module("lftools_uv.typer_apps.jenkins.token")

FQDN = "nexus.example.org"

XFAIL_953 = pytest.mark.xfail(strict=True, reason="#953: group callbacks build their client eagerly")
XFAIL_952 = pytest.mark.xfail(strict=True, reason="#952: a missing jenkins_jobs.ini section is not reported")


def _no_section(section, _option=None):
    raise configparser.NoSectionError(section)


@pytest.fixture
def jjb_ini(tmp_path, monkeypatch):
    """Isolate configuration; return a jenkins_jobs.ini holding only ``[other]``."""
    monkeypatch.setenv("HOME", str(tmp_path))
    for name in (
        "JENKINS_URL",
        "JENKINS_USER",
        "JENKINS_PASSWORD",
        "JENKINS_JOBS_INI",
        "LFTOOLS_USERNAME",
        "LFTOOLS_PASSWORD",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("lftools_uv.config.get_setting", _no_section)

    ini = tmp_path / "jenkins_jobs.ini"
    ini.write_text("[other]\nurl = https://other.example.org\nuser = user\npassword = secret\n")
    return ini


def _click(args):
    return ClickRunner().invoke(lftools_uv.cli.cli, args, obj={})


def _typer(args):
    return TyperRunner().invoke(lftools_uv.typer_apps.root.app, args)


FRONT_ENDS = {"click": _click, "typer": _typer}


def _report(result, caplog):
    """Join everything a run reported: output, log and exception."""
    return f"{result.output}\n{caplog.text}\n{result.exception!r}"


HELP_ARGS = {
    "nexus2": ["nexus2", FQDN, "privilege", "--help"],
    "nexus3": ["nexus3", FQDN, "role", "--help"],
    "jenkins": ["jenkins", "-c", "{ini}", "quiet-down", "--help"],
    "nodes": ["jenkins", "-c", "{ini}", "nodes", "list", "--help"],
    "plugins": ["jenkins", "-c", "{ini}", "plugins", "list", "--help"],
}


def _help_args(name, ini):
    return [arg.format(ini=ini) for arg in HELP_ARGS[name]]


@XFAIL_953
@pytest.mark.parametrize("name", HELP_ARGS)
def test_click_subcommand_help_needs_no_client(name, jjb_ini):
    """Legacy ``--help`` works without configuration or a server."""
    result = _click(_help_args(name, jjb_ini))

    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


@pytest.mark.parametrize("name", HELP_ARGS)
def test_typer_subcommand_help_needs_no_client(name, jjb_ini):
    """Default CLI ``--help`` works without configuration or a server."""
    result = _typer(_help_args(name, jjb_ini))

    assert result.exit_code == 0, result.output
    assert "Usage:" in result.output


@XFAIL_953
@pytest.mark.usefixtures("jjb_ini")
def test_typer_nexus2_reports_configuration_error(caplog):
    """A Nexus2 client that cannot be built reports why, not a KeyError."""
    result = _typer(["nexus2", FQDN, "privilege", "list"])
    report = _report(result, caplog)

    assert result.exit_code == 1
    assert FQDN in report
    assert "KeyError" not in report


@XFAIL_953
@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_token_reset_needs_no_server_section(front_end, jjb_ini):
    """``token reset`` only needs the file, not a section for ``--server``."""
    jjb_ini.write_text("[srv1]\nurl = https://jenkins1.example.org\nuser = user\npassword = old\n")
    if front_end == "click":
        args = ["--username", "u", "--password", "p", "jenkins", "-c", str(jjb_ini), "token", "reset"]
    else:
        args = ["jenkins", "-u", "u", "-p", "p", "-c", str(jjb_ini), "token", "reset"]

    with contextlib.ExitStack() as stack:
        for module in (click_token_module, typer_token_module):
            stack.enter_context(mock.patch.object(module, "get_token", return_value="new-token"))
        result = FRONT_ENDS[front_end](args)

    assert result.exit_code == 0, result.output
    assert "new-token" in jjb_ini.read_text()


def _lazy_client_class():
    return importlib.import_module("lftools_uv.cli.state").LazyClient


@XFAIL_953
def test_lazy_client_known_attribute_skips_factory():
    """A known attribute is answered without building the client."""
    factory = mock.Mock()
    client = _lazy_client_class()(factory, config_file="/tmp/jenkins_jobs.ini")

    assert client.config_file == "/tmp/jenkins_jobs.ini"
    factory.assert_not_called()


@XFAIL_953
def test_lazy_client_builds_once():
    """The first other attribute builds the client; later ones reuse it."""
    factory = mock.Mock()
    client = _lazy_client_class()(factory)

    first = client.server
    second = client.url

    factory.assert_called_once_with()
    assert first is factory.return_value.server
    assert second is factory.return_value.url


@XFAIL_953
def test_lazy_client_dunder_does_not_build():
    """A dunder lookup raises AttributeError without building the client."""
    factory = mock.Mock()
    client = _lazy_client_class()(factory)

    dunder = "__deepcopy__"
    with pytest.raises(AttributeError):
        getattr(client, dunder)
    factory.assert_not_called()


@XFAIL_952
def test_jenkins_missing_section_raises(jjb_ini):
    """A missing jenkins_jobs.ini section raises a ValueError naming it."""
    with pytest.raises(ValueError, match=r"\[jenkins\] section not found"):
        Jenkins("jenkins", config_file=str(jjb_ini))


@XFAIL_952
@pytest.mark.parametrize("front_end", FRONT_ENDS)
def test_get_credentials_reports_missing_section(front_end, jjb_ini, caplog):
    """A command run against a missing section reports the section."""
    result = FRONT_ENDS[front_end](["jenkins", "-c", str(jjb_ini), "get-credentials"])
    report = _report(result, caplog)

    assert result.exit_code != 0
    assert "section not found" in report
    assert "NoneType" not in report


@pytest.mark.usefixtures("jjb_ini")
def test_click_nodes_list_prints_nodes():
    """Legacy ``nodes list`` still queries the server and prints the nodes."""
    with mock.patch("lftools_uv.cli.jenkins.Jenkins") as jenkins_cls:
        jenkins_cls.return_value.server.get_nodes.return_value = [
            {"name": "builder-1", "offline": False},
            {"name": "builder-2", "offline": True},
        ]
        result = _click(["jenkins", "-s", "https://jenkins.example.org", "nodes", "list"])

    assert result.exit_code == 0, result.output
    assert "builder-1 [Online]" in result.output
    assert "builder-2 [Offline]" in result.output
    jenkins_cls.return_value.server.get_nodes.assert_called_once_with()


@pytest.mark.usefixtures("jjb_ini")
def test_click_plugins_list_prints_plugins():
    """Legacy ``plugins list`` still queries the server and prints the plugins."""
    plugins = multi_key_dict.multi_key_dict()
    plugins["git", "Git plugin"] = {"shortName": "git", "longName": "Git plugin", "version": "5.0"}
    with mock.patch("lftools_uv.cli.jenkins.Jenkins") as jenkins_cls:
        jenkins_cls.return_value.server.get_plugins.return_value = plugins
        result = _click(["jenkins", "-s", "https://jenkins.example.org", "plugins", "list"])

    assert result.exit_code == 0, result.output
    assert "Git plugin:5.0" in result.output
    jenkins_cls.return_value.server.get_plugins.assert_called_once_with()
