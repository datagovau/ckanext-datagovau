from __future__ import annotations

import logging
from tempfile import mkstemp
from typing import Iterable, Optional

import ckanapi
import click
from sqlalchemy.exc import ProgrammingError
from werkzeug.datastructures import FileStorage

import ckan.model as model
import ckan.plugins.toolkit as tk

from ckanext.datagovau.cli.maintain.bioregional_ingest import bioregional_ingest
from ckanext.datagovau.cli.maintain.purge_user import purge_deleted_users

log = logging.getLogger(__name__)


@click.group()
@click.help_option("-h", "--help")
def maintain():
    """Maintenance tasks"""
    pass


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
    username: Optional[str],
    days: int,
    skip_errors: bool,
):
    """ZIP extractor for data.gov.au"""
    ckan = ckanapi.LocalCKAN(username)
    from ...utils.zip import get_dataset_ids, select_extractable_resources

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
    """Force purge of trashed organizations. If the organization has child packages,
    they become unowned"""
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


def _execute_sql_delete_commands(commands):
    for command in commands:
        try:
            model.Session.execute(command)
            model.Session.commit()
        except ProgrammingError:
            log.warning(f'Could not execute command "{command}". Table does not exist.')
            model.Session.rollback()


@maintain.command()
@click.help_option("-h", "--help")
@click.option("--tmp-dir", help="Storage for temporal files.")
@click.pass_context
def energy_rating_ingestor(ctx: click.Context, tmp_dir: Optional[str]):
    """Update energy-rating resources."""
    from .. import _energy_rating as e

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
