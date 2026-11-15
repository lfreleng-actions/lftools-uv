# SPDX-License-Identifier: EPL-1.0
# SPDX-FileCopyrightText: 2026 The Linux Foundation
"""Credential validation for the Nexus provisioning commands.

Every test here runs offline: the Nexus client is replaced with a mock, so
a test that reached it would record the call rather than contact a server.
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Any

import pytest
import yaml

from lftools_uv.nexus import cmd

EXAMPLE_DIR = Path(__file__).resolve().parent.parent / "etc" / "nexus"

# Recognisable sentinel values, so a test can prove none leaks into a log.
ADMIN_SECRET = "admin-sentinel-value"
FOO_SECRET = "foo-sentinel-value"
BAR_SECRET = "bar-sentinel-value"
BAZ_SECRET = "baz-sentinel-value"

UNUSABLE_PASSWORDS = [
    pytest.param("", id="empty"),
    pytest.param("   ", id="blank"),
    pytest.param(None, id="null"),
    pytest.param("${NEXUS_PASSWORD}", id="braced-placeholder"),
    pytest.param("$NEXUS_PASSWORD", id="bare-placeholder"),
    pytest.param("<admin password>", id="angle-placeholder"),
    pytest.param("deploy-${NEXUS_PASSWORD}", id="composed-placeholder"),
    pytest.param("${NEXUS_PASSWORD}-${NEXUS_TOKEN}", id="two-placeholders"),
    pytest.param("${}", id="empty-braced-placeholder"),
    pytest.param(False, id="boolean"),
    pytest.param(12345, id="number"),
    pytest.param([], id="list"),
    pytest.param({}, id="mapping"),
]


@pytest.fixture
def nexus_client(mocker):
    """Replace the Nexus client so no test can reach a server."""
    client = mocker.patch.object(cmd, "Nexus")
    instance = client.return_value
    instance.get_target.side_effect = LookupError
    instance.get_priv.side_effect = LookupError
    instance.get_role.side_effect = LookupError
    instance.get_user.side_effect = LookupError
    return client


def _write(path: Path, data: dict[str, Any]) -> str:
    path.write_text(yaml.safe_dump(data))
    return str(path)


def _settings(tmp_path: Path, password: Any = ADMIN_SECRET) -> str:
    return _write(
        tmp_path / "settings.yaml",
        {"nexus": "https://nexus.example.org", "user": "admin", "password": password, "email_domain": "example.org"},
    )


def _repo_config(tmp_path: Path, baz_password: Any = BAZ_SECRET) -> str:
    return _write(
        tmp_path / "repo-config.yaml",
        {
            "base_groupId": "org.example",
            "email_domain": "example.org",
            "repositories": {
                "foo": {
                    "password": FOO_SECRET,
                    "repositories": {
                        "bar": {
                            "password": BAR_SECRET,
                            "repositories": {"baz": {"password": baz_password}},
                        }
                    },
                }
            },
        },
    )


def _assert_no_secret_logged(caplog: pytest.LogCaptureFixture, value: Any) -> None:
    if isinstance(value, str) and value.strip():
        assert value not in caplog.text


def test_create_repos_rejects_shipped_examples(tmp_path, nexus_client, caplog):
    """The shipped examples must not provision anything as they stand."""
    shutil.copy(EXAMPLE_DIR / "settings.example.yaml", tmp_path / "settings.yaml")
    repo_config = yaml.safe_load((EXAMPLE_DIR / "repo-config.example.yaml").read_text())
    repo_config.setdefault("email_domain", "example.org")
    config_file = _write(tmp_path / "repo-config.yaml", repo_config)

    with pytest.raises(SystemExit) as exc_info:
        cmd.create_repos(config_file, str(tmp_path / "settings.yaml"), "")

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()
    assert "password" in caplog.text


@pytest.mark.parametrize("password", UNUSABLE_PASSWORDS)
def test_create_repos_rejects_unusable_admin_password(tmp_path, nexus_client, caplog, password):
    """An unusable administrator password fails before the client exists."""
    caplog.set_level(logging.DEBUG)

    with pytest.raises(SystemExit) as exc_info:
        cmd.create_repos(_repo_config(tmp_path), _settings(tmp_path, password), "")

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()
    assert "password" in caplog.text
    _assert_no_secret_logged(caplog, password)


@pytest.mark.parametrize("password", UNUSABLE_PASSWORDS)
def test_create_repos_rejects_unusable_nested_password(tmp_path, nexus_client, caplog, password):
    """An unusable password on a grandchild stops the whole tree up front."""
    caplog.set_level(logging.DEBUG)

    with pytest.raises(SystemExit) as exc_info:
        cmd.create_repos(_repo_config(tmp_path, password), _settings(tmp_path), "")

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()
    assert "foo/bar/baz" in caplog.text
    for secret in (ADMIN_SECRET, FOO_SECRET, BAR_SECRET):
        assert secret not in caplog.text
    _assert_no_secret_logged(caplog, password)


def test_create_repos_rejects_missing_nested_password(tmp_path, nexus_client, caplog):
    """A repository without any password key is reported by its path."""
    config = yaml.safe_load(Path(_repo_config(tmp_path)).read_text())
    del config["repositories"]["foo"]["repositories"]["bar"]["password"]
    config_file = _write(tmp_path / "repo-config.yaml", config)

    with pytest.raises(SystemExit) as exc_info:
        cmd.create_repos(config_file, _settings(tmp_path), "")

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()
    assert "foo/bar" in caplog.text


def test_create_repos_rejects_unusable_ini_password(tmp_path, nexus_client, mocker):
    """Credentials read from lftools.ini get the same check as settings.yaml."""
    mocker.patch(
        "lftools_uv.config.get_setting", side_effect=lambda _section, option: "" if option == "password" else "admin"
    )

    with pytest.raises(SystemExit) as exc_info:
        cmd.create_repos(_repo_config(tmp_path), None, "https://nexus.example.org")

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()


@pytest.mark.parametrize("password", UNUSABLE_PASSWORDS)
def test_create_roles_rejects_unusable_admin_password(tmp_path, nexus_client, password):
    """Role creation needs a usable administrator password too."""
    role_config = _write(tmp_path / "role-config.yaml", {"lf-deployment": {"name": "LF", "roles": []}})

    with pytest.raises(SystemExit) as exc_info:
        cmd.create_roles(role_config, _settings(tmp_path, password))

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()


@pytest.mark.parametrize("password", UNUSABLE_PASSWORDS)
def test_reorder_staged_repos_rejects_unusable_admin_password(tmp_path, nexus_client, password):
    """Reordering the staging group needs a usable administrator password."""
    with pytest.raises(SystemExit) as exc_info:
        cmd.reorder_staged_repos(_settings(tmp_path, password))

    assert exc_info.value.code == 1
    nexus_client.assert_not_called()


def test_create_repos_provisions_valid_private_config(tmp_path, nexus_client):
    """A complete private configuration still provisions every repository."""
    cmd.create_repos(_repo_config(tmp_path), _settings(tmp_path), "")

    nexus_client.assert_called_once_with("https://nexus.example.org", "admin", ADMIN_SECRET)
    created = {call.args[0]: call.args[3] for call in nexus_client.return_value.create_user.call_args_list}
    assert created == {"foo": FOO_SECRET, "foo-bar": BAR_SECRET, "foo-bar-baz": BAZ_SECRET}


def test_create_repos_accepts_dollar_and_angle_characters(tmp_path, nexus_client):
    """Only a whole-value $VAR or <text> counts as a placeholder; ${VAR} counts anywhere."""
    password = "Fz$Q8k<x>2"
    config = yaml.safe_load(Path(_repo_config(tmp_path)).read_text())
    config["repositories"]["foo"]["repositories"]["bar"]["password"] = password
    config_file = _write(tmp_path / "repo-config.yaml", config)

    cmd.create_repos(config_file, _settings(tmp_path), "")

    created = {call.args[0]: call.args[3] for call in nexus_client.return_value.create_user.call_args_list}
    assert created["foo-bar"] == password


def test_search_stays_anonymous(tmp_path, nexus_client):
    """Read-only image search needs no credentials at all."""
    nexus_client.return_value.search_images.return_value = []
    settings = _write(tmp_path / "settings.yaml", {"nexus": "https://nexus.example.org"})

    assert cmd.search(settings, None, "docker.snapshot", "") == []
    nexus_client.assert_called_once_with("https://nexus.example.org")


def test_example_files_carry_no_password_values():
    """The examples document the shape, never a copyable password."""

    def passwords(node: Any) -> list[Any]:
        found = []
        if isinstance(node, dict):
            for key, value in node.items():
                if key == "password":
                    found.append(value)
                found.extend(passwords(value))
        return found

    for name in ("settings.example.yaml", "repo-config.example.yaml"):
        values = passwords(yaml.safe_load((EXAMPLE_DIR / name).read_text()))
        assert values, f"{name} should still show where the password goes"
        assert all(value in ("", None) for value in values), name
