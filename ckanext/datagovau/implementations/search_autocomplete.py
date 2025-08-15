from __future__ import annotations

import ckan.plugins as p
import ckan.plugins.toolkit as tk

from ckanext.search_autocomplete.interfaces import ISearchAutocomplete


class SearchAutocomplete(p.SingletonPlugin):
    p.implements(ISearchAutocomplete, inherit=True)

    def get_categories(self):
        return {
            "organization": tk._("Organisations"),
            "groups": tk._("Groups"),
            "tags": tk._("Tags"),
            "res_format": tk._("Formats"),
            "license_id": tk._("Licenses"),
        }
