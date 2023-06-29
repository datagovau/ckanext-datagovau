from __future__ import annotations

import contextlib
import glob
import logging
import os
import shutil
from datetime import datetime
from typing import Any, Dict, List, NamedTuple, Optional
from urllib.parse import quote

import ckan.plugins.toolkit as tk
import psycopg2

from ckanext.datagovau import utils

from . import config, load
from .exc import IngestionFail, fail
from .geoserver import get_geoserver

log = logging.getLogger(__name__)

ResourceGroup = List[Dict[str, Any]]


class GroupedResources(NamedTuple):
    tab: ResourceGroup
    tiff: ResourceGroup
    grid: ResourceGroup
    sld: ResourceGroup

    @classmethod
    def from_dataset(cls, dataset: dict[str, Any]):
        tab = []
        tiff = []
        grid = []
        sld = []

        source_formats = {f.lower() for f in config.formats("source")}

        for resource in dataset["resources"]:
            fmt = resource["format"].lower()
            is_source = utils.contains(fmt, source_formats)

            if "/geoserver" in resource["url"]:
                continue

            if utils.contains(fmt, {"sld"}):
                sld.append(resource)
            elif is_source:
                if utils.contains(fmt, {"tab", "mapinfo"}):
                    tab.append(resource)
                elif utils.contains(fmt, {"grid"}):
                    grid.append(resource)
                elif utils.contains(fmt, {"geotif"}):
                    tiff.append(resource)

        return cls(tab, tiff, grid, sld)


def _clean_dir(tempdir: str):
    shutil.rmtree(tempdir, ignore_errors=True)


def _get_cursor():
    # Connect to an existing database

    try:
        conn = psycopg2.connect(config.datastore())
    except:
        fail("I am unable to connect to the database.")
    # Open a cursor to perform database operations
    cur = conn.cursor()
    conn.set_isolation_level(0)
    # Execute a command: this creates a new table
    # cur.execute("create extension postgis")
    return cur, conn


def _clear_old_table(dataset: dict[str, Any]) -> str:
    cur, conn = _get_cursor()
    table_name = "ckan_" + dataset["id"].replace("-", "_")
    cur.execute('DROP TABLE IF EXISTS "' + table_name + '"')
    cur.close()
    conn.close()
    return table_name


def _apply_sld(
    name: str, workspace: str, layer_name: str, url=None, filepath=None
):
    server = get_geoserver()

    if url:
        r = server.get_style(workspace, name)
        if r.ok:
            with open("input.sld", "wb") as f:
                f.write(r.content)
            filepath = "input.sld"
        else:
            filepath = "input.sld"
            utils.download(url, filepath)
    elif filepath:
        log.info("sld downloaded")
        pass
    else:
        log.error("error accessing SLD")
        return

    r = server.get_style(workspace, name, quiet=True)
    if r.ok:
        log.info("Delete out old style in workspace")
        server.delete_style(workspace, name)

    server.create_style(
        workspace, {"style": {"name": name, "filename": name + ".sld"}}
    )

    sld_text = open(filepath, "r").read()
    mapping = {
        "application/vnd.ogc.sld+xml": "www.opengis.net/sld",
        "application/vnd.ogc.se+xml": "www.opengis.net/se",
    }
    for key, value in mapping.items():
        if value in sld_text:
            content_type = key
            break
    else:
        log.error("couldn't pick a sld content type")
        return

    payload = open(filepath, "rb")
    log.info("sld content type: %s", content_type)

    r = server.update_style(workspace, name, payload, content_type, raw=True)

    if r.status_code == 400:
        log.info("Delete out old style in workspace")
        server.delete_style(workspace, name)
        server.update_style(workspace, name, payload, content_type, raw=False)

    server.add_style(
        workspace,
        layer_name,
        name,
        {"layer": {"defaultStyle": {"name": name, "workspace": workspace}}},
    )


def _apply_sld_resources(
    sld_res: dict[str, Any], workspace: str, layer_name: str
):
    # Procedure for updating layer to use default style comes from
    # http://docs.geoserver.org/stable/en/user/rest/examples/curl.html that
    # explains the below steps in the 'Changing a layer style' section

    name = os.path.splitext(os.path.basename(sld_res["url"]))[0]

    server = get_geoserver()
    with server._session() as sess:
        r = sess.get(sld_res["url"])
        if r.ok:
            _apply_sld(
                name, workspace, layer_name, url=sld_res["url"], filepath=None
            )
        else:
            log.error("could not download SLD resource")


def _convert_resources(
    table_name: str, temp_dir: str, resources: GroupedResources
) -> tuple[bool, str]:
    using_grid = False
    native_crs = ""

    if len(resources.tab):
        native_crs = load.tab(resources.tab[0], table_name)
    elif len(resources.tiff):
        using_grid = True
        native_crs = load.tiff(resources.tiff[0], table_name)
    elif len(resources.grid):
        using_grid = True
        native_crs = load.grid(resources.grid[0], table_name, temp_dir)

    return using_grid, native_crs


