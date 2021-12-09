from __future__ import annotations

import time
from typing import Any, Optional

import ckan.plugins.toolkit as tk
import ckanext.datastore.backend as datastore_backend
import feedparser

from ckanext.toolbelt.decorators import Cache, Collector
import ckanext.agls.utils as agls_utils

from . import types

helper, get_helpers = Collector("dga").split()
cache = Cache(duration=600)
 
import ckan.logic as logic
import logging
log = logging.getLogger('ckanext_datagovau')

@helper
@cache
def get_ddg_site_statistics():

    stats = {'dataset_count': logic.get_action('package_search')({}, {"rows": 0})['count']}

    tmpRS=logic.get_action('package_search')({}, {"facet.field": ["unpublished"], "rows": 0})

    stats['unpub_data_count']=tmpRS['facets']['unpublished']['True']

    stats['open_count'] = logic.get_action('package_search')({}, {"fq": "isopen:true", "rows": 1})['count']

    stats['api_count'] = logic.get_action('resource_search')({}, {"query": ["format:wms"]})['count'] + len(
        datastore_backend.get_all_resources_ids_in_datastore())

    if 'unpub_data_count' not in stats:
        stats['unpub_data_count'] = 0

    return stats

@cache
def _api_count():
    return tk.get_action("resource_search")(
        {}, {"query": ["format:wms"], "limit": 0}
    )["count"] + len(datastore_backend.get_all_resources_ids_in_datastore())


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
    empty = {
        "value": "", "label": "Please Select"
    }
    return [empty] + [{"value": g["id"], "label": g["display_name"]} for g in groups]


_stat_labels = {
    "api": "API enabled resources",
    "open": "Openly licenced datasets",
    "unpublished": "Unpublished datasets",
}


@helper
def stat_group_to_facet_label(group: str) -> Optional[str]:
    return _stat_labels.get(group)
