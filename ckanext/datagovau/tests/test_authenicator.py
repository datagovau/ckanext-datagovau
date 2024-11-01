import pytest

from ckan.lib.authenticator import default_authenticate

password = "Password123"


@pytest.fixture()
def authenticator():
    return default_authenticate


@pytest.mark.usefixtures("with_plugins", "clean_db", "with_request_context")
@pytest.mark.parametrize("user__password", [password])
class TestAuthenicator:
    def test_login_by_name(self, user, authenticator):
        name = authenticator({"login": user["name"], "password": password})
        assert name.name == user["name"]

    def test_login_by_email(self, user, authenticator):
        name = authenticator({"login": user["email"], "password": password})
        assert name.name == user["name"]

    def test_invalid(self, user, authenticator):
        name = authenticator(
            {"login": user["name"] + user["email"], "password": password}
        )
        assert name is None
