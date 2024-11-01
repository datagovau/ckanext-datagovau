from __future__ import annotations

import uuid
from typing import Any

import pytest
from faker import Faker

from ckanext.datagovau.cli.googleanalytics import get_stats

DATASET_ID = str(uuid.uuid4())
RESOURCE_ID = str(uuid.uuid4())

GA_VIEWS_DATA = {
    "headers": ["ga:pagePath", "ga:pageviews"],
    "rows": [
        [f"/dataset/{DATASET_ID}", "5"],
        [f"/dataset/{DATASET_ID}/resource/{RESOURCE_ID}", "5"],
        ["/dataset/", "14"],
        [f"/dataset/activity/{DATASET_ID}", "1"],
        [f"/dataset/{DATASET_ID}/resource/{RESOURCE_ID}/view/view-id", "2"],
        [f"/dataset/groups/{DATASET_ID}", "1"],
        ["/organization/test-org", "1"],
        ["/organization/new", "1"],
        ["/user/test", "1"],
    ],
}

GA_DOWNLOADS_DATA = {
    "headers": [
        "ga:pagePath",
        "ga:eventCategory",
        "ga:eventAction",
        "ga:totalEvents",
    ],
    "rows": [
        [
            f"/dataset/{DATASET_ID}/resource/{RESOURCE_ID}",
            "Resource",
            "Download",
            "3",
        ]
    ],
}


@pytest.mark.usefixtures("clean_db")
@pytest.mark.usefixtures("with_plugins")
class TestAnalyticCollect:
    def test_stats_parsing(self, mocker: Any, dataset_factory: Any, faker: Faker):
        mocker.patch(
            "ckanext.datagovau.cli.googleanalytics.get_dataset_views",
            return_value=GA_VIEWS_DATA,
        )
        mocker.patch(
            "ckanext.datagovau.cli.googleanalytics.get_resource_downloads",
            return_value=GA_DOWNLOADS_DATA,
        )

        dataset = dataset_factory(
            name=DATASET_ID,
            resources=[{"id": RESOURCE_ID, "url": faker.url()}],
        )

        result = get_stats("1999-00")

        # We are not counting visits of `dataset/activity` | `dataset/groups`
        assert result[dataset["id"]]["views"] == 12
        # Count all downloads, not only unique ones
        assert result[dataset["id"]]["downloads"] == 3
