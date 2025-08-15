from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk


def gmd_extractor(pkg_id: str) -> dict[str, Any]:
    pkg_dict = tk.get_action("package_show")(None, {"id": pkg_id})
    owner_org = tk.h.get_organization(pkg_dict.get("owner_org")) or {}
    ident_citation = {
        "title": pkg_dict.get("title"),
        "edition_date": pkg_dict.get("metadata_modified"),
        "identifier": pkg_dict["id"],
        "teamsite": False,
        "responsible": {
            "org": owner_org,
            "position": "Data Broker",
            "role": "Custodian",
        },
    }
    return {
        "pkg_dict": pkg_dict,
        "datum_label": None,
        "owner_org": owner_org,
        "keywords": [tag["display_name"] for tag in pkg_dict["tags"]],
        "spatial_box": tk.h.spatial_bound(pkg_dict.get("spatial")),
        "vex": {},
        "ident_citation": ident_citation,
        "reports": [],
        "license_id": pkg_dict.get("license_id"),
        "language": pkg_dict.get("language") or "eng",
        "date_stamp": pkg_dict["metadata_created"],
        "temporal_coverage_from": pkg_dict.get("temporal_coverage_from"),
        "temporal_coverage_to": pkg_dict.get("temporal_coverage_to"),
    }
