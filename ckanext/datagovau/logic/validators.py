from __future__ import annotations

import datetime
import json
import logging
import mimetypes
import os
from typing import Any
from urllib.parse import urlparse

import geomet
import requests
from six import string_types

import ckan.plugins.toolkit as tk
from ckan import model, types
from ckan.lib.navl.dictization_functions import Missing, unflatten

from ckanext.agls.utils import details_for_gaz_id
from ckanext.harvest.model import HarvestObject

log = logging.getLogger(__name__)


def dga_spatial_from_coverage(
    key: types.FlattenKey,
    data: types.FlattenDataDict,
    errors: types.FlattenErrorDict,
    context: types.Context,
):
    details = []
    coverage = data[("spatial_coverage",)]
    if not coverage:
        data[key] = ""
        return
    id_ = coverage.split(":")[0]
    try:
        details = details_for_gaz_id(id_)
    except (KeyError, requests.RequestException) as e:
        log.warning("Cannot get details for GazId %s: %s", id_, e)

    valid_geojson = True
    try:
        coverage_json = json.loads(coverage)
        geomet.wkt.dumps(coverage_json)
    except (ValueError, TypeError, geomet.InvalidGeoJSONException):
        valid_geojson = False
        log.warning("Entered coverage is not a valid GeoJSON")

    if details:
        data[key] = details["geojson"]
    elif valid_geojson:
        data[key] = coverage
    elif data.get(("id",)):
        try:
            data_dict = tk.get_action("package_show")(
                tk.fresh_context(context), {"id": data[("id",)]}
            )
        except tk.ObjectNotFound:
            data[("spatial_coverage",)] = ""
        else:
            data[("spatial_coverage",)] = data_dict.get("spatial_coverage")
            data[key] = data_dict.get("spatial")
    else:
        errors[("spatial_coverage",)].append(
            tk._("Entered value cannot be converted into a spatial object")
        )


def dga_default_now(value: Any):
    if value:
        return value

    return datetime.datetime.now().isoformat()


def user_password_validator(
    key: types.FlattenKey,
    data: types.FlattenDataDict,
    errors: types.FlattenErrorDict,
    context: types.Context,
):
    base_pass_text = (
        "Password should have at least 8 characters "
        "and use of at least three of the following "
        "character sets in passphrases: "
        "lower-case alphabetical characters (a-z), "
        "upper-case alphabetical characters (A-Z), "
        "numeric characters (0-9) or"
        "special characters"
    )

    special_characters = r"!@#$%^&*()-+?_=,<>/"
    value = data[key]

    if isinstance(value, Missing):
        return

    if not isinstance(value, string_types):
        errors[("password",)].append(tk._(base_pass_text))
    elif value == "":
        return
    elif len(value) < 8:
        errors[("password",)].append(tk._(base_pass_text))

    used_char_sets = 0

    if len([x for x in value if x.islower()]):
        used_char_sets += 1
    if len([x for x in value if x.isupper()]):
        used_char_sets += 1
    if len([x for x in value if x.isdigit()]):
        used_char_sets += 1
    if len([x for x in value if x in special_characters]):
        used_char_sets += 1

    if used_char_sets < 3:
        errors[("password",)].append(tk._(base_pass_text))


def dga_tag_count_validator(max_tags: str):
    """Checks if number of tags doesn't exceed maximum limit."""

    def callable(value: str):
        tags = [tag.strip() for tag in value.split(",")]
        if len(tags) > int(max_tags):
            raise tk.Invalid(
                f"Too many tags. Maximum {max_tags} tags allowed, got {len(tags)}"
            )
        return value

    return callable


