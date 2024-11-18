from __future__ import annotations

import os
import smtplib
import tempfile
from collections.abc import Iterable, Sequence
from email.message import EmailMessage
from email.utils import formatdate
from typing import Any, BinaryIO, TextIO

import boto3
import requests
from botocore.exceptions import ClientError

import ckan.plugins.toolkit as tk


class Download:
    def __init__(self, response: requests.Response):
        self.response = response

    def __bool__(self) -> bool:
        return self.response.ok

    def reason(self) -> str:
        if bool(self):
            return ""

        if (
            self.response.status_code == 400
            and self.response.content == "The dataset is not ready for downloading"
        ):
            return f"{self.response.url} is not ready for downloading."

        return self.response.reason

    def __len__(self):
        return int(self.response.headers.get("Content-Length", 0))

    def start(self, dest: File):
        with open(dest.filename, "wb") as f:
            for chunk in self.response.iter_content(chunk_size=1024):
                if chunk:  # filter out keep-alive new chunks
                    f.write(chunk)
                    yield len(chunk)


class File:
    def __init__(self, dataset: dict[str, Any], storage: str):
        storage = os.path.realpath(storage)
        self.dataset = dataset
        self.core_name = dataset["data_path"] + dataset["folder_name"]
        directory = os.path.join(storage, self.core_name)
        self.filename = directory + "/" + dataset["id"] + ".zip"

        if not os.path.exists(directory):
            os.makedirs(directory)

    def __str__(self):
        return self.filename

    def __bool__(self):
        return os.path.exists(self.filename)

    def __len__(self):
        return os.stat(self.filename).st_size

    def download_from(
        self, url: str, ignore_ssl: bool = False, timeout: int | None = None
    ) -> Download | Fail:
        session = requests.Session()
        session.verify = not ignore_ssl

        try:
            resp = session.get(
                url, params={"_view": "download"}, stream=True, timeout=timeout
            )
        except requests.ConnectionError as e:
            return Fail(e)
        except requests.Timeout as e:
            return Fail(e)

        return Download(resp)

    def prepare_uploader(
        self,
    ):
        return Upload(os.path.join(self.core_name, self.dataset["id"] + ".zip"))


class Fail:
    def __init__(self, err: Any):
        self.err = err

    def reason(self):
        return self.err


class Upload:
    @classmethod
    def setup(
        cls,
        key: str | None,
        secret: str | None,
        region: str | None,
        profile: str | None,
        bucket: str,
    ):
        boto3.setup_default_session(
            aws_access_key_id=key,
            aws_secret_access_key=secret,
            region_name=region,
            profile_name=profile,
        )
        cls.bucket = bucket

    @property
    def obj(self):
        if not hasattr(self, "_obj"):
            try:
                self._obj = self.key.get()
            except ClientError:
                self._obj = None
        return self._obj

    def __init__(self, filename: str):
        name = "bioregionalassessments/" + filename.replace("./", "")
        self.key = boto3.resource("s3").Object(self.bucket, name)

    def __bool__(self):
        return bool(self.obj)

    def __len__(self):
        if self.obj:
            return self.obj["ContentLength"]
        return 0

    def start(self, src: File):
        self.key.upload_file(src.filename)


def send_bioregional_log(log: TextIO, sender: str, receiver: Sequence[str]):
    conn = _get_smtp_connection()
    msg = EmailMessage()

    msg.set_content(
        f"Bioregional S3 Ingest completed at {formatdate()} (UTC). Attached is"
        " the S3 ingest log.",
        cte="base64",
    )

    msg["Subject"] = "Bioregional S3 Ingest Completion Notice"
    msg["From"] = sender
    msg["Date"] = formatdate(localtime=True)

    with open(log.name, "rb") as attachment:
        msg.add_attachment(
            attachment.read(),
            filename=log.name,
            maintype="text",
            subtype="plain",
        )

    conn.sendmail(sender, receiver, msg.as_string())
    conn.quit()


def _get_smtp_connection():
    smtp_server = tk.config["smtp.server"]
    smtp_starttls = tk.config["smtp.starttls"]
    smtp_user = tk.config["smtp.user"]
    smtp_password = tk.config["smtp.password"]

    smtp_connection = smtplib.SMTP(smtp_server)
    smtp_connection.ehlo()

    # If 'smtp.starttls' is on in CKAN config, try to put the SMTP
    # connection into TLS mode.
    if smtp_starttls:
        smtp_connection.starttls()
        # Re-identify ourselves over TLS connection.
        smtp_connection.ehlo()

    # If 'smtp.user' is in CKAN config, try to login to SMTP server.
    if smtp_user:
        smtp_connection.login(smtp_user, smtp_password)

    return smtp_connection


def converted_datasets(
    datasets: Iterable[dict[str, Any]],
    storage: str,
    skip_local: bool,
    no_download: bool,
):
    for dataset in datasets:
        data = {
            "id": dataset["@id"].split("/")[-1],
            "data_path": dataset[
                "http://data.bioregionalassessments.gov.au/def/ba#ba_dataPath"
            ][0]["@value"],
            "folder_name": dataset[
                "http://data.bioregionalassessments.gov.au/def/ba#ba_folderName"
            ][0]["@value"],
            "created": dataset["http://purl.org/dc/elements/1.1/created"][0]["@value"],
        }
        src = File(data, storage)
        if src and skip_local:
            continue
        if not src and no_download:
            continue
        yield src


def download_record(record: File, no_verify: bool, timeout: int | None, url: str):
    dataset_url = url.rstrip("/") + "/" + record.dataset["id"]
    return record.download_from(dataset_url, no_verify, timeout)


def prepare_source(
    source: BinaryIO | None,
    url: str,
    ignore_ssl: bool = False,
    timeout: int | None = None,
) -> BinaryIO:
    if source:
        return source

    session = requests.Session()
    session.verify = not ignore_ssl

    resp = session.get(
        url,
        params={"_format": "application/json-ld"},
        headers={"Accept": "application/json-ld"},
        timeout=timeout,
    )

    if not resp.ok:
        raise ValueError(f"{resp.status_code} {resp.reason} {resp.url}")

    with tempfile.NamedTemporaryFile(
        "wb", delete=False, prefix="ba-", suffix=".json"
    ) as dest:
        for chunk in resp.iter_content(1024):
            dest.write(chunk)

    return open(dest.name, "rb")  # noqa: SIM115
