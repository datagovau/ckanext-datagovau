from __future__ import annotations

import logging
from collections.abc import Iterable
from tempfile import mkstemp

import ckanapi
import click
import sqlalchemy as sa
from sqlalchemy.exc import ProgrammingError
from werkzeug.datastructures import FileStorage

import ckan.plugins.toolkit as tk
from ckan import model

from ckanext.datagovau.cli.maintain.bioregional_ingest import bioregional_ingest
from ckanext.datagovau.cli.maintain.purge_user import purge_deleted_users

log = logging.getLogger(__name__)


@click.group()
@click.help_option("-h", "--help")
def maintain():
    """Maintenance tasks."""


maintain.add_command(bioregional_ingest)
maintain.add_command(purge_deleted_users)


@maintain.command()
@click.argument("ids", nargs=-1)
@click.option("-u", "--username", help="CKAN user who performs extraction.")
@click.option("--tmp-dir", default="/tmp", help="Root folder for temporal files")
@click.option(
    "--days-to-buffer",
    "days",
    default=3,
    type=int,
    help="Extract datasets modified up to <days> ago",
)
@click.option(
    "--skip-errors",
    is_flag=True,
    help="Do not interrupt extraction even after an error",
)
@click.help_option("-h", "--help")
@click.pass_context
def zip_extract(
    ctx: click.Context,
    ids: Iterable[str],
    tmp_dir: str,
    username: str | None,
    days: int,
    skip_errors: bool,
):
    """ZIP extractor for data.gov.au."""
    ckan = ckanapi.LocalCKAN(username)
    from ckanext.datagovau.utils.zip import (
        get_dataset_ids,
        select_extractable_resources,
    )

    if not ids:
        ids = get_dataset_ids(ckan, days)
    with ctx.meta["flask_app"].test_request_context():
        for resource in select_extractable_resources(ckan, ids):
            try:
                ckan.action.dga_extract_resource(id=resource["id"], tmp_dir=tmp_dir)
            except ckanapi.ValidationError:
                log.error(
                    "Cannot update resource %s from dataset %s",
                    resource["id"],
                    resource["package_id"],
                )
                if skip_errors:
                    continue
                raise


@maintain.command()
@click.help_option("-h", "--help")
def force_purge_orgs():
    """Force purge of trashed organizations.

    If the organization has child packages, they become unowned.
    """
    sql_commands = [
        "delete from group_extra_revision where group_id in (select id from"
        " \"group\" where \"state\"='deleted' AND is_organization='t');",
        'delete from group_extra where group_id in (select id from "group"'
        " where \"state\"='deleted' AND is_organization='t');",
        'delete from member where group_id in (select id from "group" where'
        " \"state\"='deleted' AND is_organization='t');",
        'delete from "group" where "state"=\'deleted\' AND' " is_organization='t';",
    ]

    _execute_sql_delete_commands(sql_commands)


@maintain.command()
@click.help_option("-h", "--help")
def force_purge_pkgs():
    """Force purge of trashed packages."""
    sql_commands = [
        "delete from package_extra pe where pe.package_id in (select id from"
        " package where name='stevetest');",
        "delete from package where name='stevetest';",
        "delete from related_dataset where dataset_id in (select id from"
        " package where \"state\"='deleted');",
        "delete from harvest_object_extra where harvest_object_id in (select"
        " id from harvest_object where package_id in (select id from package"
        " where \"state\"='deleted'));",
        "delete from harvest_object where package_id in (select id from"
        " package where \"state\"='deleted');",
        "delete from harvest_object where package_id in (select id from"
        " package where \"state\"='deleted');",
        "delete from package_extra where package_id in (select id from package"
        " where \"state\"='deleted');",
        "delete from package where \"state\"='deleted';",
    ]

    _execute_sql_delete_commands(sql_commands)


def _execute_sql_delete_commands(commands: list[str]):
    for command in commands:
        try:
            model.Session.execute(sa.text(command))
            model.Session.commit()
        except ProgrammingError:
            log.warning(
                'Could not execute command "%s". Table does not exist.', command
            )
            model.Session.rollback()


@maintain.command()
@click.help_option("-h", "--help")
@click.option("--tmp-dir", help="Storage for temporal files.")
@click.pass_context
def energy_rating_ingestor(ctx: click.Context, tmp_dir: str | None):
    """Update energy-rating resources."""
    from ckanext.datagovau.cli import _energy_rating as e

    user = tk.get_action("get_site_user")({"ignore_auth": True}, {})

    for resource, cid in e.energy_resources():
        log.info("Processing %s", resource["id"])
        filepath = mkstemp(dir=tmp_dir)[1]
        filename = e.fetch(cid, filepath)

        resource["name"] = resource["name"].split("-")[0] + " - " + filename

        with open(filepath, "rb") as stream:
            resource["upload"] = FileStorage(stream, filename, filename)
            with ctx.meta["flask_app"].test_request_context():
                resource = tk.get_action("resource_update")(
                    {"user": user["name"]}, resource
                )


