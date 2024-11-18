from __future__ import annotations

import grp
import pwd
import re
from typing import Literal

import ckan.plugins.toolkit as tk

from .exc import BadConfigError


def username() -> str:
    return tk.config["ckanext.datagovau.spatialingestor.username"]


def blacklisted(entity: Literal["org", "pkg"]) -> list[str]:
    return tk.config[f"ckanext.datagovau.spatialingestor.{entity}_blacklist"]


def formats(type_: Literal["target", "source"]) -> list[str]:
    return tk.config[f"ckanext.datagovau.spatialingestor.{type_}_formats"]


def datastore() -> str:
    return tk.config["ckanext.datagovau.spatialingestor.datastore.url"]


def ogr2ogr() -> str | None:
    return tk.config["ckanext.datagovau.spatialingestor.ogr2ogr.executable"]


def db_settings() -> dict[str, str]:
    regex = [
        "^\\s*(?P<db_type>\\w*)",
        "://",
        "(?P<db_user>[^:]*)",
        ":?",
        "(?P<db_pass>[^@]*)",
        "@",
        "(?P<db_host>[^/:]*)",
        ":?",
        "(?P<db_port>[^/]*)",
        "/",
        "(?P<db_name>[\\w.-]*)",
    ]

    url = datastore()
    match = re.match("".join(regex), url)
    if not match:
        raise BadConfigError(f"Invalid datastore.url: {url}")
    postgis_info = match.groupdict()

    db_port = postgis_info.get("db_port", "")

    return {
        "dbname": postgis_info.get("db_name"),
        "user": postgis_info.get("db_user"),
        "password": postgis_info.get("db_pass"),
        "host": postgis_info.get("db_host"),
        "port": db_port,
    }


def db_param():
    db = db_settings()
    result = (
        "PG:dbname='"
        + db["dbname"]
        + "' host='"
        + db["host"]
        + "' user='"
        + db["user"]
        + "' password='"
        + db["password"]
        + "'"
    )

    if db["port"]:
        result += " port='" + db["port"] + "'"

    return result


def large_size() -> int:
    return tk.config["ckanext.datagovau.spatialingestor.large_file_threshold"]


def data_dir(native_name: str) -> str:
    name = tk.config["ckanext.datagovau.spatialingestor.geoserver.base_dir"].rstrip("/")
    return name + "/" + native_name


def os_owner() -> tuple[int, int]:
    uid = pwd.getpwnam(
        tk.config["ckanext.datagovau.spatialingestor.geoserver.os_user"]
    ).pw_uid
    gid = grp.getgrnam(
        tk.config["ckanext.datagovau.spatialingestor.geoserver.os_group"]
    ).gr_gid
    return uid, gid
