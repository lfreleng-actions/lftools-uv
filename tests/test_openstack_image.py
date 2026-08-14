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
"""Test openstack image module."""

from datetime import datetime, timedelta
from unittest.mock import MagicMock, call, patch

import pytest
from openstack.cloud.exc import OpenStackCloudException

from lftools_uv.openstack import image as os_image


@pytest.fixture
def mock_image():
    """Create a mock OpenStack image."""
    image = MagicMock()
    image.name = "test-image"
    image.id = "image-123"
    image.is_protected = False
    image.visibility = "private"
    image.owner = "project-123"
    image.properties = {"ci_managed": "yes"}
    image.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
    return image


@pytest.fixture
def mock_cloud():
    """Create a mock OpenStack cloud connection."""
    cloud = MagicMock()
    cloud.config._name = "test-cloud"
    cloud._get_project_info.return_value = {"id": "project-123"}
    return cloud


class TestFilterImages:
    """Test _filter_images function."""

    def test_filter_images_no_filters(self, mock_image):
        """Test filtering with no filters applied."""
        images = [mock_image]
        filtered = os_image._filter_images(images)
        assert len(filtered) == 1
        assert filtered[0] == mock_image

    def test_filter_images_hide_public(self, mock_image):
        """Test filtering out public images."""
        public_image = MagicMock()
        public_image.visibility = "public"
        public_image.properties = {"ci_managed": "yes"}
        public_image.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        images = [mock_image, public_image]
        filtered = os_image._filter_images(images, hide_public=True)
        assert len(filtered) == 1
        assert filtered[0] == mock_image

    def test_filter_images_ci_managed(self, mock_image):
        """Test filtering by ci_managed metadata."""
        unmanaged_image = MagicMock()
        unmanaged_image.visibility = "private"
        unmanaged_image.is_protected = False
        unmanaged_image.properties = {}
        unmanaged_image.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        images = [mock_image, unmanaged_image]
        filtered = os_image._filter_images(images, ci_managed=True)
        assert len(filtered) == 1
        assert filtered[0] == mock_image

    def test_filter_images_by_days(self, mock_image):
        """Test filtering images by age."""
        old_image = MagicMock()
        old_image.visibility = "private"
        old_image.is_protected = False
        old_image.properties = {"ci_managed": "yes"}
        old_image.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        new_image = MagicMock()
        new_image.visibility = "private"
        new_image.is_protected = False
        new_image.properties = {"ci_managed": "yes"}
        new_image.created_at = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")

        images = [old_image, new_image]
        filtered = os_image._filter_images(images, days=5)
        assert len(filtered) == 1
        assert filtered[0] == old_image

    def test_filter_images_protected(self, mock_image):
        """Test that protected images are filtered out."""
        protected_image = MagicMock()
        protected_image.visibility = "private"
        protected_image.is_protected = True
        protected_image.properties = {"ci_managed": "yes"}
        protected_image.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")

        images = [mock_image, protected_image]
        filtered = os_image._filter_images(images)
        assert len(filtered) == 1
        assert filtered[0] == mock_image


