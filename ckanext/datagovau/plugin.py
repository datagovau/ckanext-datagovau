from __future__ import annotations

import inspect
import json
import logging

import ckan.lib.helpers as h
import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import authz, model
from ckan.lib import jobs

from ckanext.transmute.interfaces import ITransmute
from ckanext.xloader.plugin import xloaderPlugin

from ckanext.datagovau.geoserver_utils import (
    CONFIG_PUBLIC_URL,
    delete_ingested,
    run_ingestor,
)

from . import utils
from .logic import transmutators

log = logging.getLogger(__name__)

ingest_rest_list = ["kml", "kmz", "shp", "shapefile"]

CONFIG_IGNORE_WORKFLOW = "ckanext.datagovau.spatialingestor.ignore_workflow"


def _dga_xnotify(self, resource, operation):
    try:
        return _original_xnotify(self, resource, operation)
    except tk.ObjectNotFound:
        # resource has `deleted` state
        pass


_original_xnotify = xloaderPlugin.notify
xloaderPlugin.notify = _dga_xnotify


_original_permission_check = authz.has_user_permission_for_group_or_org


def _dga_permission_check(group_id, user_name, permission):
    stack = inspect.stack()
    # Bypass authorization to enable datasets to be removed from/added to AGIFT
    # classification
    if stack[1].function == "package_membership_list_save":
        return True
    return _original_permission_check(group_id, user_name, permission)


authz.has_user_permission_for_group_or_org = _dga_permission_check


@tk.blanket.actions
@tk.blanket.auth_functions
@tk.blanket.cli
@tk.blanket.config_declarations
@tk.blanket.helpers
@tk.blanket.validators
class DataGovAuPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer, inherit=False)
    p.implements(p.IPackageController, inherit=True)
    p.implements(p.IDomainObjectModification)
    p.implements(ITransmute, inherit=True)

    # ITransmute
    def get_transmutators(self):
        return transmutators.get_transmutators()

    # IConfigurer

    def update_config(self, config):
        tk.add_template_directory(config, "templates")
        tk.add_resource("assets", "datagovau")
        tk.add_public_directory(config, "assets")

    # IPackageController

    def before_dataset_index(self, pkg_dict):
        if pkg_dict["type"] == "harvest":
            return pkg_dict

        pkg_dict["unpublished"] = tk.asbool(pkg_dict.get("unpublished"))
        # uploading resources to datastore will cause SOLR error
        # for multivalued field
        # inside set_datastore_active_flag action before
        # reindexing the dataset, it retrieves the data from package_show
        # therefore these two fields are not converted.
        geospatial_topic = pkg_dict["geospatial_topic"]
        if geospatial_topic and not isinstance(geospatial_topic, str):
            pkg_dict["geospatial_topic"] = json.dumps(geospatial_topic)

        return pkg_dict

    def before_dataset_search(self, search_params):
        stat_facet = search_params["extras"].get("ext_dga_stat_group")
        if stat_facet:
            search_params.setdefault("fq_list", []).append(
                _dga_stat_group_to_fq(stat_facet)
            )
        return search_params

    def after_dataset_delete(self, context, pkg_dict):
        if pkg_dict.get("id") and not tk.asbool(tk.config[CONFIG_IGNORE_WORKFLOW]):
            try:
                jobs.enqueue(
                    delete_ingested,
                    kwargs={"pkg_id": pkg_dict["id"]},
                    rq_kwargs={"timeout": 1000},
                )
            except Exception as e:
                h.flash_error(f"{e}")

    # IDomainObjectModification

    def notify(self, entity, operation):
        if (
            operation != "changed"
            or not isinstance(entity, model.Package)
            or entity.state != "active"
        ):
            return

        if tk.config[CONFIG_IGNORE_WORKFLOW]:
            return

        ingest_resources = [
            res
            for res in entity.resources
            if utils.contains(res.format.lower(), ingest_rest_list)
        ]

        if ingest_resources:
            _do_geoserver_ingest(entity, ingest_resources)
        else:
            _do_spatial_ingest(entity.id)


_stat_fq = {
    "api": "res_extras_datastore_active:true OR res_format:WMS",
    "open": "isopen:true",
    "unpublished": "unpublished:true",
}


def _dga_stat_group_to_fq(group: str) -> str:
    return _stat_fq.get(group, "*:*")


def _do_spatial_ingest(pkg_id: str):
    """Enqueue old-style package ingestion.

    Suits for tab, mapinfo, geotif, and grid formats, because geoserver cannot
    ingest them via it's ingestion API.

    """
    log.debug("Try ingesting %s using local spatial ingestor", pkg_id)

    tk.enqueue_job(
        _do_ingesting_wrapper,
        kwargs={"dataset_id": pkg_id},
        rq_kwargs={"timeout": 1000},
    )


def _do_ingesting_wrapper(dataset_id: str):
    """Trigger spatial ingestion for the dataset.

    This wrapper can be enqueued as a background job. It allows web-node to
    skip import of the `_spatialingestor`, which requires `GDAL` to be
    installed system-wide.

    """
    from .cli._spatialingestor import do_ingesting

    do_ingesting(dataset_id, False)


def _do_geoserver_ingest(entity, ingest_resources):
    geoserver_resources = [
        res for res in entity.resources if tk.config[CONFIG_PUBLIC_URL] in res.url
    ]

    ingest_res = ingest_resources[0]
    send = False

    if not geoserver_resources:
        send = True
    else:
        if [
            r
            for r in geoserver_resources
            if r.last_modified == ingest_res.last_modified
        ]:
            send = False
        else:
            geo_res = geoserver_resources[0]
            if ingest_res.last_modified > geo_res.last_modified:
                send = True

    if send:
        log.debug("Try ingesting %s using geoserver ingest API", entity.id)
        tk.enqueue_job(
            run_ingestor,
            kwargs={"pkg_id": entity.id},
            rq_kwargs={"timeout": 1000},
        )
