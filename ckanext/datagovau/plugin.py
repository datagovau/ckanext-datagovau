from __future__ import annotations

import inspect
import logging
from typing import Any

import ckan.authz as authz
import ckan.lib.helpers as h
import ckan.lib.jobs as jobs
import ckan.model as model
import ckan.plugins as p
import ckan.plugins.toolkit as tk

import ckanext.datagovau.helpers as helpers
from ckanext.datagovau import cli, validators
from ckanext.datagovau.geoserver_utils import (
    CONFIG_PUBLIC_URL,
    delete_ingested,
    run_ingestor,
)
from ckanext.datagovau.logic.action import get_actions
from ckanext.datagovau.logic.auth import get_auth_functions
from ckanext.xloader.plugin import xloaderPlugin

log = logging.getLogger(__name__)

ingest_rest_list = ["kml", "kmz", "shp", "shapefile"]

CONFIG_IGNORE_WORKFLOW = "ckanext.datagovau.spatialingestor.ignore_workflow"
DEFAULT_IGNORE_WORKFLOW = False


def _dga_xnotify(self, resource):
    try:
        return _original_xnotify(self, resource)
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


class DataGovAuPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer, inherit=False)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IValidators)
    p.implements(p.IClick)
    p.implements(p.IPackageController, inherit=True)
    p.implements(p.IDomainObjectModification)
    p.implements(p.IActions)
    p.implements(p.IAuthFunctions)

    # IClick

    def get_commands(self):
        return cli.get_commands()

    # IConfigurer

    def update_config(self, config):
        tk.add_template_directory(config, "templates")
        tk.add_resource("assets", "datagovau")
        tk.add_public_directory(config, "assets")

    # ITemplateHelpers

    def get_helpers(self) -> dict[str, Any]:
        return helpers.get_helpers()

    # IValidators

    def get_validators(self):
        return validators.get_validators()

    # IPackageController

    def before_index(self, pkg_dict):
        pkg_dict["unpublished"] = tk.asbool(pkg_dict.get("unpublished"))
        return pkg_dict

    def before_search(self, search_params):
        stat_facet = search_params["extras"].get("ext_dga_stat_group")
        if stat_facet:
            search_params.setdefault("fq_list", []).append(
                _dga_stat_group_to_fq(stat_facet)
            )
        return search_params

    def after_delete(self, context, pkg_dict):
        if pkg_dict.get("id"):
            if not tk.asbool(
                tk.config.get(CONFIG_IGNORE_WORKFLOW, DEFAULT_IGNORE_WORKFLOW)
            ):
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

        if tk.asbool(
            tk.config.get(CONFIG_IGNORE_WORKFLOW, DEFAULT_IGNORE_WORKFLOW)
        ):
            return

        ingest_resources = [
            res
            for res in entity.resources
            if res.format.lower() in ingest_rest_list
        ]

        if ingest_resources:
            _do_geoserver_ingest(entity, ingest_resources)
        else:
            _do_spatial_ingest(entity.id)


    # IAuthFunctions

    def get_auth_functions(self):
        return get_auth_functions()

    # IActions

    def get_actions(self):
        return get_actions()


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
        res
        for res in entity.resources
        if tk.config[CONFIG_PUBLIC_URL] in res.url
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
