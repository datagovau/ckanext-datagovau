import contextlib
import json
import logging
import time
from typing import Any, Optional
from urllib.parse import quote

import ckan.plugins.toolkit as tk
import psycopg2
import requests

from ckanext.datagovau import utils

log = logging.getLogger(__name__)

CONFIG_PUBLIC_URL = "ckanext.datagovau.spatialingestor.geoserver.public_url"
CONFIG_TIMEOUT = "ckanext.datagovau.spatialingestor.request_timeout"
CONFIG_IGNORE = "ckanext.datagovau.spatialingestor.pkg_blacklist"
CONFIG_URL = "ckanext.datagovau.spatialingestor.geoserver.url"

DEFAULT_IGNORE = []
DEFAULT_TIMEOUT = 10


def _timeout():
    return tk.asint(tk.config.get(CONFIG_TIMEOUT, DEFAULT_TIMEOUT))


class Geoserverobj:
    def __init__(self):
        self.filtered_resources = {
            "shp": [],
            "kml": [],
        }
        self.res_group_formats = {
            "shp": ["shp", "shapefile"],
            "kml": ["kml", "kmz"],
        }
        self.geoserver_url = tk.config.get(CONFIG_URL)
        self.geoserver_public_url = tk.config.get(CONFIG_PUBLIC_URL)
        self.geoserver_workspace = "WORKSPACE"

        self.datastore = ""
        self.table_name = ""
        self.workspace = ""
        self.native_crs = ""
        self.task_dict = {}
        self.main_res = None
        self.geo_res_frmts = {}

    def get_geo_res_list(self, dataset):
        is_there_res = False
        resources = [res for res in dataset.get("resources")]
        for format_group in self.res_group_formats:
            for resource in resources:
                fmt = resource["format"].lower()

                is_source = (
                    True
                    if fmt in self.res_group_formats[format_group]
                    else False
                )
                if "/geoserver" in resource["url"]:
                    self.geo_res_frmts[resource["format"].lower()] = resource[
                        "id"
                    ]
                    continue

                if is_source:
                    if utils.contains(
                        fmt, self.res_group_formats[format_group]
                    ):
                        self.filtered_resources[format_group].append(resource)
                        is_there_res = True
        return is_there_res

    def run_imports(self):
        tasks = self.get_all_tasks()
        if tasks and tasks.get("imports"):
            for task in tasks["imports"]:
                if task["state"].lower() in ["pending", "ready"]:
                    log.info("Execute task {0}".format(task["id"]))
                    split_url = task["href"].split("/geoserver")
                    split_url[0] = self.geoserver_url
                    api_point = "".join(split_url)
                    post = requests.post(api_point)
                    if post.ok:
                        log.info("Import executed for layer creation.")

    def get_all_tasks(self):
        tasks = requests.get(self.geoserver_url + "/rest/imports")
        if tasks.status_code == 200:
            return tasks.json()

    def ingest_resource(self):
        if not self.filtered_resources:
            return False

        groups = [g for g in self.filtered_resources.values() if g]
        if not groups:
            return False
        res = groups[0][0]

        log.info("Adding {0} to import.".format(res["id"]))
        url = res.get("url")
        self.main_res = res
        import_data = {
            "import": {
                "targetWorkspace": {"workspace": {"name": self.workspace}},
                "targetStore": {"dataStore": {"name": self.datastore}},
                "data": {
                    "type": "remote",
                    "location": url,
                },
            }
        }

        res_import = requests.post(
            self.geoserver_url + "/rest/imports",
            data=json.dumps(import_data),
            headers={"Content-Type": "application/json"},
        )
        if res_import.ok:
            import_data = res_import.json()
            if import_data["import"].get("tasks"):
                task = import_data["import"]["tasks"][0]
                if task["state"] != "ERROR":
                    self.task_dict = task
                    data = {"layer": {"name": self.table_name}}
                    if task.get("state") and task["state"] == "NO_CRS":
                        data["layer"]["srs"] = self.native_crs

                    upd_l = self.update_layer(task["href"], data)
                    if upd_l.ok:
                        log.info("Layer is being updated.")
                        return True
                    else:
                        log.error(
                            "Layer wasn't updated due to"
                            " some unexpected issues."
                        )
                        log.error(
                            "Status code is {0}".format(upd_l.status_code)
                        )
                else:
                    log.error("An error appeard during task, skip.")
        else:
            log.error(
                "Something went wrong while sending"
                " resource to import. Status code is {0}".format(
                    res_import.status_code
                )
            )
            log.error(f"{res_import.content}")
        return False

    def get_data(self, url):
        with self._session() as s:
            api_point = self.update_geo_url(url)
            return s.get(api_point, json={}, timeout=_timeout())

    def upload_file_to_datastore(
        self,
        workspace,
        datastore,
        storage_type,
        file,
        filename,
        content_type,
        extension,
    ):
        rsrc = requests.get(file)
        with self._session() as s:
            resp = s.put(
                f"{self.geoserver_url}/rest/workspaces/{workspace}/{storage_type}/{datastore}/file{extension}",
                files={"file": rsrc.content},
                headers={"Content-type": content_type},
                timeout=_timeout(),
            )

    def update_datastore(self, workspace, datastore, storage_type, data):
        with self._session() as s:
            resp = s.put(
                f"{self.geoserver_url}/rest/workspaces/{workspace}/{storage_type}/{datastore}.json",
                json=data,
                timeout=_timeout(),
            )

    def get_task(self, url):
        with self._session() as s:
            api_point = self.update_geo_url(url)
            return s.get(api_point, json={}, timeout=_timeout())

    def update_task(self, url, data):
        with self._session() as s:
            api_point = self.update_geo_url(url)
            resp = s.put(api_point, json=data, timeout=_timeout())

    def get_file_format(self, url):
        with self._session() as s:
            split_url = url.split("/geoserver")
            split_url[0] = self.geoserver_url
            api_point = "".join(split_url) + "/data"
            resp = s.get(api_point, json={}, timeout=_timeout())
            if resp.ok and resp.status_code == 200:
                data = resp.json()
                if not data["format"] and data.get("file"):
                    file = data["file"]
                    file_ext = file.split(".")
                    if file_ext:
                        return file_ext[-1]
        return None

    def update_layer(self, url, data):
        with self._session() as s:
            split_url = url.split("/geoserver")
            split_url[0] = self.geoserver_url
            api_point = "".join(split_url) + "/layer/"
            return s.put(api_point, json=data, timeout=_timeout())

    def into_workspace(self, raw):
        if any([c.isalpha() for c in raw]):
            if not raw[0].isalpha():
                raw += "-"
                while not raw[0].isalpha():
                    first_literal = raw[0]
                    raw = raw[1:]
                    if first_literal.isdigit():
                        raw += first_literal
                if raw[-1] == "-":
                    raw = raw[:-1]
        else:
            raw = "ckan-" + raw

        return raw

    def check_workspace(self, workspace: str) -> bool:
        url = self._workspace_url(workspace)
        with self._session() as s:
            return s.head(url, timeout=_timeout()).ok

    def drop_workspace(self, workspace: str):
        url = self._workspace_url(workspace)
        with self._session() as s:
            return s.delete(
                url + "?recurse=true&quietOnNotFound", timeout=_timeout()
            )

    def create_workspace(self, workspace: str):
        url = self._workspace_url()
        self.workspace = workspace
        with self._session() as s:
            return s.post(
                url,
                json={"workspace": {"name": workspace}},
                timeout=_timeout(),
            )

    def _workspace_url(self, workspace: str = "") -> str:
        return f"{self.geoserver_url}/rest/workspaces/{workspace}"

    def _session(self):
        session = requests.Session()
        return session

    def _convert_resources(self):
        using_grid = False
        native_crs = "EPSG:4326"
        self.native_crs = native_crs

        return using_grid

    def _clear_old_table(self, dataset, table_name):
        self.table_name = table_name
        log.info(
            "Delete existing rows in DB for dataset {0}".format(dataset["id"])
        )
        cur, conn = _get_cursor()
        table_name = "ckan_" + dataset["id"].replace("-", "_")
        cur.execute('DROP TABLE IF EXISTS "' + table_name + '"')
        cur.close()
        conn.close()

    def create_store(
        self, datastore: str, workspace: str, table_name: Optional[str]
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
                    "type": " ImagePyramid",
                    "enabled": True,
                    "url": "file:data/" + table_name,
                    "workspace": workspace,
                }
            }

        self.datastore = datastore
        r = self._create_store(workspace, bool(table_name), dsdata)
        log.debug("Datastore created")

        if not r.ok:
            log.error(f"Failed to create Geoserver store {r.url}: {r.content}")

    def _create_store(self, workspace: str, is_cs: bool, data):
        url = self._store_url(workspace, is_cs)
        with self._session() as s:
            return s.post(url, json=data, timeout=_timeout())

    def _store_url(self, workspace: str, is_cs: bool, store: str = "") -> str:
        type_ = "coveragestores" if is_cs else "datastores"
        base = self._workspace_url(workspace)

        return f"{base}/{type_}/{store}"

    def update_geo_url(self, url):
        split_url = url.split("/geoserver")
        split_url[0] = self.geoserver_url
        api_point = "".join(split_url)
        return api_point

    def _delete_resources(self, dataset_dict):
        geoserver_resources = [
            res
            for res in dataset_dict.get("resources")
            if self.geoserver_public_url in res["url"]
        ]

        for res in geoserver_resources:
            time.sleep(5)
            with contextlib.suppress(tk.ObjectNotFound):
                call_action("resource_delete", res, True)

    def _get_layer(self):
        if self.task_dict:
            split_url = self.task_dict["href"].split("/geoserver")
            split_url[0] = self.geoserver_url
            api_point = "".join(split_url)
            with self._session() as s:
                return s.get(api_point + "/layer", json={}, timeout=_timeout())
        return None

    def _create_resources_from_formats(
        self, workspace, layer_name, existing_formats, pkg_id, using_grid
    ):
        if self.main_res:
            ##  Get updated dataset data before creating new resources
            dataset = tk.get_action("package_show")({}, {"id": pkg_id})

            bbox_str = ""
            layer_info = self._get_layer()
            log.debug("Check if layer created")
            if layer_info.ok:
                layer_data = layer_info.json()
                log.debug("Layer created")
                bbox_str = (
                    "&bbox="
                    + str(layer_data["layer"]["bbox"]["minx"])
                    + ","
                    + str(layer_data["layer"]["bbox"]["miny"])
                    + ","
                    + str(layer_data["layer"]["bbox"]["maxx"])
                    + ","
                    + str(layer_data["layer"]["bbox"]["maxy"])
                    if layer_data["layer"]["bbox"]
                    else ""
                )
            ws_addr = self.geoserver_public_url + "/" + workspace + "/"

            if "geojson" in self.geo_res_frmts.keys():
                self.geo_res_frmts["json"] = self.geo_res_frmts["geojson"]
            for _format in tk.aslist(
                tk.config.get(
                    "ckanext.datagovau.spatialingestor.target_formats", []
                )
            ):
                time.sleep(5)
                action_word = "Creating"
                action = "resource_create"
                data = {
                    "package_id": dataset["id"],
                    "last_modified": self.main_res["last_modified"],
                }
                if _format in self.geo_res_frmts:
                    action = "resource_patch"
                    action_word = "Patching"
                    data["id"] = self.geo_res_frmts[_format]

                log.debug(
                    f"'{action}' action is applied to '{_format}' resource"
                )

                if _format == "kml" and (
                    "kml" not in existing_formats or action == "resource_patch"
                ):
                    log.debug(f"{action_word} KML Resource")
                    if bbox_str:
                        url = (
                            ws_addr
                            + "wms?request=GetMap&layers="
                            + layer_name
                            + bbox_str
                            + "&width=512&height=512&format="
                            + quote(_format)
                        )
                    else:
                        url = ws_addr + "wms/kml?layers=" + layer_name
                    data["name"] = dataset["title"] + " KML"
                    data["description"] = (
                        "View a map of this dataset in web "
                        "and desktop spatial data tools"
                        " including Google Earth"
                    )
                    data["format"] = _format
                    data["url"] = url
                    call_action(
                        action,
                        data,
                    )
                elif _format in ["wms", "wfs"] and (
                    _format not in existing_formats
                    or action == "resource_patch"
                ):
                    if _format == "wms":
                        log.debug(f"{action_word} WMS API Endpoint Resource")
                        data["name"] = (
                            dataset["title"] + " - Preview this Dataset (WMS)"
                        )
                        data["description"] = (
                            "View the data in this "
                            "dataset online via an online map"
                        )
                        data["format"] = "wms"
                        data["url"] = ws_addr + "wms?request=GetCapabilities"
                        data["wms_layer"] = layer_name
                        a = call_action(
                            action,
                            data,
                        )
                        log.debug(a)
                    else:
                        log.debug(f"{action_word} WFS API Endpoint Resource")
                        data["name"] = (
                            dataset["title"] + " Web Feature Service API Link"
                        )
                        data[
                            "description"
                        ] = "WFS API Link for use in Desktop GIS tools"
                        data["format"] = "wfs"
                        data["url"] = ws_addr + "wfs"
                        data["wfs_layer"] = layer_name
                        call_action(
                            action,
                            data,
                        )
                elif _format in ["json", "geojson"] and (
                    _format not in existing_formats
                    or action == "resource_patch"
                ):
                    url = (
                        ws_addr
                        + "wfs?request=GetFeature&typeName="
                        + layer_name
                        + "&outputFormat="
                        + quote("json")
                    )
                    if not any(
                        [x in existing_formats for x in ["json", "geojson"]]
                    ):
                        log.debug(f"{action_word} GeoJSON Resource")
                        data["name"] = dataset["title"] + " GeoJSON"
                        data["description"] = (
                            "For use in web-based data "
                            "visualisation of this collection"
                        )
                        data["format"] = "geojson"
                        data["url"] = url
                        call_action(
                            action,
                            data,
                        )