def _get_geojson(table_name: str) -> tuple[str, str, str]:
    cur, conn = _get_cursor()
    select_query = (
        "SELECT ST_Extent(geom) as box,"
        "ST_Extent(ST_Transform(geom,4326)) as latlngbox, "
        "ST_AsGeoJSON(ST_Extent(ST_Transform(geom,4326))) as geojson "
        'from "{}"'
    ).format(table_name)
    cur.execute(select_query)
    # logger.debug(select_query)

    bbox, latlngbbox, bgjson = cur.fetchone()
    cur.close()
    conn.close()
    return bbox, latlngbbox, bgjson


def _perform_workspace_requests(
    datastore: str, workspace: str, table_name: Optional[str]
):
    if not table_name:
        dsdata = {
            "dataStore": {
                "name": datastore,
                "connectionParameters": {
                    "dbtype": "postgis",
                    "encode functions": "false",
                    "jndiReferenceName": "java:comp/env/jdbc/postgres",
                    # jndi name you have setup in tomcat http://docs.geoserver.org
                    # /stable/en/user/tutorials/tomcat-jndi/tomcat-jndi.html
                    # #configuring-a-postgresql-connection-pool
                    "Support on the fly geometry simplification": "true",
                    "Expose primary keys": "false",
                    "Estimated extends": "false",
                },
            }
        }
    else:
        dsdata = {
            "coverageStore": {
                "name": datastore,
                "type": "ImagePyramid",
                "enabled": True,
                "url": "file:data/" + table_name,
                "workspace": workspace,
            }
        }

    log.debug("_perform_workspace_requests():: dsdata = %s", dsdata)

    server = get_geoserver()
    r = server.create_store(workspace, bool(table_name), dsdata)
    log.debug("_perform_workspace_requests():: r = %s", r)

    if not r.ok:
        fail(f"Failed to create Geoserver store {r.url}: {r.content}")


def _update_package_with_bbox(
    bbox, latlngbbox, ftdata, dataset, native_crs, bgjson
):
    def _clear_box(string):
        return (
            string.replace("BOX", "")
            .replace("(", "")
            .replace(")", "")
            .replace(",", " ")
            .split(" ")
        )

    minx, miny, maxx, maxy = _clear_box(bbox)
    bbox_obj = {
        "minx": minx,
        "maxx": maxx,
        "miny": miny,
        "maxy": maxy,
        "crs": native_crs,
    }

    llminx, llminy, llmaxx, llmaxy = _clear_box(latlngbbox)
    llbbox_obj = {
        "minx": llminx,
        "maxx": llmaxx,
        "miny": llminy,
        "maxy": llmaxy,
        "crs": "EPSG:4326",
    }

    ftdata["featureType"]["nativeBoundingBox"] = bbox_obj
    ftdata["featureType"]["latLonBoundingBox"] = llbbox_obj
    if float(llminx) < -180 or float(llmaxx) > 180:
        log.debug("Invalid projection: %s", ftdata)
        fail(
            dataset["title"]
            + " has invalid automatic projection: "
            + native_crs
        )

    ftdata["featureType"]["srs"] = native_crs
    # logger.debug('bgjson({}), llbox_obj({})'.format(bgjson, llbbox_obj))
    if "spatial" not in dataset or dataset["spatial"] != bgjson:
        dataset["spatial"] = bgjson
        call_action("package_update", dataset)
    return bbox_obj


