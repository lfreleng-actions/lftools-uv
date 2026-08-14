# -*- code: utf-8 -*-
# SPDX-License-Identifier: EPL-1.0
##############################################################################
# Copyright (c) 2024 The Linux Foundation and others.
#
# All rights reserved. This program and the accompanying materials
# are made available under the terms of the Eclipse Public License v1.0
# which accompanies this distribution, and is available at
# http://www.eclipse.org/legal/epl-v10.html
##############################################################################
"""Test openstack server module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest
from openstack.cloud.exc import OpenStackCloudException

from lftools_uv.openstack import server as os_server


@pytest.fixture
def mock_server():
    """Create a mock OpenStack server."""
    server = MagicMock()
    server.name = "test-server"
    server.id = "server-123"
    server.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return server


@pytest.fixture
def mock_cloud():
    """Create a mock OpenStack cloud connection."""
    cloud = MagicMock()
    cloud.cloud_config.name = "test-cloud"
    return cloud


class TestFilterServers:
    """Test _filter_servers function."""

    def test_filter_servers_no_filters(self, mock_server):
        """Test filtering with no filters applied."""
        servers = [mock_server]
        filtered = os_server._filter_servers(servers)
        assert len(filtered) == 1
        assert filtered[0] == mock_server

    def test_filter_servers_by_days(self, mock_server):
        """Test filtering servers by age."""
        old_server = MagicMock()
        old_server.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_server = MagicMock()
        new_server.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        servers = [old_server, new_server]
        filtered = os_server._filter_servers(servers, days=5)
        assert len(filtered) == 1
        assert filtered[0] == old_server

    def test_filter_servers_all_recent(self, mock_server):
        """Test filtering when all servers are too recent."""
        recent_server = MagicMock()
        recent_server.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        servers = [recent_server]
        filtered = os_server._filter_servers(servers, days=5)
        assert len(filtered) == 0


@patch("openstack.connection.from_config")
class TestListServers:
    """Test list function."""

    def test_list_servers(self, mock_from_config, mock_cloud, mock_server):
        """Test listing servers."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [mock_server]

        os_server.list("test-cloud")
        mock_cloud.list_servers.assert_called_once()

    def test_list_servers_with_filter(self, mock_from_config, mock_cloud, mock_server):
        """Test listing servers with age filter."""
        old_server = MagicMock()
        old_server.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_server = MagicMock()
        new_server.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [old_server, new_server]

        os_server.list("test-cloud", days=5)
        mock_cloud.list_servers.assert_called_once()


