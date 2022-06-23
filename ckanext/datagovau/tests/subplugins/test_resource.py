from unittest import mock

import pytest
from ckan.tests.helpers import call_action


@pytest.mark.ckan_config("ckan.plugins", "datagovau dga_resource")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestScheduler:
    @mock.patch("ckanext.datagovau.subplugins.resource._schedule_unzip")
    def test_not_triggered_for_non_zip(
        self, mock, create_with_upload, dataset
    ):
        create_with_upload(
            "hello",
            "file.txt",
            description="created!",
            package_id=dataset["id"],
        )
        mock.assert_not_called()

    @mock.patch("ckanext.datagovau.subplugins.resource._schedule_unzip")
    def test_not_triggered_for_zip_without_flag(
        self, mock, create_with_upload, dataset
    ):
        create_with_upload(
            "hello",
            "file.zip",
            description="created!",
            package_id=dataset["id"],
        )
        mock.assert_not_called()

    @mock.patch("ckanext.datagovau.subplugins.resource._schedule_unzip")
    def test_triggered_for_zip_with_flag(
        self, mock, create_with_upload, dataset
    ):
        create_with_upload(
            "hello",
            "file.zip",
            description="created!",
            package_id=dataset["id"],
            zip_extract=True,
        )
        mock.assert_called()

    def test_job_enqueued(self, create_with_upload, dataset):
        create_with_upload(
            "hello",
            "file.zip",
            description="created!",
            package_id=dataset["id"],
            zip_extract=True,
        )
