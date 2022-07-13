from __future__ import annotations

import json
import logging
from email.utils import formatdate
from functools import partial
from tempfile import mkstemp
from time import time
from typing import BinaryIO, Iterable, Optional, Sequence, TextIO

import ckan.model as model
import ckan.plugins.toolkit as tk
import ckanapi
import click
from sqlalchemy.exc import ProgrammingError
from werkzeug.datastructures import FileStorage

log = logging.getLogger(__name__)


@click.group()
@click.help_option("-h", "--help")
def maintain():
    """Maintenance tasks"""
    pass


@maintain.command()
@click.argument("ids", nargs=-1)
@click.option("-u", "--username", help="CKAN user who performs extraction.")
@click.option(
    "--tmp-dir", default="/tmp", help="Root folder for temporal files"
)
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
    from ..utils.zip import get_dataset_ids, select_extractable_resources

    if not ids:
        ids = get_dataset_ids(ckan, days)
    with ctx.meta["flask_app"].test_request_context():
        for resource in select_extractable_resources(ckan, ids):
            try:
                ckan.action.dga_extract_resource(
                    id=resource["id"], tmp_dir=tmp_dir
                )
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
    """Force purge of trashed organizations. If the organization has child packages, they become unowned"""
    sql_commands = [
        "delete from group_extra_revision where group_id in (select id from"
        " \"group\" where \"state\"='deleted' AND is_organization='t');",
        'delete from group_extra where group_id in (select id from "group"'
        " where \"state\"='deleted' AND is_organization='t');",
        'delete from member where group_id in (select id from "group" where'
        " \"state\"='deleted' AND is_organization='t');",
        'delete from "group" where "state"=\'deleted\' AND'
        " is_organization='t';",
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
            log.warning(
                f'Could not execute command "{command}". Table does not exist.'
            )
            model.Session.rollback()


@maintain.command()
@click.help_option("-h", "--help")
@click.option(
    "--storage", required=True, help="Storage path for downloaded assesments"
)
@click.option(
    "--log", type=click.File("w"), help="Log file(STDOUT by default)"
)
@click.option("--sender", help="From-header of an email with ingestion log")
@click.option(
    "--receiver", multiple=True, help="Receivers of the ingestion log"
)
@click.option("--aws-key", "key", help="AWS KeyId")
@click.option("--aws-secret", "secret", help="AWS SecretKey")
@click.option(
    "--aws-profile",
    "profile",
    help="Predefined AWS Profile(use it instead of Key/Secret pair)",
)
@click.option("--aws-region", "region", help="AWS region")
@click.option(
    "--s3-bucket",
    "bucket",
    required=True,
    help="S3 Bucket for uploading assesments",
)
@click.option(
    "--source", type=click.File("rb"), help="Static local source of assesments"
)
@click.option(
    "--url",
    default="https://data.bioregionalassessments.gov.au/datastore/dataset/",
    help="Source URL of the bioregional assesments",
)
@click.option(
    "--no-verify",
    is_flag=True,
    help="Ignore SSL certificates while making requests to bioregional source",
)
@click.option(
    "--timeout",
    type=int,
    help="Timeout for requests to bioregional source",
)
@click.option(
    "--skip-local",
    is_flag=True,
    help="Skip datasets that are already downloaded",
)
@click.option(
    "--no-download",
    is_flag=True,
    help="Do not download datasets, process only existing files",
)
@click.option(
    "--no-upload",
    is_flag=True,
    help="Do not upload datasets to S3",
)
def bioregional_ingest(
    storage: str,
    log: Optional[TextIO],
    sender: Optional[str],
    receiver: Sequence[str],
    key: Optional[str],
    secret: Optional[str],
    region: Optional[str],
    profile: Optional[str],
    bucket: str,
    source: Optional[BinaryIO],
    url: str,
    no_verify: bool,
    timeout: Optional[int],
    skip_local: bool,
    no_download: bool,
    no_upload: bool,
):
    """Upload Bioregional Assesments to S3 bucket,"""
    from . import _bioregional as b

    echo = partial(click.echo, file=log)

    echo(f"S3 Bioregional S3 ingest starting at {formatdate(localtime=True)}")
    try:
        source = b.prepare_source(source, url, no_verify, timeout)
    except ValueError as e:
        echo(f"Cannot prepare source: {e}")
        raise click.Abort()

    echo(f"Reading data from {source.name}")

    try:
        datasets = json.load(source)
    except ValueError as e:
        echo(f"Cannot parse source as JSON: {e}")
        raise click.Abort()
    b.Upload.setup(key, secret, region, profile, bucket)

    for record in b.converted_datasets(
        datasets, storage, skip_local, no_download
    ):
        echo("-" * 80)
        echo(f"Ingesting dataset {record.dataset['id']}:")
        if record:
            echo(f"\t{record} exists on filesystem")
        else:
            download = b.download_record(record, no_verify, timeout, url)
            if not download or not isinstance(download, b.Download):
                echo(
                    f"\tCannot download {record.dataset['id']}:"
                    f" {download.reason()}"
                )
                continue

            echo(f"\tDownload data from URL {download.response.url}")
            size = len(download)

            echo(
                "\tDownloading"
                f" {record.dataset['folder_name']} {size} bytes"
                f" ({size // 1024 ** 2}MB)"
            )
            start = time()
            with click.progressbar(download.start(record), length=size) as bar:
                for step in bar:
                    bar.update(step)
            echo(f"\tDownloaded in {time() - start}")

        if no_upload:
            continue

        upload = record.prepare_uploader()
        echo(f"\tCheck the presence of {upload.key.key} on S3")
        if upload:
            echo(f"\t{upload.key.key} exists on S3. Compare")
            if len(record) != len(upload):
                echo(
                    f"\tFilesizes differ: remote - {len(upload)} |"
                    f" local - {len(record)}"
                )
                upload.start(record)
                echo(f"\t{upload.key.key} uploaded to S3")
            else:
                echo("\tFilesize is the same. Skip")
        else:
            echo(f"\tObject does not exist. Upload")
            upload.start(record)
            echo(f"\t{upload.key.key} uploaded to S3")

    if log and sender and receiver:
        log.close()
        b.send_bioregional_log(log, sender, receiver)
        click.secho(f"Successfully sent email to {receiver}", fg="green")


@maintain.command()
@click.help_option("-h", "--help")
@click.option("--tmp-dir", help="Storage for temporal files.")
@click.pass_context
def energy_rating_ingestor(ctx: click.Context, tmp_dir: Optional[str]):
    """Update energy-rating resources."""
    from . import _energy_rating as e

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
