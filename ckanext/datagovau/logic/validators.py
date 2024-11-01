import datetime
import json
import logging

import geomet
import requests
from six import string_types

import ckan.plugins.toolkit as tk
from ckan.common import _
from ckan.lib.navl.dictization_functions import Missing

from ckanext.agls.utils import details_for_gaz_id

log = logging.getLogger(__name__)


def dga_spatial_from_coverage(key, data, errors, context):
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
    except (ValueError, geomet.InvalidGeoJSONException):
        valid_geojson = False
        log.warning("Entered coverageerage is not a valid geojson")

    if details:
        data[key] = details["geojson"]
    elif valid_geojson:
        data[key] = coverage
    elif data.get(("id",)):
        data_dict = tk.get_action("package_show")({}, {"id": data[("id",)]})
        data[("spatial_coverage",)] = data_dict.get("spatial_coverage")
        data[key] = data_dict.get("spatial")
    else:
        errors[("spatial_coverage",)].append(
            tk._("Entered value cannot be converted into a spatial object")
        )


def dga_default_now(value):
    if value:
        return value

    return datetime.datetime.now().isoformat()


def user_password_validator(key, data, errors, context):
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
        errors[("password",)].append(_(base_pass_text))
    elif value == "":
        return
    elif len(value) < 8:
        errors[("password",)].append(_(base_pass_text))

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
        errors[("password",)].append(_(base_pass_text))


def dga_tag_count_validator(max_tags: str):
    """
    Checks if number of tags doesn't exceed maximum limit.
    """
    def callable(value: str):
        tags = [tag.strip() for tag in value.split(",")]
        if len(tags) > int(max_tags):
            raise tk.Invalid(
                f"Too many tags. Maximum {max_tags} tags allowed, got {len(tags)}"
            )
        return value
    return callable
