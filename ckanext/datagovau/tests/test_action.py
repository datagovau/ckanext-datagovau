import unittest.mock as mock

import pytest

import ckan.logic as logic
import ckan.plugins.toolkit as tk
from ckan.tests.helpers import call_action


@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestGetPackageStats:
    def test_no_data(self):
        with pytest.raises(tk.ObjectNotFound, match="No dataset statistics"):
            call_action("dga_get_package_stats")

    def test_dataset_not_found(self):
        flakes_flake_lookup = mock.Mock(
            return_value={
                "data": {
                    "4c5973e1-6a7e-4ee2-8a22-9296fa8db838": {
                        "2022-06": {"views": 18, "downloads": 9}
                    }
                }
            }
        )

        logic._actions["flakes_flake_lookup"] = flakes_flake_lookup

        with pytest.raises(tk.ValidationError, match="Not found: Dataset"):
            call_action("dga_get_package_stats", id="test")

    def test_dataset_found(self, dataset):
        flakes_flake_lookup = mock.Mock(
            return_value={
                "data": {dataset["id"]: {"2022-06": {"views": 18, "downloads": 9}}}
            }
        )

        logic._actions["flakes_flake_lookup"] = flakes_flake_lookup

        result = call_action("dga_get_package_stats", id=dataset["id"])
        assert result == {"2022-06": {"views": 18, "downloads": 9}}
