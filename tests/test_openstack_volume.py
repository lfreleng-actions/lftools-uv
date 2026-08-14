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
"""Test openstack volume module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest
from openstack.cloud.exc import OpenStackCloudException

from lftools_uv.openstack import volume as os_volume


@pytest.fixture
def mock_volume():
    """Create a mock OpenStack volume."""
    volume = MagicMock()
    volume.name = "test-volume"
    volume.id = "volume-123"
    volume.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")
    return volume


@pytest.fixture
def mock_cloud():
    """Create a mock OpenStack cloud connection."""
    cloud = MagicMock()
    cloud.cloud_config.name = "test-cloud"
    return cloud


class TestFilterVolumes:
    """Test _filter_volumes function."""

    def test_filter_volumes_no_filters(self, mock_volume):
        """Test filtering with no filters applied."""
        volumes = [mock_volume]
        filtered = os_volume._filter_volumes(volumes)
        assert len(filtered) == 1
        assert filtered[0] == mock_volume

    def test_filter_volumes_by_days(self, mock_volume):
        """Test filtering volumes by age."""
        old_volume = MagicMock()
        old_volume.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        new_volume = MagicMock()
        new_volume.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        volumes = [old_volume, new_volume]
        filtered = os_volume._filter_volumes(volumes, days=5)
        assert len(filtered) == 1
        assert filtered[0] == old_volume

    def test_filter_volumes_all_recent(self, mock_volume):
        """Test filtering when all volumes are too recent."""
        recent_volume = MagicMock()
        recent_volume.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        volumes = [recent_volume]
        filtered = os_volume._filter_volumes(volumes, days=5)
        assert len(filtered) == 0


@patch("openstack.connection.from_config")
class TestListVolumes:
    """Test list function."""

    def test_list_volumes(self, mock_from_config, mock_cloud, mock_volume):
        """Test listing volumes."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [mock_volume]

        os_volume.list("test-cloud")
        mock_cloud.list_volumes.assert_called_once()

    def test_list_volumes_with_filter(self, mock_from_config, mock_cloud, mock_volume):
        """Test listing volumes with age filter."""
        old_volume = MagicMock()
        old_volume.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        new_volume = MagicMock()
        new_volume.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [old_volume, new_volume]

        os_volume.list("test-cloud", days=5)
        mock_cloud.list_volumes.assert_called_once()


