from __future__ import annotations

import contextlib
import json
import re
import sys
import uuid
from datetime import datetime

from dateutil.parser import ParserError, parse
from shapely import geometry

import ckan.plugins.toolkit as tk
from ckan.authz import get_local_functions
from ckan.lib import munge
from ckan.lib.helpers import markdown_extract

from ckanext.transmute.types import Field


def get_transmutators():
    members = dict(get_local_functions(sys.modules[__name__]))
    members.pop(get_transmutators.__name__)
    return members


def dga_tsm_name_from_url(field: Field):
    """Extract last part of landing page to use it as
    dataset name [100 characters or less]"""
    delimiter = "::" if "::" in field.value else "/"
    field.value = field.value.rsplit(delimiter, 1)[-1][:100]
    return field


def dga_tsm_words_into_tags(field: Field):
    """Transform list of words into list of tag dictionaries."""
    field.value = [{"name": munge.munge_tag(tag)} for tag in field.value]
    return field


def dga_tsm_url_into_license(field: Field):
    """Convert licence URL into licence ID"""
    field.value = "other"
    return field


def dga_tsm_contact_name(field: Field):
    """Extract author name from contact point dictionary."""
    field.value = field.value["fn"]
    return field


def dga_tsm_contact_email(field: Field):
    """Extract author email from contact point dictionary."""
    field.value = field.value.get("hasEmail", "unknown")
    if field.value.startswith("mailto:"):
        field.value = field.value[7:]

    return field


def dga_tsm_parse_issued_date(field: Field):
    """Parse temporal_coverage_from date string to a datetime object."""
    field.value = parse(field.value)
    return field


def dga_tsm_parse_description(field: Field):
    """
    Parse and convert an HTML description field to plain text.
    Sets default value if the field is empty or invalid.
    """
    # Set of values to be treated as placeholders
    invalid_values = {"null", "{{description}}"}

    if not field.value or field.value in invalid_values:
        field.value = "No description available."
    else:
        field.value = markdown_extract(field.value, extract_length=0)
    return field


def dga_tsm_from_extras(field: Field, key: str):
    """Replace field value with the give extra value."""
    for extra in field.data.get("extras", []):
        if extra["key"] == key:
            field.value = extra["value"]
            break

    return field


def dga_tsm_parse_spatial(field: Field):
    """Parse and convert a spatial coverage string to GeoJSON format."""

    # Check if the value is empty or contains the compute property placeholder
    spatial_placeholders = {"extent:computeSpatialProperty", "extent"}
    if not field.value or any(
        placeholder in field.value for placeholder in spatial_placeholders
    ):
        field.value = ""
        return field

    if isinstance(field.value, str):
        coords = [float(x) for x in field.value.split(",")]

        # Create a GeoJSON polygon from the bounding box
        geojson = {
            "type": "Polygon",
            "coordinates": [
                [
                    [coords[0], coords[1]],
                    [coords[0], coords[3]],
                    [coords[2], coords[3]],
                    [coords[2], coords[1]],
                    [coords[0], coords[1]],
                ]
            ],
        }
    elif isinstance(field.value, dict) and field.value.get("type") == "envelope":
        coordinates = field.value["coordinates"]
        geojson = {
            "type": "Polygon",
            "coordinates": [
                [
                    [coordinates[0][0], coordinates[0][1]],
                    [coordinates[0][0], coordinates[1][1]],
                    [coordinates[1][0], coordinates[1][1]],
                    [coordinates[1][0], coordinates[0][1]],
                    [coordinates[0][0], coordinates[0][1]],
                ]
            ],
        }

    field.value = json.dumps(geojson)
    return field


def dga_tsm_parse_date(field: Field):
    """Transform non-strict date string into ISO date."""
    if isinstance(field.value, str):
        with contextlib.suppress(ParserError):
            field.value = parse(field.value, default=datetime(2020, 1, 1))
    return field


def dga_tsm_southern_grampians_parse_license(field: Field):
    """
    Normalize license strings to a standard format; all values
    contain 'CC BY'."""
    license_mapping = {
        "CC BY": "cc-by",
    }
    field.value = license_mapping.get(field.value, "other")
    return field


def dga_tsm_southern_grampians_contact_name(field: Field):
    """
    Set the contact name to 'Southern Grampians Shire' since all values
    contain '<Nobody>'.
    """
    field.value = "Southern Grampians Shire"
    return field


def dga_tsm_southern_grampians_from_url(field: Field):
    """
    Extract the second-to-last segment from the landing page URL and prepend a
    'southern-grampians-' prefix to use it as the dataset name. This ensures
    uniqueness in naming to prevent ValidationError during creation.
    """
    prefix = "southern-grampians-"
    field.value = prefix + field.value.rsplit("/", 2)[-2]
    return field


def dga_tsm_southern_grampians_parse_language(field: Field):
    """
    Convert the language field value to uppercase.
    If the value is a list (containing only one element),
    extract the first element for conversion.
    """
    if isinstance(field.value, list):
        field.value = field.value[0].upper()
    field.value = field.value.upper()
    return field


