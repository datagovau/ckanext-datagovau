from __future__ import annotations

import json
import logging
from collections.abc import Sequence
from email.utils import formatdate
from functools import partial
from time import time
from typing import BinaryIO, TextIO

import click

log = logging.getLogger(__name__)


@click.command()
@click.help_option("-h", "--help")
@click.option("--storage", required=True, help="Storage path for downloaded assesments")
@click.option("--log", type=click.File("w"), help="Log file(STDOUT by default)")
@click.option("--sender", help="From-header of an email with ingestion log")
@click.option("--receiver", multiple=True, help="Receivers of the ingestion log")
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
    log: TextIO | None,
    sender: str | None,
    receiver: Sequence[str],
    key: str | None,
    secret: str | None,
    region: str | None,
    profile: str | None,
    bucket: str,
    source: BinaryIO | None,
    url: str,
    no_verify: bool,
    timeout: int | None,
    skip_local: bool,
    no_download: bool,
    no_upload: bool,
):
    """Upload Bioregional Assesments to S3 bucket,."""
    from ckanext.datagovau.cli import _bioregional as b

    echo = partial(click.echo, file=log)

    echo(f"S3 Bioregional S3 ingest starting at {formatdate(localtime=True)}")
    try:
        source = b.prepare_source(source, url, no_verify, timeout)
    except ValueError as e:
        echo(f"Cannot prepare source: {e}")
        raise click.Abort from e

    echo(f"Reading data from {source.name}")

    try:
        datasets = json.load(source)
    except ValueError as e:
        echo(f"Cannot parse source as JSON: {e}")
        raise click.Abort from e
    b.Upload.setup(key, secret, region, profile, bucket)

    for record in b.converted_datasets(datasets, storage, skip_local, no_download):
        echo("-" * 80)
        echo(f"Ingesting dataset {record.dataset['id']}:")
        if record:
            echo(f"\t{record} exists on filesystem")
        else:
            download = b.download_record(record, no_verify, timeout, url)
            if not download or not isinstance(download, b.Download):
                echo(
                    f"\tCannot download {record.dataset['id']}:" f" {download.reason()}"
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
            echo("\tObject does not exist. Upload")
            upload.start(record)
            echo(f"\t{upload.key.key} uploaded to S3")

    if log and sender and receiver:
        log.close()
        b.send_bioregional_log(log, sender, receiver)
        click.secho(f"Successfully sent email to {receiver}", fg="green")