def call_action(action: str, data, ignore_auth=False) -> Any:
    return tk.get_action(action)(
        {
            "user": tk.config.get(
                "ckanext.datagovau.spatialingestor.username", ""
            ),
            "ignore_auth": ignore_auth,
        },
        data,
    )


def _get_cursor():
    # Connect to an existing database
    try:
        conn = psycopg2.connect(
            tk.config["ckanext.datagovau.spatialingestor.datastore.url"]
        )
    except:
        log.error("I am unable to connect to the database.")
        raise
    # Open a cursor to perform database operations
    cur = conn.cursor()
    conn.set_isolation_level(0)
    # Execute a command: this creates a new table
    # cur.execute("create extension postgis")
    return cur, conn


def run_ingestor(pkg_id: str):
    ignored = tk.aslist(tk.config.get(CONFIG_IGNORE, DEFAULT_IGNORE))
    if pkg_id in ignored:
        log.debug("%s is ignored")
        return

    log.info(f"Send {pkg_id} to ingest")
    dataset_dict = tk.get_action("package_show")({}, {"id": pkg_id})
    table_name = "ckan_" + dataset_dict["id"].replace("-", "_")
    geo_obj = Geoserverobj()

    log.debug("Prepare filtered resources")
    res_group_exist = geo_obj.get_geo_res_list(dataset_dict)
    if not res_group_exist:
        log.info("No ingest resource for this Dataset")
        return

    log.debug("Clear all exisitng Data in DB before start the process")
    geo_obj._clear_old_table(dataset_dict, table_name)

    log.debug("Checking Workspace for existence.")
    workspace = geo_obj.into_workspace(dataset_dict["name"])

    if geo_obj.check_workspace(workspace):
        log.debug("Dropping existing Workspace")
        geo_obj.drop_workspace(workspace)

    log.debug("Creating new workspace for the Dataset")
    r = geo_obj.create_workspace(workspace)

    using_grid = geo_obj._convert_resources()

    datastore = workspace + ("cs" if using_grid else "ds")

    try:
        log.debug("Creating new Datastore for the Dataset")
        geo_obj.create_store(
            datastore, workspace, table_name if using_grid else None
        )
    except Exception as e:
        log.exception("Cannot create store for %s", pkg_id)
        return

    log.debug("Check if ingest resource exists")

    log.debug("Send first resource to Import")

    if not geo_obj.ingest_resource():
        log.error(
            "Datset %s  wasn't ingested during ingest process. Skipping...",
            dataset_dict["name"],
        )
        return

    log.debug("Run Dataset import.")
    geo_obj.run_imports()

    existing_formats = []
    for resource in dataset_dict["resources"]:
        existing_formats.append(resource["format"].lower())

    log.debug("Creating new resources for Dataset")
    geo_obj._create_resources_from_formats(
        workspace,
        table_name,
        existing_formats,
        pkg_id,
        using_grid,
    )


def delete_ingested(pkg_id):
    dataset_dict = call_action("package_show", {"id": pkg_id})
    if not dataset_dict:
        return

    table_name = "ckan_" + dataset_dict["id"].replace("-", "_")
    geo_obj = Geoserverobj()
    geo_obj._delete_resources(dataset_dict)

    geo_obj._clear_old_table(dataset_dict, table_name)

    workspace = geo_obj.into_workspace(dataset_dict["name"])

    if geo_obj.check_workspace(workspace):
        log.info("Dropping existing Workspace")
        geo_obj.drop_workspace(workspace)