def dga_tsm_qld_parse_resource_size(field: Field):
    """
    Parses a resource size field and attempts to convert its value to an integer.
    If the value contains non-numeric characters (e.g., "MiB", "KiB"), it sets the
    value to an empty string to avoid a ValidationError for invalid integers.
    """
    try:
        field.value = int(field.value)
    except:
        field.value = ""
    return field


def dga_tsm_qld_resource_id(field: Field):
    """
    Validates the resource ID. If the value is not a valid UUID v4,
    it sets the value to an empty string.

    Many QLD resources have invalid ID formats, which will cause failures
    in CKAN-2.11 due to the addition of the uuid_validator.
    """
    try:
        uuid.UUID(field.value, version=4)
    except ValueError:
        field.value = ""
    return field


def dga_tsm_sa_parse_spatial_coverage(field: Field):
    """
    Maps location names to their corresponding codes:
    - "South Australia" -> "SA0062407: South Australia"

    # TODO: Add more location mappings as needed.
    """
    field.value = "SA0062407: South Australia"
    return field


def dga_tsm_sa_temporal_coverage(field: Field):
    """
    Converts various temporal coverage date formats (both 'from' and 'to')
    to a standardized YYYY-MM-DD string.

    Handles date formats such as:
    - current (treated as an empty string)
    - DD-MM-YYYY
    - YYYY
    - Month YYYY (e.g., January 1970)
    - 2007/2008

    If parsing fails or date is invalid:
    - For 'temporal_coverage_from', sets the value to 'metadata_created' as a fallback.
    - For 'temporal_coverage_to', sets the value to an empty string.
    """
    fallback_value = (
        field.data["metadata_created"]
        if field.field_name == "temporal_coverage_from"
        else ""
    )
    if not field.value or field.value.lower() == "current":
        field.value = fallback_value
        return field

    try:
        parsed_date = parse(field.value, fuzzy=True)
        field.value = parsed_date.strftime("%Y-%m-%d")
    except (ParserError, ValueError):
        field.value = fallback_value

    return field


def dga_tsm_sa_geospatial_topic(field: Field):
    """
    Handles values as 'Environment, Inland waters',
    causing unexpected choice errors. If there are multiple values,
    they are stored as a list. Single values remain as a string.
    """
    if isinstance(field.value, str):
        split_values = field.value.split(",")
        if len(split_values) >= 2:
            field.value = [item.strip() for item in field.value.split(",")]
    return field


def dga_tsm_sa_author_email(field: Field):
    """
    Corrects email addresses where there are spaces in the local part
    by replacing the space with a dot.
    For example, 'alexis tindall@sa.gov.au' will be corrected to
    'alexis.tindall@sa.gov.au'.
    """
    if isinstance(field.value, str) and field.value.count("@") == 1:
        local_part, domain = field.value.split("@")
        if len(local_part.split(" ")) == 2:
            corrected_name = local_part.replace(" ", ".")
            field.value = f"{corrected_name}@{domain}"
    return field


def dga_tsm_dms_to_spatial(field: Field):
    """Convert DMS coordinates dictionary into GeoJSON string."""
    if not isinstance(field.value, dict):
        return field

    dms_pattern = re.compile(r"(\d+)°(\d+)′([\d.]+)″\s*([NSEW])")

    coordinates = []
    for attr in ["westLongitude", "southLatitude", "eastLongitude", "northLatitude"]:
        group = dms_pattern.match(field.value[attr])

        if not group:
            raise tk.Invalid(f"Invalid DMS format: {field.value}")

        degrees, minutes, seconds, direction = group.groups()
        degrees = float(degrees)
        minutes = float(minutes)
        seconds = float(seconds)

        decimal_degrees = degrees + (minutes / 60) + (seconds / 3600)

        if direction in ["S", "W"]:
            decimal_degrees *= -1

        coordinates.append(decimal_degrees)

    bbox = geometry.box(*coordinates)
    polygon = geometry.mapping(bbox)
    field.value = json.dumps(polygon)
    return field


def dga_tsm_qa_maintainer_email(field: Field):
    """
    Handles invalid email values in qld maintainer_email fields.
    If an email is invalid (e.g., "publisher-1122", "N/A"),
    it is replaced with "unknown@data.qld.gov.au"
    """
    if isinstance(field.value, str):
        field.value = field.value.strip()

    email_validator = tk.get_validator("email_validator")
    try:
        email_validator(field.value, {})
    except tk.Invalid:
        field.value = "unknown@data.qld.gov.au"
    return field


def dga_tsm_dcceew_from_url(field: Field):
    """
    Adds the "erin-" prefix to the package name to ensure uniqueness.
    Truncates the name to 100 characters if it exceeds the maximum length.
    """
    max_length: int = 100
    prefix = "erin-"

    field.value = prefix + field.value.rsplit("::", 1)[-1]
    if len(field.value) > max_length:
        field.value = field.value[:max_length]
    return field