@patch("openstack.connection.from_config")
class TestListImages:
    """Test list function."""

    def test_list_images(self, mock_from_config, mock_cloud, mock_image):
        """Test listing images."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]

        os_image.list("test-cloud")
        mock_cloud.list_images.assert_called_once()


@patch("openstack.connection.from_config")
class TestCleanupImages:
    """Test cleanup function."""

    def test_cleanup_success(self, mock_from_config, mock_cloud, mock_image):
        """Test successful image cleanup."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]
        mock_cloud.delete_image.return_value = True

        os_image.cleanup("test-cloud", days=5)

        mock_cloud.delete_image.assert_called_once_with(mock_image.id)

    def test_cleanup_protected_image(self, mock_from_config, mock_cloud, mock_image):
        """Test that protected images are not deleted."""
        mock_image.is_protected = True
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]

        os_image.cleanup("test-cloud")

        mock_cloud.delete_image.assert_not_called()

    def test_cleanup_shared_image(self, mock_from_config, mock_cloud, mock_image):
        """Test that shared images are not deleted."""
        mock_image.visibility = "shared"
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]

        os_image.cleanup("test-cloud")

        mock_cloud.delete_image.assert_not_called()

    def test_cleanup_not_owned_image(self, mock_from_config, mock_cloud, mock_image):
        """Test that images not owned by project are not deleted."""
        mock_image.owner = "different-project"
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]

        os_image.cleanup("test-cloud")

        mock_cloud.delete_image.assert_not_called()

    def test_cleanup_multiple_matches_old_format(self, mock_from_config, mock_cloud, mock_image):
        """Test handling of duplicate image exception with old format."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]
        mock_cloud.delete_image.side_effect = OpenStackCloudException("Multiple matches found for image-name")

        # Should not raise exception, just skip the image
        os_image.cleanup("test-cloud")

        mock_cloud.delete_image.assert_called_once_with(mock_image.id)

    def test_cleanup_multiple_matches_new_format(self, mock_from_config, mock_cloud, mock_image):
        """Test handling of duplicate image exception with new format."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]
        mock_cloud.delete_image.side_effect = OpenStackCloudException(
            "More than one Image exists with the name 'image-name'"
        )

        # Should not raise exception, just skip the image
        os_image.cleanup("test-cloud")

        mock_cloud.delete_image.assert_called_once_with(mock_image.id)

    def test_cleanup_unexpected_exception(self, mock_from_config, mock_cloud, mock_image):
        """Test that unexpected exceptions are raised."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]
        mock_cloud.delete_image.side_effect = OpenStackCloudException("Unexpected error")

        with pytest.raises(OpenStackCloudException, match="Unexpected error"):
            os_image.cleanup("test-cloud")

    def test_cleanup_delete_failed(self, mock_from_config, mock_cloud, mock_image):
        """Test handling when delete returns False."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]
        mock_cloud.delete_image.return_value = False

        # Should not raise exception, just log warning
        os_image.cleanup("test-cloud")

        mock_cloud.delete_image.assert_called_once_with(mock_image.id)

    def test_cleanup_duplicate_names_deleted_by_id(self, mock_from_config, mock_cloud):
        """Duplicate image names must not stop those images being removed.

        Glance does not enforce unique image names, and retried builds do
        produce duplicates. Addressing an image by name makes the lookup
        ambiguous for a duplicated name, which raised DuplicateResource and
        skipped the image on every run. Addressing by id always resolves to
        exactly one image, so every copy is removed.
        """

        def _image(name, image_id):
            i = MagicMock()
            i.name = name
            i.id = image_id
            i.is_protected = False
            i.visibility = "private"
            i.owner = "project-123"
            i.properties = {"ci_managed": "yes"}
            i.created_at = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%SZ")
            return i

        first = _image("duplicate-name", "image-aaa")
        second = _image("duplicate-name", "image-bbb")
        unique = _image("unique-name", "image-ccc")

        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [first, second, unique]
        mock_cloud.delete_image.return_value = True

        os_image.cleanup("test-cloud", days=5)

        assert mock_cloud.delete_image.call_args_list == [
            call("image-aaa"),
            call("image-bbb"),
            call("image-ccc"),
        ]

    def test_cleanup_multiple_clouds(self, mock_from_config, mock_cloud, mock_image):
        """Test cleanup across multiple clouds."""
        mock_from_config.return_value = mock_cloud
        mock_cloud.list_images.return_value = [mock_image]
        mock_cloud.delete_image.return_value = True

        os_image.cleanup("test-cloud", clouds="cloud1,cloud2")

        # Should be called for test-cloud, cloud1, and cloud2
        assert mock_from_config.call_count == 3
