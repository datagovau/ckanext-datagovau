from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Callable, Literal, cast

import sqlalchemy as sa

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.lib import munge
from ckan.lib.helpers import Page
from ckan.plugins import plugin_loaded

import ckanext.agls.utils as agls_utils
from ckanext.toolbelt.decorators import Cache

from ckanext.datagovau.utils.dataset_duplicate_handler import find_copies
from ckanext.datagovau.utils.lga import lga_names

from . import config, develop

cache = Cache(duration=600)

log = logging.getLogger(__name__)
RE_SWAP_CASE = re.compile("(?<=[a-z])(?=[A-Z])")


def dga_geospatial_topics(_field: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform AGLS topics into select options."""
    topics = cast("list[str]", agls_utils.geospatial_topics())
    return [{"value": t, "label": t} for t in topics]


def dga_fields_of_research(_field: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform AGLS fields of research into select options."""
    fields = cast("list[str]", agls_utils.fields_of_research())
    return [{"value": t, "label": t} for t in fields]


def dga_agift_themes(_field: dict[str, Any]) -> list[dict[str, Any]]:
    """Transform groups into select options."""
    groups = tk.get_action("group_list")({}, {"all_fields": True})
    empty = {"value": "", "label": "Please Select"}
    return [empty] + [{"value": g["id"], "label": g["display_name"]} for g in groups]


@tk.chained_helper
def advanced_search_form_config(_next_helper: Any) -> dict[str, Any]:
    """Configure advanced search filters."""
    if tk.get_endpoint() == ("organization", "read"):
        org_dict = tk.get_action("organization_show")(
            {}, {"id": tk.request.path.split("/")[-1]}
        )
        fq = f"owner_org:{org_dict['id']}"

        if tk.request.args.get("include_children"):
            children_orgs = model.Group.get(
                org_dict["id"]
            ).get_children_group_hierarchy(type="organization")
            children_names = [org[1] for org in children_orgs]
            fq += " OR {}".format(" OR ".join(children_names))
    else:
        fq = ""

    facets = tk.get_action("package_search")(
        {},
        {
            "fq": fq,
            "rows": 0,
            "facet.field": ["organization", "res_format", "license_id", "tags"],
            "facet.mincount": 1,
        },
    )["search_facets"]

    definition: dict[str, Any] = {
        "text": {
            "type": "text",
            "label": "Any attribute",
            "placeholder": "Enter a search term",
            "default": True,
        },
        "title": {
            "type": "text",
            "label": "Dataset title",
            "placeholder": "Enter a search term",
        },
        "notes": {
            "type": "text",
            "label": "Description",
            "placeholder": "Enter a search term",
        },
        "organization": {
            "type": "select",
            "label": "Organisation",
            "placeholder": "Filter datasets by organisation",
            "options": _sort_facet_options(facets["organization"]["items"]),
        },
        "res_format": {
            "type": "select",
            "label": "Format",
            "placeholder": "Filter data by visibility",
            "options": _sort_facet_options(facets["res_format"]["items"]),
        },
        "license_id": {
            "type": "select",
            "label": "Licenses",
            "placeholder": "Filter data by visibility",
            "options": _sort_facet_options(facets["license_id"]["items"]),
        },
        "tags": {
            "type": "text",
            "label": "Tags",
            "placeholder": "Enter a search term",
        },
        "extras_res_attachment": {
            "type": "text",
            "label": "Document attachments",
            "placeholder": "Enter a search term",
        },
    }

    order = list(definition)
    return {
        "definitions": definition,
        "order": order,
    }


def _sort_facet_options(facet_items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Convert CKAN facet items to [{'value', 'label'}] sorted by label."""
    return sorted(
        (
            {"value": item["name"], "label": item["display_name"]}
            for item in facet_items
        ),
        key=lambda opt: opt["label"].lower(),
    )


def dga_get_original_harvest_source(pkg: dict[str, Any]) -> dict[str, Any]:
    """Fetches the original harvest source's landing page URL and title."""
    if source := pkg.get("original_harvest_source"):
        return source

    return tk.h.dga_default_original_source(pkg)


def dga_default_original_source(pkg: dict[str, Any]) -> dict[str, Any]:
    """Default harvest source that points to the current portal."""
    return {
        "site_url": tk.h.url_for("dataset.search", _external=True),
        "href": tk.h.url_for("dataset.read", id=pkg["name"], _external=True),
        "title": "data.gov.au",
    }


def dga_facet_to_json(
    facets: list[dict[str, Any]],
    name: str | None = None,
    extras: dict[str, Any] | None = None,
    alternative_url: str | None = None,
):
    """Convert facet items to JSON with dynamically generated URLs.

    Returns:
        JSON string of facet items with added href for each item.
    """
    enhanced_facets = []
    for item in facets:
        enhanced_item = item.copy()

        if item.get("active"):
            enhanced_item["href"] = tk.h.remove_url_param(
                name, item["name"], extras=extras, alternative_url=alternative_url
            )
        else:
            enhanced_item["href"] = tk.h.add_url_param(
                new_params={name: item["name"]},
                extras=extras,
                alternative_url=alternative_url,
            )
            if enhanced_item["display_name"] == "notspecified":
                enhanced_item["display_name"] = tk._("Not Specified")

        enhanced_facets.append(enhanced_item)

    return json.dumps(enhanced_facets)


def dga_detect_duplicates(package_dict: dict[str, Any]) -> dict[str, Any]:
    """Detect duplicates for a dataset."""
    return find_copies(package_dict)


def dga_generate_page_unique_class() -> str:
    """Build a unique css class for each page."""
    return munge.munge_name(f"dga-{tk.request.endpoint}")


def dga_get_menu(
    type: Literal[
        "main",
        "footer",
        "publishers",
        "developers",
        "site",
    ],
) -> list[dict[str, Any]]:
    """Fetch menu item from Drupal side.

    Returns:
        Menu items with label and href fields
    """
    menu = None
    if plugin_loaded("drupal_api") and (
        menu_dict := tk.h.drupal_api_custom_endpoint(f"/api/resource/menu/{type}")
    ):
        menu = menu_dict.get("items", [])

    if not menu:
        return develop.static_header_links(type)

    return menu


def dga_get_check_link_pager(collection: Any) -> Page:
    """Replace the pager from the check-link report with a CKAN default pager."""
    return Page(
        collection=[],
        page=collection.pager.page,
        url=_check_link_pager_url_generator,
        item_count=collection.data.total,
        items_per_page=collection.pager.size,
        rows_per_page=collection.pager.size,
        collection_name=collection.name,
        **(tk.request.view_args or {}),
    )


def _check_link_pager_url_generator(**kwargs: Any) -> str:
    """URL generator for the check-link report pager."""
    args = [tk.request.endpoint]
    kwargs[f"{kwargs['collection_name']}:page"] = kwargs["page"]
    kwargs[f"{kwargs['collection_name']}:rows_per_page"] = kwargs["rows_per_page"]
    kwargs.pop("page")
    kwargs.pop("rows_per_page")
    kwargs.pop("collection_name")

    return tk.url_for(*args, **kwargs)


def dga_search_autocomplete_needed() -> bool:
    """Check if the search autocomplete is needed on the current page."""
    return tk.get_endpoint() in [
        ("dataset", "search"),
        ("organization", "read"),
        ("group", "read"),
    ]


def dga_search_tweaks_needed() -> bool:
    """Check if the search tweaks are needed on the current page."""
    return tk.get_endpoint() not in [("organization", "index"), ("group", "index")]


def dga_get_fq_for_search_autocomplete(facets: dict[str, Any]) -> str:
    """Generate fq string for search autocomplete on the organization page.

    Its need to restrict the search to the current organization and its child
    organizations on the organization read page. On the organization page we
    have a facet dictionary that contains the current organization and its child
    organizations.
    """
    if tk.get_endpoint() not in [("organization", "read")]:
        return ""
    try:
        orgs = facets["search"]["organization"]["items"]
    except (KeyError, IndexError):
        return ""

    org_ids = [
        tk.get_action("organization_show")({"ignore_auth": True}, {"id": org["name"]})[
            "id"
        ]
        for org in orgs
    ]

    return f"owner_org:({' OR '.join(org_ids)})"


def dga_user_can_suggest_dataset() -> bool:
    """Check if the user can suggest a dataset."""
    if config.anonymous_suggestion():
        return True

    return tk.current_user.is_authenticated


def dga_user_can_ask_question() -> bool:
    """Check if the user can ask a question."""
    if config.anonymous_question():
        return True

    return tk.current_user.is_authenticated


def dga_get_organization_image_url(organization_id: str) -> str:
    """Get the URL for an organization image."""
    organization = model.Group.get(organization_id)

    if not organization or not organization.image_url:
        return ""

    if organization.image_url.startswith("http"):
        return organization.image_url

    image_url = munge.munge_filename_legacy(organization.image_url)

    return tk.h.url_for_static(f"uploads/group/{image_url}", qualified=True)


@tk.chained_helper
def new_activities(next_helper: Callable[[], int | None]) -> int | None:
    """Cache the number of new activities."""

    # keep this unused `_user` argument to show every user his own
    # counter. Without this argument there will be the one global counter that
    # is shown to every user
    @cache
    def _get_new_activities_count(_user: str):
        return next_helper()

    return _get_new_activities_count(tk.current_user.name)


@tk.chained_helper
def group_tree_parents(_: Any, group_id: str) -> list[model.Group]:
    """Replace group_tree_parents with a more time efficient one."""
    if group := model.Group.get(group_id):
        return group.get_parent_group_hierarchy(group.type)

    return []


def dga_paginate_items(items: list[dict[str, Any]]) -> Page:
    """Returns a paginated Page object for a given list of items."""
    items_per_page = tk.config["ckan.datasets_per_page"]
    page = tk.h.get_page_number(tk.request.args)
    total_count = len(items)
    offset = (page - 1) * items_per_page
    paginated_items = items[offset : offset + items_per_page]

    page = Page(
        collection=items,
        page=page,
        url=tk.h.pager_url,
        item_count=total_count,
        items_per_page=items_per_page,
    )

    page.items = paginated_items
    return page


def dga_lga_names() -> list[Any]:
    """Produce list of LGA names for spatial search widget."""
    return lga_names()


def dga_humanize_geospatial_topic(topic: str) -> str:
    """Transform camelcased topic into capitalized form with separate words."""
    return RE_SWAP_CASE.sub(" ", topic).capitalize()


def dga_organizations_available(user: str) -> list[dict[str, Any]]:
    """Add extras from scheming to displayed organizations."""
    orgs = tk.h.organizations_available(
        include_dataset_count=True,
        include_member_count=True,
        user=user,
    )

    # references to list item for quick access during extra field assignment
    mmap = {org["id"]: org for org in orgs}

    stmt = (
        sa.select(
            model.Group.id,
            model.GroupExtra.value.label("jurisdiction"),
        )
        .select_from(model.Group)
        .join(model.GroupExtra)
        .where(model.GroupExtra.key == "jurisdiction", model.Group.id.in_(mmap))
    )
    for id, jurisdiction in model.Session.execute(stmt):
        mmap[id]["jurisdiction"] = jurisdiction

    return orgs


def dga_is_license_open(license_id: str) -> bool:
    register = model.Package.get_license_register()
    if license := register.get(license_id):
        return license.od_conformance

    return False


def dga_get_valid_extent(*args: str | None) -> str | None:
    """Check arguments to be valid GeoJSON and return the first valid one."""

    def is_valid_geojson(s: str | None) -> bool:
        if not isinstance(s, str):
            return False
        try:
            data = json.loads(s)
            return isinstance(data, dict) and "type" in data and "coordinates" in data
        except json.JSONDecodeError:
            return False

    for value in args:
        if is_valid_geojson(value):
            return value


def dga_hash_string(value: str) -> str:
    """Return a short, deterministic hash (first 8 chars of md5)."""
    if not isinstance(value, str):
        value = str(value)

    return hashlib.md5(value.encode("utf-8")).hexdigest()[:8]


def dga_pretty_json(value: str) -> str:
    return json.dumps(json.loads(value), indent=2, sort_keys=True)
