from __future__ import annotations

from typing import Any, Callable

import pytest
from faker import Faker

import ckan.plugins.toolkit as tk


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestRestrictResourceFormat:
    """Test resource upload format restrictions.

    PDF files can only be uploaded after at least one CSV file has been uploaded.

    Because we don't have a format field exposed in the UI, we're relying on
    file name extensions to determine the mime type.
    """

    def test_cant_upload_pdf_first(
        self, create_with_upload: Callable[..., dict[str, Any]], dataset: dict[str, Any]
    ):
        with pytest.raises(
            tk.ValidationError,
            match="Upload at least one CSV file before uploading PDF",
        ):
            create_with_upload(
                "hello", "file.pdf", {"user": "default"}, package_id=dataset["id"]
            )

    def test_can_upload_pdf_after_csv(
        self, create_with_upload: Callable[..., dict[str, Any]], dataset: dict[str, Any]
    ):
        create_with_upload(
            "hello", "file.csv", {"user": "default"}, package_id=dataset["id"]
        )
        create_with_upload(
            "hello", "file.pdf", {"user": "default"}, package_id=dataset["id"]
        )


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDgaResourceFormat:
    def test_upload_format(self, resource_factory: Any, faker: Faker):
        res = resource_factory(url=faker.file_path(extension="GIF"), format=None)
        assert res["format"] == "GIF"

        fmt = faker.word()
        res = resource_factory(url=faker.file_path(extension="unknown"), format=fmt)
        assert res["format"] == fmt

        res = resource_factory(url=faker.file_path(extension="unknown"), format=None)
        assert not res["format"]

    def test_urls_format(self, resource_factory: Any, faker: Faker):
        res = resource_factory(url=faker.url(), format=None)
        assert res["format"] == "HTML"

        res = resource_factory(url=faker.url(), format="MP4")
        assert res["format"] == "MP4"

        res = resource_factory(url=faker.url() + "test.png", format=None)
        assert res["format"] == "PNG"

        res = resource_factory(url=faker.url() + "test.png", format="MP4")
        assert res["format"] == "MP4"

        res = resource_factory(url=faker.url() + "hello", format=None)
        assert res["format"] == "HTML"

        res = resource_factory(url=faker.url() + "csv", format=None)
        assert res["format"] == "CSV"

        res = resource_factory(url=faker.url() + "x.txt?a=1", format=None)
        assert res["format"] == "TXT"

        res = resource_factory(url=faker.url() + "y.zip#hello", format=None)
        assert res["format"] == "ZIP"

    def test_manual_format(self, resource_factory: Any, faker: Faker):
        fmt = faker.word()
        res = resource_factory(url=faker.url(), format=fmt)
        assert res["format"] == fmt
