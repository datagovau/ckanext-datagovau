from pytest_factoryboy import register
from ckan.tests import factories


@register
class UserFactory(factories.User):
    pass


@register
class OrganizationFactory(factories.Organization):
    pass