def dga_detect_harvest_source(
    key: types.FlattenKey,
    data: types.FlattenDataDict,
    errors: types.FlattenErrorDict,
    context: types.Context,
):
    """Compute original source of harvested dataset."""
    pkg = unflatten(data)

    harvest_object = (
        model.Session.query(HarvestObject)
        .filter(HarvestObject.package_id == pkg["id"])
        .filter(
            HarvestObject.current == True  # noqa
        )
        .order_by(HarvestObject.import_finished.desc())
        .first()
    )

    if not harvest_object:
        # No harvest object found, indicating the package is local
        # (not harvested from an external source)
        data[key] = tk.h.dga_default_original_source(pkg)
        return

    harvest_source_title = harvest_object.source.title
    harvest_source_id = harvest_object.source.id

    try:
        # Harvest source was probably removed without proper cleaning and we are
        # dealing with an orphan
        harvest_source = tk.get_action("harvest_source_show")(
            {}, {"id": harvest_source_id}
        )
    except tk.ObjectNotFound:
        data[key] = tk.h.dga_default_original_source(pkg)
        return

    dataset_href = f"{harvest_source['url'].rstrip('/')}/dataset/{pkg['name']}"

    if harvest_source.get("source_type") == "ckan":
        data[key] = {
            "site_url": harvest_source["url"],
            "href": dataset_href,
            "title": harvest_source_title,
        }
        return

    content = harvest_object.content
    if isinstance(content, str):
        try:
            content_dict: dict[str, Any] = json.loads(content)
        except ValueError:
            log.error(tk._("Could not parse as valid JSON"))
            content_dict = {}

        if harvest_source.get("source_type") == "csiro":
            landing_page = tk.h.get_pkg_dict_extra(content_dict, "landingPage")
            dataset_href = landing_page.get("href", "")

        elif harvest_source.get("source_type") == "basket_dcat_json":
            dataset_href = content_dict.get("landingPage", "")

    parsed_href = urlparse(dataset_href)

    data[key] = {
        "site_url": parsed_href.scheme + "://" + parsed_href.netloc,
        "href": dataset_href,
        "title": harvest_source_title,
    }


def dga_categorize_dataset(
    key: types.FlattenKey,
    data: types.FlattenDataDict,
    errors: types.FlattenErrorDict,
    context: types.Context,
):
    """Categorize datasets based on comprehensive rules.

    Rules:
    - Datasets with 'harvest*' prefix in field names or extras: score 2
    - Datasets with fields matching 'syndicate' pattern: score 0
    - All other datasets: score 1
    """
    all_keys = {k[-1] for k in data if isinstance(k, tuple) and k[-1]}
    extras_keys = {
        data[k]
        for k in data
        if isinstance(k, tuple) and len(k) >= 3 and k[0] == "extras" and k[2] == "key"
    }
    all_keys.update(extras_keys)

    # Check for 'harvest' fields (highest priority)
    if any(k.startswith("harvest") for k in all_keys):
        data[key] = 2
        return

    # Check for 'syndicate' pattern (lowest priority)
    if any("syndicate" in k for k in all_keys):
        data[key] = 0
        return

    # Default score
    data[key] = 1


def dga_resource_format(
    key: types.FlattenKey,
    data: types.FlattenDataDict,
    errors: types.FlattenErrorDict,
    context: types.Context,
):
    filepath = data[key]
    parsed = urlparse(filepath)

    if parsed.scheme:
        # URL that contains only domain name receives HTML format
        filepath = os.path.basename(parsed.path) or "index.html"
        name, ext = os.path.splitext(filepath)
        # URL without an explicit extension is treated as if it contains format
        # as a last path segment. I.e, `/path/csv` or `/another/txt`
        if not ext:
            filepath = f"index.{name}"

    mime_type, _ = mimetypes.guess_type(filepath)
    # URL without obvious format falls into HTML category, but uploads do not
    # follow this strategy.
    if not mime_type and parsed.scheme:
        mime_type = "text/html"

    format_key = key[:-1] + ("format",)
    if (
        mime_type
        and not data.get(format_key)
        and (extension := mimetypes.guess_extension(mime_type))
    ):
        data[format_key] = extension.lstrip(".").upper()

    if ("id",) not in data:
        return
    package = model.Package.get(data[("id",)])
    if not package:
        return

    if mime_type == "application/pdf":
        formats = [res.format.lower() for res in package.resources if res.format]

        if not formats:
            errors[key].append(
                tk._("Upload at least one file of any format before uploading PDF.")
            )
