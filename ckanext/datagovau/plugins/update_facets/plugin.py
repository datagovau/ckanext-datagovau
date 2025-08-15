from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk


class DgaUpdateFacets(p.SingletonPlugin):
    p.implements(p.IFacets, inherit=True)

    def dataset_facets(
        self, facets_dict: dict[str, Any], package_type: str
    ) -> dict[str, Any]:
        if package_type != "harvest":
            return facets_dict
        return {
            "organization": tk._("Organisation"),
            "frequency": tk._("Frequency"),
            "source_type": tk._("Type"),
        }
