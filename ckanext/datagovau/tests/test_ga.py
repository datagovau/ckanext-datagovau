import pytest

import ckan.tests.factories as factories

from ckanext.datagovau.cli.googleanalytics import get_stats

GA_VIEWS_DATA = {
    "headers": ["ga:pagePath", "ga:pageviews"],
    "rows": [
        ["/dataset/test-ds-1", "5"],
        ["/dataset/test-ds-1/resource/test-res-1", "5"],
        ["/dataset/", "14"],
        ["/dataset/activity/test-ds-1", "1"],
        ["/dataset/test-ds-1/resource/test-res-1/view/view-id", "2"],
        ["/dataset/groups/test-ds-1", "1"],
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
            "/dataset/test-ds-1/resource/test-res-1",
            "Resource",
            "Download",
            "3",
        ]
    ],
}


@pytest.mark.usefixtures("clean_db")
@pytest.mark.usefixtures("with_plugins")
class TestAnalyticCollect:
    def test_stats_parsing(self, mocker):
        mocker.patch(
            "ckanext.datagovau.cli.googleanalytics.get_dataset_views",
            return_value=GA_VIEWS_DATA,
        )
        mocker.patch(
            "ckanext.datagovau.cli.googleanalytics.get_resource_downloads",
            return_value=GA_DOWNLOADS_DATA,
        )

        dataset = factories.Dataset(
            id="test-ds-1",
            name="test-ds-1",
            resources=[{"id": "test-res-1"}],
        )

        result = get_stats("1999-00")

        # We are not counting visits of `dataset/activity` | `dataset/groups`
        assert result[dataset["id"]]["views"] == 12
        # Count all downloads, not only unique ones
        assert result[dataset["id"]]["downloads"] == 3
