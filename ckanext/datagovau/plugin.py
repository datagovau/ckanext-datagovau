from __future__ import annotations

import logging
from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import model, types
from ckan.common import CKANConfig
from ckan.lib.plugins import DefaultTranslation

from ckanext.metaexport.formatters import Format, Formatter
from ckanext.metaexport.interfaces import IMetaexport
from ckanext.transmute.interfaces import ITransmute

from ckanext.datagovau import metaexport
from ckanext.datagovau.geoserver_utils import (
    CONFIG_PUBLIC_URL,
    run_ingestor,
)

from . import config, implementations, utils
from .logic import transmutators
from .middleware import DGARedisSessionSerializer

log = logging.getLogger(__name__)

ingest_rest_list = ["kml", "kmz", "shp", "shapefile"]


@tk.blanket.actions
@tk.blanket.auth_functions
@tk.blanket.cli
@tk.blanket.config_declarations
@tk.blanket.helpers
@tk.blanket.validators
@tk.blanket.blueprints
class DataGovAuPlugin(
    implementations.SearchAutocomplete,
    implementations.PackageController,
    implementations.Iso19115,
    p.SingletonPlugin,
    DefaultTranslation,
):
    p.implements(p.IConfigurer, inherit=False)
    p.implements(p.IDomainObjectModification)
    p.implements(ITransmute, inherit=True)
    p.implements(p.IMiddleware, inherit=True)
    p.implements(p.ITranslation)
    p.implements(p.IFacets, inherit=True)
    p.implements(IMetaexport, inherit=True)

    # ITransmute

    def get_transmutators(self):
        return transmutators.get_transmutators()

    # IConfigurer

    def update_config(self, config_: CKANConfig):
        tk.add_template_directory(config_, "templates")
        tk.add_resource("assets", "datagovau")
        tk.add_public_directory(config_, "public")

    # IDomainObjectModification

    def notify(self, entity: Any, operation: str):
        if config.ignore_si_workflow():
            return

        if (
            operation != "changed"
            or not isinstance(entity, model.Package)
            or entity.state != "active"
        ):
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

    # IMiddleware

    def make_middleware(self, app: types.CKANApp, config_: CKANConfig):
        if tk.config.get("SESSION_TYPE", None) == "redis":
            app.session_interface.serializer = DGARedisSessionSerializer()
        return app

    # IFacets
    def dataset_facets(
        self, facets_dict: dict[str, Any], package_type: str
    ) -> dict[str, Any]:
        facets_dict["organization"] = tk._("Organisation")
        return facets_dict

    def group_facets(
        self, facets_dict: dict[str, Any], group_type: str, package_type: str | None
    ) -> dict[str, Any]:
        facets_dict["organization"] = tk._("Organisation")
        return facets_dict

    def organization_facets(
        self,
        facets_dict: dict[str, Any],
        organization_type: str,
        package_type: str | None,
    ) -> dict[str, Any]:
        facets_dict["organization"] = tk._("Organisation")
        return facets_dict

    # IMetaexport

    def register_data_extractors(self, formatters: type[Formatter]):
        fmt: Format = formatters.get("gmd")
        fmt.set_data_extractor(metaexport.gmd_extractor)


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


def _do_geoserver_ingest(entity: model.Package, ingest_resources: list[model.Resource]):
    geoserver_resources = [
        res for res in entity.resources if tk.config[CONFIG_PUBLIC_URL] in res.url
    ]

    ingest_res = ingest_resources[0]

    if not geoserver_resources:
        send = True
    elif any(r.last_modified == ingest_res.last_modified for r in geoserver_resources):
        send = False
    else:
        send = ingest_res.last_modified > geoserver_resources[0].last_modified

    if send:
        log.debug("Try ingesting %s using geoserver ingest API", entity.id)
        tk.enqueue_job(
            run_ingestor,
            kwargs={"pkg_id": entity.id},
            rq_kwargs={"timeout": 1000},
        )
