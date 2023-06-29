import pytest
from pytest_factoryboy import register

from ckan.tests import factories


@register
class UserFactory(factories.User):
    pass


@register
class OrganizationFactory(factories.Organization):
    pass


@pytest.fixture
def clean_db(reset_db, migrate_db_for):
    reset_db()
    migrate_db_for("flakes")


@register(_name="sysadmin")
class SysadminFactory(factories.Sysadmin):
    pass


@register(_name="dataset")
class DatasetFactory(factories.Dataset):
    pass
