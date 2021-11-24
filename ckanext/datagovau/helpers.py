from __future__ import annotations

import time
from typing import Any

import ckan.plugins.toolkit as tk
import ckanext.datastore.backend as datastore_backend
import feedparser

from ckanext.toolbelt.decorators import Cache, Collector
import ckanext.agls.utils as agls_utils

from . import types

helper, get_helpers = Collector("dga").split()
cache = Cache(duration=600)


@helper
# @cache
def get_ddg_site_statistics() -> types.DdgStatistics:
    package_search = tk.get_action("package_search")
    total = package_search({}, {"rows": 0})["count"]
    unpublished = package_search({}, {"fq": "unpublished:true", "rows": 0})[
        "count"
    ]
    open_count = package_search({}, {"fq": "isopen:true", "rows": 0})["count"]
    api_count = package_search(
        {},
        {
            "fq": "(res_extras_datastore_active:true OR res_format:WMS)",
            "rows": 0,
        },
    )["count"]

    return types.DdgStatistics(
        dataset_count=total,
        unpub_data_count=unpublished,
        open_count=open_count,
        api_count=api_count,
    )


@helper
def blogfeed():
    d = feedparser.parse("https://blog.data.gov.au/blogs/rss.xml")
    for entry in d.entries:
        entry.date = time.strftime("%a, %d %b %Y", entry.published_parsed)
    return d


@helper
def geospatial_topics(_field: dict[str, Any]) -> types.SchemingChoices:
    return [{"value": t, "label": t} for t in agls_utils.geospatial_topics()]


@helper
def fields_of_research(_field: dict[str, Any]) -> types.SchemingChoices:
    return [{"value": t, "label": t} for t in agls_utils.fields_of_research()]


@helper
def agift_themes(_field: dict[str, Any]) -> types.SchemingChoices:
    groups = tk.get_action("group_list")({}, {"all_fields": True})
    return [{"value": g["id"], "label": g["display_name"]} for g in groups]
