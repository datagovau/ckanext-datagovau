import pytest
from ..authenticator import UsernameEmailPasswordAuthenticator

password = "Password123"


@pytest.fixture
def authenticator():
    return UsernameEmailPasswordAuthenticator()


@pytest.mark.usefixtures("clean_db")
@pytest.mark.parametrize("user__password", [password])
class TestAuthenicator:

    def test_login_by_name(self, user, authenticator):
        name = authenticator.authenticate({}, {"login": user["name"], "password": password})
        assert name == user["name"]

    def test_login_by_email(self, user, authenticator):
        name = authenticator.authenticate({}, {"login": user["email"], "password": password})
        assert name == user["name"]

    def test_invalid(self, user, authenticator):
        name = authenticator.authenticate({}, {"login": user["name"] + user["email"], "password": password})
        assert name is None
