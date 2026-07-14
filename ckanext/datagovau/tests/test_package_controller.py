import pytest

from ckan.tests.helpers import call_action

from ckanext.datagovau.implementations.package_controller import (
    _hide_showcases_from_search,
)
from ckanext.datagovau.tests.conftest import DatasetFactory, OrganizationFactory

SPATIAL_1 = '{"type": "Point", "coordinates": [23, 45]}'
SPATIAL_2 = '{"type": "Point", "coordinates": [67, 89]}'


@pytest.mark.parametrize(
    ("search_params", "expected_fq"),
    [
        ({}, "-dataset_type:showcase"),
        (
            {"fq": "organization:example-org"},
            "organization:example-org -dataset_type:showcase",
        ),
        ({"fq": "dataset_type:showcase"}, "dataset_type:showcase"),
    ],
)
def test_hide_showcases_from_search(search_params, expected_fq):
    _hide_showcases_from_search(search_params)

    assert search_params["fq"] == expected_fq


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestDatasetSpatialCoveragePopulatedFromOrganization:
    def test_dataset_spatial_coverage_populated_from_organization(self):
        organization = OrganizationFactory(spatial_coverage=SPATIAL_1)
        pkg_dict = DatasetFactory(owner_org=organization["id"], spatial_coverage=None)
        pkg_dict_after_show = call_action("package_show", id=pkg_dict["id"])
        assert pkg_dict_after_show["spatial"] == SPATIAL_1

    def test_dataset_spatial_coverage_not_overwritten(self):
        organization = OrganizationFactory(spatial_coverage=SPATIAL_1)
        pkg_dict = DatasetFactory(
            owner_org=organization["id"], spatial_coverage=SPATIAL_2
        )
        pkg_dict_after_show = call_action("package_show", id=pkg_dict["id"])
        assert pkg_dict_after_show["spatial"] == SPATIAL_2
