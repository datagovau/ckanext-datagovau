from __future__ import annotations

import re
from typing import Any, NamedTuple

import requests

import ckan.plugins.toolkit as tk

from ckanext.datagovau.geoserver_utils import CONFIG_PUBLIC_URL, CONFIG_URL, _timeout

from .exc import BadConfigError


class GeoServer(NamedTuple):
    host: str
    user: str
    password: str
    public_url: str

    def into_workspace(self, raw: str):
        if any(c.isalpha() for c in raw):
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
            return s.delete(url + "?recurse=true&quietOnNotFound", timeout=_timeout())

    def create_workspace(self, workspace: str):
        url = self._workspace_url()
        with self._session() as s:
            return s.post(
                url,
                json={"workspace": {"name": workspace}},
                timeout=_timeout(),
            )

    def create_store(self, workspace: str, is_cs: bool, data: dict[str, Any]):
        url = self._store_url(workspace, is_cs)
        with self._session() as s:
            return s.post(url, json=data, timeout=_timeout())

    def create_layer(
        self, workspace: str, is_cs: bool, store: str, data: dict[str, Any]
    ):
        url = self._layer_url(workspace, is_cs, store)
        with self._session() as s:
            return s.post(url, json=data, timeout=_timeout())

    def get_style(self, workspace: str, style: str, quiet: bool = False):
        url = self._style_url(workspace, style)
        params = {}
        if quiet:
            params["quietOnNotFound"] = True
        with self._session() as s:
            return s.get(url, params=params, timeout=_timeout())

    def create_style(self, workspace: str, data: dict[str, Any]):
        url = self._style_url(workspace)
        with self._session() as s:
            return s.post(url, json=data, timeout=_timeout())

    def delete_style(self, workspace: str, style: str):
        url = self._style_url(workspace, style)
        with self._session() as s:
            return s.delete(url, timeout=_timeout())

    def update_style(
        self,
        workspace: str,
        style: str,
        data: Any,
        content_type: str,
        raw: bool,
    ):
        url = self._style_url(workspace, style)
        with self._session() as s:
            return s.put(
                url,
                data=data,
                headers={"Content-type": content_type},
                params={"raw": raw},
                timeout=_timeout(),
            )

    def add_style(self, workspace: str, layer: str, style: str, data: dict[str, Any]):
        url = f"{self.host}rest/layers/{layer}"
        with self._session() as s:
            return s.put(url, json=data, timeout=_timeout())

    def _workspace_url(self, workspace: str = "") -> str:
        return f"{self.host}rest/workspaces/{workspace}"

    def _store_url(self, workspace: str, is_cs: bool, store: str = "") -> str:
        type_ = "coveragestores" if is_cs else "datastores"
        base = self._workspace_url(workspace)

        return f"{base}/{type_}/{store}"

    def _style_url(self, workspace: str, style: str = "") -> str:
        base = self._workspace_url(workspace)
        return f"{base}/styles/{style}"

    def _layer_url(self, workspace: str, is_cs: bool, store: str) -> str:
        type_ = "coveragestores" if is_cs else "datastores"
        sub_type = "coverages" if is_cs else "featuretypes"
        base = self._workspace_url(workspace)

        return f"{base}/{type_}/{store}/{sub_type}"

    def _session(self):
        session = requests.Session()
        session.auth = (self.user, self.password)
        return session


def get_geoserver() -> GeoServer:
    regex = [
        r"^\s*(?P<db_type>\w*)",
        "://",
        "(?P<db_user>[^:]*)",
        ":?",
        "(?P<db_pass>.*)",
        "@",
        "(?P<db_host>[^/:]*)",
        ":?",
        "(?P<db_port>[^/]*)",
        "/",
        r"(?P<db_name>[\w.-]*)",
    ]
    admin_url = tk.config[CONFIG_URL]
    public_url = tk.config[CONFIG_PUBLIC_URL]

    match = re.match("".join(regex), admin_url)

    if not match:
        raise BadConfigError(f"Invalid GEOSERVER_ADMIN_URL: {admin_url}")

    info = match.groupdict()
    host = "https://" + info["db_host"]

    port = info.get("db_port", "")
    if port:
        host += ":" + port

    host += "/" + info["db_name"] + "/"
    return GeoServer(host, info["db_user"], info["db_pass"], public_url)