@patch("openstack.connection.from_config")
class TestCleanupVolumes:
    """Test cleanup function."""

    def test_cleanup_success(self, mock_from_config, mock_cloud, mock_volume):
        """Test successful volume cleanup."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [mock_volume]
        mock_cloud.delete_volume.return_value = True

        os_volume.cleanup("test-cloud", days=5)

        mock_cloud.delete_volume.assert_called_once_with(mock_volume.id)

    def test_cleanup_multiple_volumes(self, mock_from_config, mock_cloud):
        """Test cleanup of multiple volumes."""
        volume1 = MagicMock()
        volume1.name = "volume-1"
        volume1.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        volume2 = MagicMock()
        volume2.name = "volume-2"
        volume2.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [volume1, volume2]
        mock_cloud.delete_volume.return_value = True

        os_volume.cleanup("test-cloud", days=5)

        assert mock_cloud.delete_volume.call_count == 2

    def test_cleanup_multiple_matches_old_format(self, mock_from_config, mock_cloud, mock_volume):
        """Test handling of duplicate volume exception with old format."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [mock_volume]
        mock_cloud.delete_volume.side_effect = OpenStackCloudException("Multiple matches found for volume-name")

        # Should not raise exception, just skip the volume
        os_volume.cleanup("test-cloud")

        mock_cloud.delete_volume.assert_called_once_with(mock_volume.id)

    def test_cleanup_multiple_matches_new_format(self, mock_from_config, mock_cloud, mock_volume):
        """Test handling of duplicate volume exception with new format."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [mock_volume]
        mock_cloud.delete_volume.side_effect = OpenStackCloudException(
            "More than one Volume exists with the name 'volume-name'"
        )

        # Should not raise exception, just skip the volume
        os_volume.cleanup("test-cloud")

        mock_cloud.delete_volume.assert_called_once_with(mock_volume.id)

    def test_cleanup_unexpected_exception(self, mock_from_config, mock_cloud, mock_volume):
        """Test that unexpected exceptions are raised."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [mock_volume]
        mock_cloud.delete_volume.side_effect = OpenStackCloudException("Unexpected error")

        with pytest.raises(OpenStackCloudException, match="Unexpected error"):
            os_volume.cleanup("test-cloud")

    def test_cleanup_delete_failed(self, mock_from_config, mock_cloud, mock_volume):
        """Test handling when delete returns False."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [mock_volume]
        mock_cloud.delete_volume.return_value = False

        # Should not raise exception, just log warning
        os_volume.cleanup("test-cloud")

        mock_cloud.delete_volume.assert_called_once_with(mock_volume.id)

    def test_cleanup_mixed_results(self, mock_from_config, mock_cloud):
        """Test cleanup with one success and one duplicate exception."""
        volume1 = MagicMock()
        volume1.name = "volume-1"
        volume1.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        volume2 = MagicMock()
        volume2.name = "volume-2"
        volume2.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [volume1, volume2]

        # First call succeeds, second call raises duplicate exception
        mock_cloud.delete_volume.side_effect = [
            True,
            OpenStackCloudException("More than one Volume exists with the name 'volume-2'"),
        ]

        # Should not raise exception
        os_volume.cleanup("test-cloud")

        assert mock_cloud.delete_volume.call_count == 2

    def test_cleanup_duplicate_names_deleted_by_id(self, mock_from_config, mock_cloud):
        """Duplicate volume names must not stop those volumes being removed.

        Cinder does not enforce unique volume names. Addressing a volume by
        name makes the lookup ambiguous for a duplicated name, which raised
        DuplicateResource and skipped the volume on every run. Addressing by
        id always resolves to exactly one volume, so every copy is removed.
        """

        def _volume(name, volume_id):
            v = MagicMock()
            v.name = name
            v.id = volume_id
            v.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")
            return v

        first = _volume("duplicate-name", "volume-aaa")
        second = _volume("duplicate-name", "volume-bbb")
        unique = _volume("unique-name", "volume-ccc")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_volumes.return_value = [first, second, unique]
        mock_cloud.delete_volume.return_value = True

        os_volume.cleanup("test-cloud", days=5)

        assert mock_cloud.delete_volume.call_args_list == [
            call("volume-aaa"),
            call("volume-bbb"),
            call("volume-ccc"),
        ]


@patch("openstack.connection.from_config")
class TestRemoveVolume:
    """Test remove function."""

    def test_remove_volume_success(self, mock_from_config, mock_cloud, mock_volume):
        """Test successful volume removal."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_volume_by_id.return_value = mock_volume
        mock_volume.created_at = (datetime.utcnow() - timedelta(minutes=10)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        os_volume.remove("test-cloud", "volume-123", minutes=5)

        mock_cloud.delete_volume.assert_called_once_with(mock_volume.id)

    def test_remove_volume_not_found(self, mock_from_config, mock_cloud):
        """Test removal when volume is not found."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_volume_by_id.return_value = None

        with pytest.raises(SystemExit) as exc_info:
            os_volume.remove("test-cloud", "nonexistent-volume")

        assert exc_info.value.code == 1
        mock_cloud.delete_volume.assert_not_called()

    def test_remove_volume_too_recent(self, mock_from_config, mock_cloud, mock_volume):
        """Test that recent volumes are not deleted."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_volume_by_id.return_value = mock_volume
        mock_volume.created_at = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        os_volume.remove("test-cloud", "volume-123", minutes=5)

        # Should not delete the volume
        mock_cloud.delete_volume.assert_not_called()

    def test_remove_volume_no_time_check(self, mock_from_config, mock_cloud, mock_volume):
        """Test removal without time check."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.get_volume_by_id.return_value = mock_volume
        mock_volume.created_at = (datetime.utcnow() - timedelta(minutes=1)).strftime("%Y-%m-%dT%H:%M:%S.%f")

        os_volume.remove("test-cloud", "volume-123", minutes=0)

        # Should delete the volume regardless of age
        mock_cloud.delete_volume.assert_called_once_with(mock_volume.id)