def _create_resources_from_formats(
    ws_addr, layer_name, bbox_obj, existing_formats, dataset, using_grid
):
    bbox_str = (
        "&bbox="
        + bbox_obj["minx"]
        + ","
        + bbox_obj["miny"]
        + ","
        + bbox_obj["maxx"]
        + ","
        + bbox_obj["maxy"]
        if bbox_obj
        else ""
    )

    for _format in config.formats("target"):
        url = (
            ws_addr
            + "wms?request=GetMap&layers="
            + layer_name
            + bbox_str
            + "&width=512&height=512&format="
            + quote(_format)
        )
        if _format == "image/png" and _format not in existing_formats:
            log.debug("Creating PNG Resource")
            call_action(
                "resource_create",
                {
                    "package_id": dataset["id"],
                    "name": dataset["title"] + " Preview Image",
                    "description": "View overview image of this dataset",
                    "format": _format,
                    "url": url,
                    "last_modified": datetime.now().isoformat(),
                },
            )
        elif _format in ["wms", "wfs"] and _format not in existing_formats:
            if _format == "wms":
                log.debug("Creating WMS API Endpoint Resource")
                call_action(
                    "resource_create",
                    {
                        "package_id": dataset["id"],
                        "name": dataset["title"]
                        + " - Preview this Dataset (WMS)",
                        "description": (
                            "View the data in this "
                            "dataset online via an online map"
                        ),
                        "format": "wms",
                        "url": ws_addr + "wms?request=GetCapabilities",
                        "wms_layer": layer_name,
                        "last_modified": datetime.now().isoformat(),
                    },
                )
            else:
                log.debug("Creating WFS API Endpoint Resource")
                call_action(
                    "resource_create",
                    {
                        "package_id": dataset["id"],
                        "name": dataset["title"]
                        + " Web Feature Service API Link",
                        "description": (
                            "WFS API Link for use in Desktop GIS tools"
                        ),
                        "format": "wfs",
                        "url": ws_addr + "wfs",
                        "wfs_layer": layer_name,
                        "last_modified": datetime.now().isoformat(),
                    },
                )
        elif _format in ["json", "geojson"] and not using_grid:
            url = (
                ws_addr
                + "wfs?request=GetFeature&typeName="
                + layer_name
                + "&outputFormat="
                + quote("json")
            )
            if not any([x in existing_formats for x in ["json", "geojson"]]):
                log.debug("Creating GeoJSON Resource")
                call_action(
                    "resource_create",
                    {
                        "package_id": dataset["id"],
                        "name": dataset["title"] + " GeoJSON",
                        "description": (
                            "For use in web-based data "
                            "visualisation of this collection"
                        ),
                        "format": "geojson",
                        "url": url,
                        "last_modified": datetime.now().isoformat(),
                    },
                )


def _delete_resources(dataset):
    server = get_geoserver()
    geoserver_resources = [
        res for res in dataset["resources"] if server.public_url in res["url"]
    ]

    for res in geoserver_resources:
        with contextlib.suppress(tk.ObjectNotFound):
            call_action("resource_delete", res, True)


def _prepare_everything(
    dataset: dict[str, Any], resources: GroupedResources, tempdir: str
) -> tuple[bool, str, str, str]:
    table_name = _clear_old_table(dataset)
    _clean_dir(config.data_dir(table_name))

    using_grid, native_crs = _convert_resources(
        table_name, tempdir, resources
    )

    server = get_geoserver()
    workspace = server.into_workspace(dataset["name"])

    log.debug("_prepare_everything():: GeoServer host = %s", server.host)
    log.debug("_prepare_everything():: workspace = %s", workspace)

    if server.check_workspace(workspace):
        server.drop_workspace(workspace)

    r = server.create_workspace(workspace)

    log.debug(
        "_prepare_everything():: Workspace creation request result r = %s", r
    )
    if not r.ok:
        fail(f"Failed to create Geoserver workspace: {r.content}")

    # load bounding boxes from database
    return using_grid, table_name, workspace, native_crs


def clean_assets(dataset_id: str, skip_grids: bool = False):
    dataset = _get_dataset(dataset_id)

    if not dataset:
        return

    # Skip cleaning datasets that may have a manually ingested grid
    is_grid = {"grid", "geotif"} & {
        r["format"].lower() for r in dataset["resources"]
    }
    if skip_grids and is_grid:
        return

    # clear old data table
    table_name = _clear_old_table(dataset)

    # clear rasterised directory
    _clean_dir(config.data_dir(table_name))

    server = get_geoserver()
    workspace = server.into_workspace(dataset["name"])

    if server.check_workspace(workspace):
        server.drop_workspace(workspace)

    _delete_resources(dataset)


