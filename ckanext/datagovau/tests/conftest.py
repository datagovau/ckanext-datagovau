from __future__ import annotations

from typing import Any

import pytest
from factory import Faker
from pytest_factoryboy import register

from ckan.tests import factories

Faker.override_default_locale("en_AU")


@pytest.fixture()
def clean_db(reset_db: Any, migrate_db_for: Any):
    reset_db()
    migrate_db_for("flakes")
    migrate_db_for("activity")


@register(_name="dataset")
class DatasetFactory(factories.Dataset):
    contact_point = Faker("email")
    data_state = "active"
    jurisdiction = "Commonwealth of Australia"
    license_id = "cc-by"
    spatial_coverage = "GA1487"
    temporal_coverage_from = Faker("date")
    update_freq = "daily"


@register(_name="organization")
class OrganizationFactory(factories.Organization):
    email = Faker("email")
    jurisdiction = "Commonwealth of Australia"
    spatial_coverage = "GA1487"
    telephone = Faker("phone_number")
    website = Faker("url")
