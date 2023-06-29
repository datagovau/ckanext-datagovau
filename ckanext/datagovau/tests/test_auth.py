import pytest

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.tests.helpers import call_auth


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestGetPackageStatsAuth:
    def test_anon_not_allowed(self, user):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "dga_get_package_stats",
                context={"user": None, "model": model},
            )

    def test_user_not_allowed(self, user):
        with pytest.raises(tk.NotAuthorized):
            call_auth(
                "dga_get_package_stats",
                context={"user": user["name"], "model": model},
            )

    def test_sysadmin_allowed(self, sysadmin):
        call_auth(
            "dga_get_package_stats",
            context={"user": sysadmin["name"], "model": model},
        )