_sources = {
    "act": {
        "config": '{"tsm_named_schema": "act"}',
        "frequency": "MANUAL",
        "name": "act",
        "notes": "ACT DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "ACT",
        "url": "https://www.data.act.gov.au/data.json",
    },
    "nsw": {
        "config": '{"tsm_named_schema": "nsw"}',
        "frequency": "MANUAL",
        "name": "nsw",
        "notes": "DataNSW harvester",
        "source_type": "ckan",
        "title": "DataNSW",
        "url": "https://data.nsw.gov.au/data/",
    },
    "vic": {
        "config": '{"tsm_named_schema": "vic"}',
        "frequency": "MANUAL",
        "name": "vic",
        "notes": "Victoria Government harvester",
        "source_type": "ckan",
        "title": "Victoria Government",
        "url": "https://discover.data.vic.gov.au",
    },
    "wa": {
        "config": '{"tsm_named_schema": "wa", "fq": "access_level:open"}',
        "frequency": "MANUAL",
        "name": "wa",
        "notes": "Western Australia Government harvester",
        "source_type": "ckan",
        "title": "Western Australia Government",
        "url": "https://catalogue.data.wa.gov.au",
    },
    "aurin": {
        "config": '{"tsm_named_schema": "aurin"}',
        "frequency": "MANUAL",
        "name": "aurin",
        "notes": "Australian Urban Research Infrastructure Networkharvester",
        "source_type": "ckan",
        "title": "Australian Urban Research Infrastructure Network",
        "url": "https://data.aurin.org.au/",
    },
    "sa": {
        "config": '{"tsm_named_schema": "sa"}',
        "frequency": "MANUAL",
        "name": "sa",
        "notes": "South Australia Government harvester",
        "source_type": "ckan",
        "title": "South Australia Government",
        "url": "https://data.sa.gov.au/data/",
    },
    "ditrdca": {
        "config": '{"tsm_named_schema": "ditrdca", "fq": "-harvest_source_title:No"}',
        "frequency": "MANUAL",
        "name": "ditrdca",
        "notes": "DITRDCA harvester",
        "source_type": "ckan",
        "title": "DITRDCA",
        "url": "https://catalogue.data.infrastructure.gov.au",
    },
    "bureau_of_meteorology": {
        "config": '{"tsm_named_schema": "bureau_of_meteorology"}',
        "frequency": "MANUAL",
        "name": "bureau_of_meteorology",
        "notes": "Bureau of Meteorology harvester",
        "source_type": "basket_csw",
        "title": "Bureau of Meteorology",
        "url": "http://www.bom.gov.au/geonetwork/srv/eng/csw",
    },
    "marlin": {
        "config": '{"tsm_named_schema": "marlin"}',
        "frequency": "MANUAL",
        "name": "marlin",
        "notes": "CSIRO Marlin harvester",
        "source_type": "basket_csw",
        "title": "CSIRO Marlin",
        "url": "https://marlin.csiro.au/geonetwork/srv/eng/csw",
    },
    "mrt": {
        "config": '{"tsm_named_schema": "mrt"}',
        "frequency": "MANUAL",
        "name": "mrt",
        "notes": "Mineral Resources Tasmania harvester",
        "source_type": "basket_csw",
        "title": "Mineral Resources Tasmania",
        "url": "https://www.mrt.tas.gov.au/web-catalogue/srv/eng/csw",
    },
    "geo-au": {
        "config": '{"tsm_named_schema": "geo-au"}',
        "frequency": "MANUAL",
        "name": "geo-au",
        "notes": "Geoscience Australia harvester",
        "source_type": "basket_csw",
        "title": "Geoscience Australia",
        "url": "https://ecat.ga.gov.au/geonetwork/srv/eng/csw",
    },
    "tasmania-list": {
        "config": '{"tsm_named_schema": "tasmania-list"}',
        "frequency": "MANUAL",
        "name": "tasmania-list",
        "notes": "Tasmania TheList harvester",
        "source_type": "basket_csw",
        "title": "Tasmania TheList",
        "url": "https://data.thelist.tas.gov.au/datagn/srv/eng/csw",
    },
    "odn": {
        "config": '{"tsm_named_schema": "odn"}',
        "frequency": "MANUAL",
        "name": "odn",
        "notes": "Australian Oceans Data Network harvester",
        "source_type": "basket_csw",
        "title": "Australian Oceans Data Network",
        "url": "https://catalogue.aodn.org.au/geonetwork/srv/eng/csw",
    },
    "tern": {
        "config": '{"tsm_named_schema": "tern"}',
        "frequency": "MANUAL",
        "name": "tern",
        "notes": "Terrestrial Ecosystem Research Network harvester",
        "source_type": "basket_csw",
        "title": "Terrestrial Ecosystem Research Network",
        "url": "https://geonetwork.tern.org.au/geonetwork/srv/eng/csw",
    },
    "csiro": {
        "config": '{"tsm_named_schema": "csiro"}',
        "frequency": "MANUAL",
        "name": "csiro",
        "notes": "CSIRO DAP harvester",
        "source_type": "csiro",
        "title": "CSIRO DAP",
        "url": "https://data.csiro.au/dap/ws/v2",
    },
    "actmapi": {
        "config": '{"tsm_named_schema": "actmapi"}',
        "frequency": "MANUAL",
        "name": "actmapi",
        "notes": "ACTMAPi DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "ACTMAPi",
        "url": "https://actmapi-actgov.opendata.arcgis.com/api/feed/dcat-us/1.1.json",
    },
    "hobart": {
        "config": '{"tsm_named_schema": "hobart"}',
        "frequency": "MANUAL",
        "name": "hobart",
        "notes": "Hobart City DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Hobart City",
        "url": "https://data-1-hobartcc.opendata.arcgis.com/api/feed/dcat-us/1.1.json",
    },
    "melbourne": {
        "config": '{"tsm_named_schema": "melbourne"}',
        "frequency": "MANUAL",
        "name": "melbourne",
        "notes": "Melbourne Data harvester",
        "source_type": "basket_dcat_json",
        "title": "Melbourne Data",
        "url": "https://data.melbourne.vic.gov.au/data.json",
    },
    "melbourne_water": {
        "config": '{"tsm_named_schema": "melbourne_water"}',
        "frequency": "MANUAL",
        "name": "melbourne_water",
        "notes": "Melbourne Water Corporation DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Melbourne Water Corporation",
        "url": "https://data-melbournewater.opendata.arcgis.com/api/feed/dcat-us/1.1.json",
    },
    "moreton_bay": {
        "config": '{"tsm_named_schema": "moreton_bay"}',
        "frequency": "MANUAL",
        "name": "moreton_bay",
        "notes": "Moreton Bay Regional Council DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Moreton Bay Regional Council",
        "url": "https://datahub.moretonbay.qld.gov.au/api/feed/dcat-us/1.1.json",
    },
    "cardinia_shire": {
        "config": '{"tsm_named_schema": "cardinia_shire"}',
        "frequency": "MANUAL",
        "name": "cardinia_shire",
        "notes": "Cardinia Shire Council DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Cardinia Shire Council",
        "url": "https://data-cscgis.opendata.arcgis.com/api/feed/dcat-us/1.1.json",
    },
    "launceston": {
        "config": '{"tsm_named_schema": "launceston"}',
        "frequency": "MANUAL",
        "name": "launceston",
        "notes": "City of Launceston Open Data DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "City of Launceston",
        "url": "https://opendata.launceston.tas.gov.au/api/feed/dcat-us/1.1.json",
    },
    "southern_grampians": {
        "config": '{"tsm_named_schema": "southern_grampians"}',
        "frequency": "MANUAL",
        "name": "southern_grampians",
        "notes": "Southern Grampians Shire Council DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Southern Grampians Shire",
        "url": "https://www.connectgh.com.au/data.json",
    },
    "qld": {
        "config": '{"tsm_named_schema": "qld"}',
        "frequency": "MANUAL",
        "name": "qld",
        "notes": "Queensland Government harvester",
        "source_type": "ckan",
        "title": "Queensland Government",
        "url": "https://data.qld.gov.au/",
    },
    "connector_bundaberg": {
        "config": '{"tsm_named_schema": "connector_bundaberg"}',
        "frequency": "MANUAL",
        "name": "connector_bundaberg",
        "notes": "Connector Bundaberg DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Connector Bundaberg",
        "url": "https://opendata-bundabergrc.hub.arcgis.com/api/feed/dcat-us/1.1.json",
    },
    "dcceew": {
        "config": '{"tsm_named_schema": "dcceew"}',
        "frequency": "MANUAL",
        "name": "dcceew",
        "notes": "DCCEEW DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "DCCEEW",
        "url": "https://fed.dcceew.gov.au/api/feed/dcat-us/1.1.json",
    },
    "connector_redland": {
        "config": '{"tsm_named_schema": "connector_redland"}',
        "frequency": "MANUAL",
        "name": "connector_redland",
        "notes": "Connector Redland DCAT harvester",
        "source_type": "basket_dcat_json",
        "title": "Connector Redland",
        "url": "https://opendata.redland.qld.gov.au/api/feed/dcat-us/1.1.json",
    },
}


@maintain.command()
@click.argument("names", nargs=-1)
@click.option("-o", "--organization", help="Organization for harvested datasets")
def recreate_harvesters(names: tuple[str], organization: str | None):
    """Create or reset harvesters."""
    user = tk.get_action("get_site_user")({"ignore_auth": True}, {})

    for name, info in _sources.items():
        if names and name not in names:
            continue

        try:
            source = tk.get_action("harvest_source_show")(
                {"user": user["name"]},
                {
                    "id": name,
                },
            )
        except tk.ObjectNotFound:
            source = tk.get_action("harvest_source_create")(
                {"user": user["name"]}, dict(info, owner_org=organization)
            )
        else:
            source.update(info)
            source = tk.get_action("harvest_source_update")(
                {"user": user["name"]}, source
            )

        click.echo(f"Source {name} recreated.")
