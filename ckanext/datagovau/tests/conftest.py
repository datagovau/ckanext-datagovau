from __future__ import annotations

from typing import Any
from unittest import mock

import pytest
from factory import Faker, LazyFunction
from pytest_factoryboy import register

from ckan.tests import factories

from ckanext.mailcraft.utils import get_mailer
from ckanext.security.model import db_setup as security_db_setup

Faker.override_default_locale("en_AU")


@pytest.fixture
def fake_mailer(monkeypatch: Any):
    mailer = get_mailer()
    fake_mailer = mock.Mock()
    monkeypatch.setattr(type(mailer), "mail_recipients", fake_mailer)
    return fake_mailer


@pytest.fixture
def clean_db(reset_db: Any, migrate_db_for: Any):
    reset_db()
    migrate_db_for("datagovau")
    migrate_db_for("flakes")
    migrate_db_for("activity")
    migrate_db_for("harvest")
    security_db_setup()


@register(_name="dataset")
class DatasetFactory(factories.Dataset):
    contact_point = Faker("email")
    data_state = "active"
    license_id = "cc-by"
    spatial_coverage = "GA1487"
    temporal_coverage_from = Faker("date")
    update_freq = "daily"

    @classmethod
    def _create(cls, model_class, *args, **kwargs):
        kwargs.setdefault("original_name", kwargs["name"])

        return super()._create(model_class, *args, **kwargs)


@register()
class ResourceFactory(factories.Resource):
    package_id = LazyFunction(lambda: DatasetFactory()["id"])


@register(_name="organization")
class OrganizationFactory(factories.Organization):
    email = Faker("email")
    jurisdiction = "Commonwealth of Australia"
    spatial_coverage = "GA1487"
    telephone = Faker("phone_number")
    website = Faker("url")
    contact_point = "dev@linkdigital.com.au"
    temporal_coverage_from = "2024-10-20"
    original_name = None
