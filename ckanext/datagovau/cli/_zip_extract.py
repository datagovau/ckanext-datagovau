from __future__ import annotations
import os
from datetime import datetime
import time
import logging
import zipfile

from typing import Any, Iterable, Optional

import ckanapi
import requests
import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)
INTERESTING_EXTENSIONS = {
    "csv",
    "xls",
    "xlsx",
    "json",
    "geojson",
    "shp",
    "kml",
}


def get_dataset_ids(ckan: ckanapi.LocalCKAN, days: int) -> Iterable[str]:
    fq = " AND ".join(
        [
            "+res_format:ZIP",
            "-harvest_portal:*",
            "-harvest_source_id:*",
            f"metadata_modified:[NOW-{days}DAY TO NOW]",
        ]
    )
    total = ckan.action.package_search(fq=fq, rows=0)["count"]
    chunk_size = 20
    for start in range(0, total, chunk_size):
        packages = ckan.action.package_search(
            fq=fq, rows=chunk_size, start=start
        )["results"]
        yield from (p["id"] for p in packages)


def select_extractable_resources(
    ckan: ckanapi.LocalCKAN, dataset_ids: Iterable[str]
) -> Iterable[tuple[dict[str, Any], dict[str, Any]]]:

    current_user = ckan.action.user_show(id=ckan.username)
    for id_ in dataset_ids:
        log.info("-" * 80)
        log.info(f"Processing dataset {id_}")
        try:
            dataset = ckan.action.package_show(id=id_)
        except ckanapi.NotFound:
            log.error(f"Dataset {id_} not found.")
            continue

        activity_list = ckan.action.package_activity_list(id=dataset["id"])
        # checking that bot was not last editor ensures no infinite loop
        # todo scan for last date of non-bot edit
        # Or last modified date could be compared with zip_extracted resources scan dates set.
        if activity_list and activity_list[0]["user_id"] == current_user["id"]:
            log.info("No changes since last extraction.")
            continue
        yield from (
            (r, dataset)
            for r in dataset["resources"]
            if r["format"].lower() == "zip" and r.get("zip_extract", "")
        )


def extract_resource(
    resource: dict[str, Any], path: str
) -> Optional[tuple[str, str]]:
    os.chdir(path)

    log.info(
        "Downloading resource %s from URL %s into %s",
        resource["id"],
        resource["url"],
        path,
    )

    try:
        resp = requests.get(resource["url"], stream=True)
    except requests.RequestException:
        log.exception("Cannot connect to URL")
        return

    if not resp.ok:
        log.error(
            "Cannot retrive resource: %s %s",
            resp.status_code,
            resp.reason,
        )
        return
    with open("input.zip", "wb") as dest:
        for chunk in resp.iter_content(1024 * 1024):
            dest.write(chunk)

    archive = zipfile.ZipFile("input.zip")
    archive.extractall()
    return recurse_directory(path)


def update_resource(
    file: str,
    path: str,
    ckan: ckanapi.LocalCKAN,
    resource: dict[str, Any],
    dataset: dict[str, Any],
) -> str:

    for res in dataset["resources"]:
        if res["name"] == file:
            res["last_modified"] = datetime.utcnow().isoformat()
            log.info("Updating resource %s", res["id"])
            ckan.call_action(
                "resource_update", res, files={"upload": open(path)}
            )
            break
    else:
        log.info("Creating new resource for file")
        res = ckan.call_action(
            "resource_create",
            {
                "package_id": dataset["id"],
                "name": file,
                "url": file,
                "parent_res": resource["id"],
                "zip_extracted": "True",
                "last_modified": datetime.utcnow().isoformat(),
            },
            files={"upload": open(path)},
        )

    return res["id"]


def submit_to_datapusher(res_id: str, ckan: ckanapi.LocalCKAN):
    # Give datapusher 10 seconds to start
    datapusher_working = True
    datapusher_present = True
    poll_time = 10
    count = 0
    timeout = 1200
    last_update_checked = False
    log.info("Checking to see if datapusher has been triggered...")
    while datapusher_working and datapusher_present and count < timeout:
        count += 1
        if count % poll_time == 0:
            try:
                datapusher_task = ckan.call_action(
                    "task_status_show",
                    {
                        "entity_id": res_id,
                        "task_type": "datapusher",
                        "key": "datapusher",
                    },
                )
                datapusher_working = datapusher_task.get("state", "") in [
                    "pending",
                    "submitting",
                ]
                if datapusher_working and not last_update_checked:
                    if (
                        "last_updated" not in datapusher_task
                        or (
                            datetime.utcnow()
                            - tk.h.date_str_to_datetime(
                                datapusher_task["last_updated"]
                            )
                        ).total_seconds()
                        > 86400
                    ):
                        log.info(
                            "Datapusher is in a stale pending state,"
                            " re-submitting job..."
                        )
                        log.info(
                            "Waiting for datapusher to ingest resource... "
                        )
                        ckan.call_action(
                            "datapusher_submit", {"resource_id": res_id}
                        )
                    last_update_checked = True
            except:
                datapusher_present = False

        if datapusher_working and datapusher_present:
            if count == 1:
                log.info("Waiting for datapusher to ingest resource... ")
        time.sleep(1)

    if datapusher_present:
        log.info(
            "Datapusher has finished pushing resource, continuing with Zip"
            " extraction..."
        )


def has_interesting_files(path: str) -> bool:
    for g in os.listdir(path):
        if g.split(".").pop().lower() in INTERESTING_EXTENSIONS:
            return True
    return False


def recurse_directory(path: str) -> Optional[tuple[str, str]]:
    if (
        len([fn for fn in os.listdir(path)]) < 3
        and len([ndir for ndir in os.listdir(path) if os.path.isdir(ndir)])
        == 1
    ):
        for f in os.listdir(path):
            if os.path.isdir(os.path.join(path, f)):
                return recurse_directory(os.path.join(path, f))

    os.chdir(path)
    numInteresting = len(
        [
            f
            for f in os.listdir(path)
            if (
                os.path.isfile(os.path.join(path, f))
                and (f.split(".").pop().lower() in INTERESTING_EXTENSIONS)
            )
        ]
    )
    for f in os.listdir(path):
        if os.path.isfile(os.path.join(path, f)) and numInteresting > 1:
            if f.split(".").pop().lower() in INTERESTING_EXTENSIONS:
                return (f, os.path.join(path, f))
        if os.path.isdir(os.path.join(path, f)):
            # only zip up folders if they contain at least one interesting file
            if has_interesting_files(os.path.join(path, f)):
                zipf = zipfile.ZipFile(f + ".zip", "w", zipfile.ZIP_DEFLATED)
                zipdir(f, zipf)
                zipf.close()
                return (f, f + ".zip")


def zipdir(path: str, ziph: zipfile.ZipFile):
    for root, dirs, files in os.walk(path):
        for file in files:
            ziph.write(os.path.join(root, file))
