import json
import os
from typing import Any

import pytest

import ckan.plugins.toolkit as tk


@pytest.mark.usefixtures("with_plugins")
class TestGetDgaMenuHelper:
    def _load_response(self, file_name: str) -> Any:
        with open(os.path.join(os.path.dirname(__file__), file_name)) as file:
            return json.load(file)

    def test_dga_get_menu(self):
        assert (
            tk.h.dga_get_menu("site")
            == self._load_response("responses/menu_site.json")["items"]
        )


@pytest.mark.usefixtures("with_plugins")
class TestIsLicenseOpenHelper:
    def test_is_license_open(self):
        assert tk.h.dga_is_license_open("cc-by-4.0")
        assert not tk.h.dga_is_license_open("cc-nc")
