from __future__ import annotations

import json
from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import types
from ckan.lib import jobs

from ckanext.datagovau import config
from ckanext.datagovau.geoserver_utils import delete_ingested


class PackageController(p.SingletonPlugin):
    p.implements(p.IPackageController, inherit=True)

    def before_dataset_index(self, pkg_dict: dict[str, Any]):
        if pkg_dict["type"] == "harvest":
            _index_source_type(pkg_dict)
            return pkg_dict

        pkg_dict["unpublished"] = tk.asbool(pkg_dict.get("unpublished"))
        # uploading resources to datastore will cause SOLR error
        # for multivalued field
        # inside set_datastore_active_flag action before
        # reindexing the dataset, it retrieves the data from package_show
        # therefore these two fields are not converted.
        geospatial_topic = pkg_dict.get("geospatial_topic")
        if geospatial_topic and not isinstance(geospatial_topic, str):
            pkg_dict["geospatial_topic"] = json.dumps(geospatial_topic)

        _set_extras_spatial_for_index(pkg_dict)

        return pkg_dict

    def before_dataset_search(self, search_params: dict[str, Any]):
        extras: dict[str, Any] = search_params["extras"]

        start_d = extras.get("ext_startdate")
        end_d = extras.get("ext_enddate")

        if start_d and end_d:
            fq_list: list[str] = search_params.setdefault("fq_list", [])

            fq_list.append(
                f"temporal_coverage_from:[{start_d}T00:00:00Z TO {end_d}T23:59:59Z]"
            )

        if tk.get_endpoint() == ("harvest", "search"):
            _adjust_harvest_source_search_params(search_params)

        return search_params

    def after_dataset_delete(self, context: types.Context, pkg_dict: dict[str, Any]):
        if pkg_dict.get("id") and not config.ignore_si_workflow():
            try:
                jobs.enqueue(
                    delete_ingested,
                    kwargs={"pkg_id": pkg_dict["id"]},
                    rq_kwargs={"timeout": 1000},
                )
            except Exception as e:
                tk.h.flash_error(f"{e}")

    def after_dataset_show(self, context: types.Context, pkg_dict: dict[str, Any]):
        _set_spatial_from_org(pkg_dict)
        return pkg_dict


def _set_spatial_from_org(pkg_dict: dict[str, Any]) -> None:
    if pkg_dict.get("spatial_coverage"):
        return
    extras = pkg_dict.get("extras", [])
    if any(extra["key"] == "spatial_coverage" and extra["value"] for extra in extras):
        return
    spatial_coverage = _fetch_org_spatial_coverage(pkg_dict)
    if spatial_coverage:
        pkg_dict["spatial"] = spatial_coverage


def _set_extras_spatial_for_index(pkg_dict: dict[str, Any]) -> None:
    if pkg_dict.get("extras_spatial_coverage"):
        return
    spatial_coverage = _fetch_org_spatial_coverage(pkg_dict)
    if spatial_coverage:
        pkg_dict["extras_spatial"] = spatial_coverage


def _fetch_org_spatial_coverage(pkg_dict: dict[str, Any]) -> str | None:
    """Fetch spatial coverage from the package's organization."""
    owner_org = pkg_dict.get("owner_org")
    if not owner_org:
        return None
    organization = tk.get_action("organization_show")(
        {"ignore_auth": True}, {"id": owner_org}
    )
    return organization.get("spatial_coverage")


def _index_source_type(pkg_dict: dict[str, Any]):
    value = pkg_dict["source_type"]
    result = next(
        (
            d
            for d in tk.get_action("harvesters_info_show")({}, {})
            if d.get("name") == value
        ),
        {},
    )
    pkg_dict["source_type"] = result.get("title", value)


def _adjust_harvest_source_search_params(search_params: dict[str, Any]) -> None:
    if not tk.current_user.is_authenticated:
        tk.abort(403, tk._("Not authorized to see this page"))

    if tk.current_user.sysadmin:
        return

    if ids := [org["id"] for org in tk.h.organizations_available() if "id" in org]:
        search_params["fq"] += " +owner_org:(" + " OR ".join(ids) + ")"
    else:
        search_params["fq"] += " +owner_org:__nonexistent__"
