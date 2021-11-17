import logging
import os
import time

import ckan.model as model
import feedparser
from ckan.lib import formatters, uploader
import ckan.plugins.toolkit as tk
import ckanext.datastore.backend as datastore_backend
from ckanext.toolbelt.decorators import Cache, Collector

helper, get_helpers = Collector("dga").split()

cache = Cache(600)

log = logging.getLogger(__name__)


@helper("get_user_datasets")
def get_user_datasets(user_dict):
    # Need to test packages carefully to make sure they haven't been purged from the DB (like what happens
    # in a harvest purge), as the activity list does not have the associated entries cleaned out.
    # [SXTPDFINXZCB-145]
    # TODO: not the fastest way, right?
    def pkg_test(input):
        try:
            result = input["data"].get("package")

            # Test just to catch an exception if need be
            data = tk.get_action("package_show")(
                context, {"id": input["data"]["package"]["id"]}
            )
        except:
            result = False
        return result

    context = {"model": model, "user": user_dict["name"]}
    created_datasets_list = user_dict["datasets"]

    active_datasets_list = [
        tk.get_action("package_show")(
            context.copy(), {"id": x["data"]["package"]["id"]}
        )
        for x in tk.get_action("user_activity_list")(context.copy(), {"id": user_dict["id"]})
        if pkg_test(x)
    ]
    raw_list = sorted(
        active_datasets_list + created_datasets_list,
        key=lambda pkg: pkg["state"],
    )
    filtered_dict = {}
    for dataset in raw_list:
        if dataset["id"] not in filtered_dict.keys():
            filtered_dict[dataset["id"]] = dataset
    return filtered_dict.values()


@helper("get_user_datasets_public")
def get_user_datasets_public(user_dict):
    return [
        pkg for pkg in get_user_datasets(user_dict) if pkg["state"] == "active"
    ]


@helper("get_ddg_site_statistics")
@cache
def get_ddg_site_statistics():
    stats = {
        "dataset_count": tk.get_action("package_search")({}, {"rows": 0})[
            "count"
        ]
    }

    for fDict in tk.get_action("package_search")(
        {}, {"facet.field": ["unpublished"], "rows": 0}
    )["search_facets"]["unpublished"]["items"]:
        if fDict["name"] == "Unpublished datasets":
            stats["unpub_data_count"] = fDict["count"]
            break

    stats["open_count"] = tk.get_action("package_search")(
        {}, {"fq": "isopen:true", "rows": 0}
    )["count"]

    stats["api_count"] = tk.get_action("resource_search")(
        {}, {"query": ["format:wms"]}
    )["count"] + len(datastore_backend.get_all_resources_ids_in_datastore())

    if "unpub_data_count" not in stats:
        stats["unpub_data_count"] = 0

    return stats


@helper("get_resource_file_size")
def get_resource_file_size(rsc):
    if rsc.get("url_type") == "upload":
        upload = uploader.ResourceUpload(rsc)
        value = None
        try:
            value = os.path.getsize(upload.get_path(rsc["id"]))
            value = formatters.localised_filesize(int(value))
        except Exception:
            # Sometimes values that can't be converted to ints can sneak
            # into the db. In this case, just leave them as they are.
            pass
        return value
    return None


@helper("blogfeed")
def blogfeed():
    d = feedparser.parse("https://blog.data.gov.au/blogs/rss.xml")
    for entry in d.entries:
        entry.date = time.strftime("%a, %d %b %Y", entry.published_parsed)
    return d


@helper
def group_tree_section(grp_id, grp_type):
    result = tk.get_action("group_tree_section")(
        {}, {"id": grp_id, "type": grp_type}
    )
    return result
