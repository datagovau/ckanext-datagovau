import unittest.mock as mock

import pytest

import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as tk


@pytest.mark.usefixtures("with_request_context", "with_plugins", "clean_db")
class TestGetPackageStatsHelper:
    def test_get_package_stats(self, app, sysadmin, dataset):
        with app.flask_app.test_request_context():
            tk.current_user = model.User.get(sysadmin["name"])

            # no dataset statistics
            result = tk.h.dga_get_package_stats(dataset["id"])
            assert result == {}

            # dataset doesn't exists
            result = tk.h.dga_get_package_stats("not-existing-dataset")
            assert result == {}

            # mock some data
            dga_get_package_stats = mock.Mock(
                return_value={
                    "2022-05": {"views": 18, "downloads": 9},
                    "2022-06": {"views": 24, "downloads": 11},
                }
            )
            logic._actions["dga_get_package_stats"] = dga_get_package_stats

            result = tk.h.dga_get_package_stats(dataset["id"])

            assert len(result) == 2
            assert result[0]["datasets"]
            assert result[0]["labels"] == ["2022 May", "2022 Jun"]
            assert result[0]["total"]
