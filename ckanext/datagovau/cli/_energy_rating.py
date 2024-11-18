from __future__ import annotations

import logging
import os
from urllib.parse import urlsplit

import ckan.plugins.toolkit as tk

from ckanext.datagovau.utils import download

log = logging.getLogger(__name__)

_energy_pkgs = {
    "energy-rating-for-household-appliances": {
        "air conditioners": 64,
        "clothes dryers": 35,
        "clothes washers": 49,
        "computer monitors": 74,
        "dishwashers": 41,
        "fridges and freezers": 28,
        "televisions": 32,
    },
    "energy-rating-data-for-household-appliances-non-labelled-products": {
        "air conditioners": 64,
        "ballasts": 51,
        "chillers": 59,
        "close control air conditioners": 60,
        "commercial refrigerators": 37,
        "compact fluorescent lamps": 61,
        "computers": 73,
        "distribution transformers": 38,
        "electric motors": 54,
        "elv lighting converter/transformer": 39,
        "external power supply": 55,
        "hot water heaters (electric)": 58,
        "hot water heaters (gas)": 62,
        "incandescent lamps": 40,
        "linear fluorescent lamps": 34,
        "set top boxes": 33,
    },
}


def fetch(category, filename):
    url = f"http://reg.energyrating.gov.au/comparator/product_types/{category}/search/"
    log.info("Download %s into %s", url, filename)
    resp = download(
        url,
        filename,
        params={"export_format": "csv"},
        headers={"User-Agent": "Mozilla/4.0 (compatible; data.gov.au webspider)"},
    )
    return resp.headers.get("Content-Disposition", "").split("filename=")[-1].strip(
        "\"'"
    ) or os.path.basename(urlsplit(url)[2])


def energy_resources():
    user = tk.get_action("get_site_user")({"ignore_auth": True}, {})

    for name, categories in _energy_pkgs.items():
        try:
            pkg = tk.get_action("package_show")({"user": user["name"]}, {"id": name})
        except tk.ObjectNotFound:
            log.error("Energy package %s not found", name)
            continue

        for resource in pkg["resources"]:
            resource_category = resource["name"].split("-")[0].strip().lower()
            if resource_category not in categories:
                log.info("Resource %s is not an energy resource", resource["id"])
                continue

            yield resource, categories[resource_category]