@patch("openstack.connection.from_config")
class TestCleanupServers:
    """Test cleanup function."""

    def test_cleanup_success(self, mock_from_config, mock_cloud, mock_server):
        """Test successful server cleanup."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [mock_server]
        mock_cloud.delete_server.return_value = True

        os_server.cleanup("test-cloud", days=5)

        mock_cloud.delete_server.assert_called_once_with(mock_server.id)

    def test_cleanup_multiple_servers(self, mock_from_config, mock_cloud):
        """Test cleanup of multiple servers."""
        server1 = MagicMock()
        server1.name = "server-1"
        server1.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        server2 = MagicMock()
        server2.name = "server-2"
        server2.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [server1, server2]
        mock_cloud.delete_server.return_value = True

        os_server.cleanup("test-cloud", days=5)

        assert mock_cloud.delete_server.call_count == 2

    def test_cleanup_multiple_matches_old_format(self, mock_from_config, mock_cloud, mock_server):
        """Test handling of duplicate server exception with old format."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [mock_server]
        mock_cloud.delete_server.side_effect = OpenStackCloudException("Multiple matches found for server-name")

        # Should not raise exception, just skip the server
        os_server.cleanup("test-cloud")

        mock_cloud.delete_server.assert_called_once_with(mock_server.id)

    def test_cleanup_multiple_matches_new_format(self, mock_from_config, mock_cloud, mock_server):
        """Test handling of duplicate server exception with new format."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [mock_server]
        mock_cloud.delete_server.side_effect = OpenStackCloudException(
            "More than one Server exists with the name 'server-name'"
        )

        # Should not raise exception, just skip the server
        os_server.cleanup("test-cloud")

        mock_cloud.delete_server.assert_called_once_with(mock_server.id)

    def test_cleanup_unexpected_exception(self, mock_from_config, mock_cloud, mock_server):
        """Test that unexpected exceptions are raised."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [mock_server]
        mock_cloud.delete_server.side_effect = OpenStackCloudException("Unexpected error")

        with pytest.raises(OpenStackCloudException, match="Unexpected error"):
            os_server.cleanup("test-cloud")

    def test_cleanup_delete_failed(self, mock_from_config, mock_cloud, mock_server):
        """Test handling when delete returns False."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [mock_server]
        mock_cloud.delete_server.return_value = False

        # Should not raise exception, just log warning
        os_server.cleanup("test-cloud")

        mock_cloud.delete_server.assert_called_once_with(mock_server.id)

    def test_cleanup_mixed_results(self, mock_from_config, mock_cloud):
        """Test cleanup with one success and one duplicate exception."""
        server1 = MagicMock()
        server1.name = "server-1"
        server1.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        server2 = MagicMock()
        server2.name = "server-2"
        server2.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [server1, server2]

        # First call succeeds, second call raises duplicate exception
        mock_cloud.delete_server.side_effect = [
            True,
            OpenStackCloudException("More than one Server exists with the name 'server-2'"),
        ]

        # Should not raise exception
        os_server.cleanup("test-cloud")

        assert mock_cloud.delete_server.call_count == 2

    def test_cleanup_duplicate_names_deleted_by_id(self, mock_from_config, mock_cloud):
        """Duplicate server names must not stop those servers being removed.

        Nova does not enforce unique server names. Addressing a server by
        name makes the lookup ambiguous for a duplicated name, which raised
        DuplicateResource and skipped the server on every run. Addressing by
        id always resolves to exactly one server, so every copy is removed.
        """

        def _server(name, server_id):
            s = MagicMock()
            s.name = name
            s.id = server_id
            s.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return s

        first = _server("duplicate-name", "server-aaa")
        second = _server("duplicate-name", "server-bbb")
        unique = _server("unique-name", "server-ccc")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_servers.return_value = [first, second, unique]
        mock_cloud.delete_server.return_value = True

        os_server.cleanup("test-cloud", days=5)

        assert mock_cloud.delete_server.call_args_list == [
            call("server-aaa"),
            call("server-bbb"),
            call("server-ccc"),
        ]


@patch("openstack.connection.from_config")
class TestRemoveServer:
    """Test remove function."""

    def test_remove_server_success(self, mock_from_config, mock_cloud, mock_server):
        """Test successful server removal."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_server.return_value = mock_server
        mock_server.created_at = (datetime.utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        os_server.remove("test-cloud", "test-server", minutes=5)

        mock_cloud.delete_server.assert_called_once_with(mock_server.id)

    def test_remove_server_not_found(self, mock_from_config, mock_cloud):
        """Test removal when server is not found."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_server.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            os_server.remove("test-cloud", "nonexistent-server")

        assert exc_info.value.code == 1
        mock_cloud.delete_server.assert_not_called()

    def test_remove_server_too_recent(self, mock_from_config, mock_cloud, mock_server):
        """Test that recent servers are not deleted."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_server.return_value = mock_server
        mock_server.created_at = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        os_server.remove("test-cloud", "test-server", minutes=5)

        # Should not delete the server
        mock_cloud.delete_server.assert_not_called()

    def test_remove_server_no_time_check(self, mock_from_config, mock_cloud, mock_server):
        """Test removal without time check."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_server.return_value = mock_server
        mock_server.created_at = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        os_server.remove("test-cloud", "test-server", minutes=0)

        # Should delete the server regardless of age
        mock_cloud.delete_server.assert_called_once_with(mock_server.id)