def do_ingesting(dataset_id: str, force: bool):
    if not force and may_skip(dataset_id):
        return

    dataset = _get_dataset(dataset_id)
    assert dataset, "Dataset cannot be missing"
    log.info("Ingesting %s", dataset["id"])
    resources = GroupedResources.from_dataset(dataset)

    with utils.temp_dir(dataset["id"], "/tmp") as tempdir:
        log.debug("do_ingesting():: tempdir = %s", tempdir)
        os.chdir(tempdir)

        try:
            (
                using_grid,
                table_name,
                workspace,
                native_crs,
            ) = _prepare_everything(dataset, resources, tempdir)
        except IngestionFail as e:
            log.info("%s: %s", type(e), e)
            clean_assets(dataset_id)
            return

        datastore = workspace + ("cs" if using_grid else "ds")
        log.debug(
            "do_ingesting():: before _perform_workplace_requests().  datastore"
            " = %s",
            datastore,
        )

        try:
            _perform_workspace_requests(
                datastore, workspace, table_name if using_grid else None
            )
        except IngestionFail as e:
            log.info("{}: {}".format(type(e), e))
            clean_assets(dataset_id)
            return

        server = get_geoserver()
        layer_name = table_name

        if using_grid:
            layer_data = {
                "coverage": {
                    "name": layer_name,
                    "nativeName": table_name,
                    "title": dataset["title"],
                    "srs": native_crs,
                    "coverageParameters": {
                        "AllowMultithreading": False,
                        "SUGGESTED_TILE_SIZE": "1024,1024",
                        "USE_JAI_IMAGEREAD": False,
                    },
                }
            }
        else:
            layer_data = {
                "featureType": {
                    "name": layer_name,
                    "nativeName": table_name,
                    "title": dataset["title"],
                    "srs": native_crs,
                    ## XXX: if you want to test it locally and you don't have
                    ## access to geoserver's postgis DB, uncomment the line
                    ## below for bypassing the validation error
                    # "attributes": {"attribute": [{"name": "geom"},]},
                }
            }

        bbox_obj = None
        try:
            if not using_grid:
                bbox, latlngbbox, bgjson = _get_geojson(table_name)
                bbox_obj = (
                    _update_package_with_bbox(
                        bbox,
                        latlngbbox,
                        layer_data,
                        dataset,
                        native_crs,
                        bgjson,
                    )
                    if bbox
                    else None
                )
            log.debug("Create layer: %s", layer_data)

            r = server.create_layer(
                workspace, using_grid, datastore, layer_data
            )
            if not r.ok:
                fail(f"Failed to create Geoserver layer {r.url}: {r.content}")
        except IngestionFail as e:
            log.info("%s: %s", type(e), e)
            clean_assets(dataset_id)
            return

        sldfiles = glob.glob("*.[sS][lL][dD]")
        log.debug(
            "SLD Files %s. Grouped resources: %s", sldfiles, resources.sld
        )
        if len(sldfiles):
            _apply_sld(
                os.path.splitext(os.path.basename(sldfiles[0]))[0],
                workspace,
                layer_name,
                url=None,
                filepath=sldfiles[0],
            )
        else:
            log.info("no sld file in package")

        # With layers created, we can apply any SLDs
        if len(resources.sld):
            if resources.sld[0].get("url", "") == "":
                log.info("bad sld resource url")
            else:
                _apply_sld_resources(resources.sld[0], workspace, layer_name)
        else:
            log.info("no sld resources or sld url invalid")

        # Delete out all geoserver resources before rebuilding (this simplifies update logic)
        _delete_resources(dataset)
        dataset = _get_dataset(dataset["id"])
        assert dataset

        existing_formats = []
        for resource in dataset["resources"]:
            existing_formats.append(resource["format"].lower())

        ws_addr = (
            server.public_url
            + "/"
            + server.into_workspace(dataset["name"])
            + "/"
        )
        _create_resources_from_formats(
            ws_addr,
            layer_name,
            bbox_obj,
            existing_formats,
            dataset,
            using_grid,
        )

        log.info("Completed!")


def may_skip(dataset_id: str) -> bool:
    """Skip blacklisted orgs, datasets and datasets, updated by bot."""
    log.debug("Check if may skip %s", dataset_id)
    dataset = _get_dataset(dataset_id)

    if not dataset:
        log.debug("No package found to ingest")
        return True

    org = dataset.get("organization", {}).get("name")
    if not org:
        log.debug(
            "Package must be associate with valid organization to be ingested"
        )
        return True

    if org in config.blacklisted("org"):
        log.debug("%s in omitted_orgs blacklist", org)
        return True

    if dataset["name"] in config.blacklisted("pkg"):
        log.debug("%s in omitted_pkgs blacklist", dataset["name"])
        return True

    if dataset.get("harvest_source_id") or tk.asbool(
        dataset.get("spatial_harvester")
    ):
        log.debug("Harvested datasets are not eligible for ingestion")
        return True

    if dataset["private"]:
        log.debug("Private datasets are not eligible for ingestion")
        return True

    if dataset["state"] != "active":
        log.debug("Dataset must be active to ingest")
        return True

    # SLD resources(last group) are not checked
    grouped_resources = GroupedResources.from_dataset(dataset)[:-1]

    if not any(grouped_resources):
        log.debug("No geodata format files detected")
        return True

    if any(len(x) > 1 for x in grouped_resources):
        log.debug("Can not determine unique spatial file to ingest")
        return True

    activity_list = call_action("package_activity_list", {"id": dataset["id"], "include_hidden_activity": True})

    user = call_action("user_show", {"id": config.username()}, True)

    if activity_list and activity_list[0]["user_id"] == user["id"]:
        log.debug("Not updated since last ingest")
        return True

    return False


def _get_dataset(dataset_id: str) -> Optional[dict[str, Any]]:
    with contextlib.suppress(tk.ObjectNotFound):
        return call_action("package_show", {"id": dataset_id}, True)


def call_action(action: str, data: dict[str, Any], ignore_auth=False) -> Any:
    return tk.get_action(action)(
        {"user": config.username(), "ignore_auth": ignore_auth}, data
    )
