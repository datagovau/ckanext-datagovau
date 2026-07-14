import pytest

from ckan.tests import factories
from ckan.tests.helpers import call_action

from ckanext.datagovau.tests.conftest import DatasetFactory, OrganizationFactory


@pytest.mark.ckan_config("ckan.datasets_per_page", 2)
@pytest.mark.usefixtures("with_plugins", "clean_db")
def test_dataset_groups_are_paginated_after_filtering_to_dataset_groups(app):
    sysadmin = factories.Sysadmin()
    organization = OrganizationFactory()
    dataset = DatasetFactory(owner_org=organization["id"])

    factories.Group(title="A unrelated group")
    factories.Group(title="B unrelated group")
    group_1 = factories.Group(title="Y associated group")
    group_2 = factories.Group(title="Z associated group")

    for group in (group_1, group_2):
        call_action(
            "member_create",
            context={"user": sysadmin["name"]},
            id=group["id"],
            object=dataset["id"],
            object_type="package",
            capacity="public",
        )

    response = app.get(
        f"/dataset/groups/{dataset['name']}",
        query_string={"sort": "title asc"},
    )

    assert "2 groups found" in response.body
    assert group_1["title"] in response.body
    assert group_2["title"] in response.body
    assert "There are no groups associated with this dataset" not in response.body
