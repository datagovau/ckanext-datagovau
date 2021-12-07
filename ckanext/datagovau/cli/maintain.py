from __future__ import annotations

import shutil
import tempfile
import logging

from typing import Iterable, Optional
import contextlib

import click
import ckanapi

log = logging.getLogger(__name__)


@contextlib.contextmanager
def temp_dir(suffix: str, dir: str):
    path = tempfile.mkdtemp(suffix=suffix, dir=dir)
    try:
        yield path
    finally:
        shutil.rmtree(path)


@click.group()
def maintain():
    """Maintenance tasks"""
    pass


@maintain.command()
@click.argument("ids", nargs=-1)
@click.option("-u", "--username")
@click.option("--tmp-dir", "/tmp")
@click.option("--days-to-buffer", "days", default=3, type=int)
@click.option("--skip-errors", is_flag=True)
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
    from . import _zip_extract as z

    if not ids:
        ids = z.get_dataset_ids(ckan, days)
    with ctx.meta["flask_app"].test_request_context():
        for resource, dataset in z.select_extractable_resources(ckan, ids):
            with temp_dir(resource["id"], tmp_dir) as path:
                result = z.extract_resource(resource, path)
                if not result:
                    continue
                try:
                    updated_resource_id = z.update_resource(
                        *result, ckan, resource, dataset
                    )
                except ckanapi.ValidationError:
                    log.error(
                        "Cannot update resource {} from dataset {}".format(
                            resource["id"], dataset["id"]
                        )
                    )
                    if skip_errors:
                        continue
                    raise

                z.submit_to_datapusher(updated_resource_id, ckan)
