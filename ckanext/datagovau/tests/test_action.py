import pytest

import ckan.lib.jobs as jobs
from ckan.tests.helpers import call_action

from ckanext.datagovau.tests.conftest import DatasetFactory, OrganizationFactory

SPATIAL_1 = '{"type": "Point", "coordinates": [23, 45]}'
SPATIAL_2 = '{"type": "Point", "coordinates": [67, 89]}'


@pytest.mark.usefixtures("with_plugins", "clean_db", "clean_index", "clean_queues")
class TestOrganizationUpdateReindexing:
    def test_reindex_triggered_on_spatial_coverage_change(self, user):
        """Reindexing is triggered when an organization's spatial_coverage changes."""
        organization = OrganizationFactory(spatial_coverage=SPATIAL_1)
        DatasetFactory(owner_org=organization["id"], spatial_coverage=None)

        queue = jobs.get_queue()
        assert queue.is_empty() == True

        call_action(
            "organization_patch",
            context={"user": user["name"]},
            id=organization["id"],
            spatial_coverage=SPATIAL_2,
        )
        assert queue.is_empty() == False

    def test_no_reindex_when_spatial_coverage_unchanged(self, user):
        """Reindexing is not triggered when spatial_coverage remains unchanged."""
        organization = OrganizationFactory(spatial_coverage=SPATIAL_1)
        DatasetFactory(owner_org=organization["id"], spatial_coverage=None)

        queue = jobs.get_queue()
        assert queue.is_empty() == True

        call_action(
            "organization_patch",
            context={"user": user["name"]},
            id=organization["id"],
            spatial_coverage=SPATIAL_1,
        )
        assert queue.is_empty() == True

    def test_datasets_with_existing_spatial_coverage(self, user):
        """Datasets with their own spatial_coverage are not reindexed."""
        organization = OrganizationFactory(spatial_coverage=SPATIAL_1)
        DatasetFactory(owner_org=organization["id"], spatial_coverage=SPATIAL_1)

        queue = jobs.get_queue()
        assert queue.is_empty() == True

        call_action(
            "organization_patch",
            context={"user": user["name"]},
            id=organization["id"],
            spatial_coverage=SPATIAL_2,
        )
        assert queue.is_empty() == False

    def test_no_datasets_to_reindex(self, user):
        """No reindexing occurs if there are no active datasets."""
        organization = OrganizationFactory(spatial_coverage=SPATIAL_1)

        queue = jobs.get_queue()
        assert queue.is_empty() == True

        call_action(
            "organization_patch",
            context={"user": user["name"]},
            id=organization["id"],
            spatial_coverage=SPATIAL_2,
        )
        assert queue.is_empty() == False
