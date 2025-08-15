from __future__ import annotations

import logging
from functools import reduce
from typing import Any, Callable

import requests
from pyproj import CRS, Transformer

import ckan.plugins.toolkit as tk

from ckanext.toolbelt.decorators import Cache
from ckanext.toolbelt.utils.cache import MaybeNotCached

from ckanext.datagovau import config

log = logging.getLogger(__name__)

suburb_url = "https://maps.six.nsw.gov.au/arcgis/rest/services/public/NSW_Administrative_Boundaries/MapServer/0/query"


def cache_key_strategy(func: Callable[..., Any], *args: Any) -> str:
    fn = func.__name__.replace("_", ":")
    site_id = tk.config["ckan.site_id"]
    base = f"{site_id}:dga:{fn}"
    for part in args:
        base += f":{part}"
    return base


cache = Cache(key=cache_key_strategy)


@cache
def lga_names() -> MaybeNotCached[list[str]]:
    """Return all registered LGA names."""
    url = config.lga_url()
    try:
        names = _get_names(url, "lganame")
    except requests.ConnectionError:
        log.exception("Cannot connect to LGA service at %s", url)
        names = []
    except KeyError:
        log.exception("Cannot extract LGA names")
        names = []

    if not names:
        names = cache.dont_cache(names)
    return names


def _get_names(url: str, prop: str) -> list[str]:
    """Pull names from map service."""
    params = _arcgis_params()
    timeout = config.lga_timeout()
    try:
        resp = requests.get(url, params=params, timeout=timeout).json()
    except requests.Timeout:
        log.warning("Fetch names timeout: %s", url)
        return []
    name_attribute = config.lga_name()
    return [f["attributes"][name_attribute] for f in resp["results"]]


def _arcgis_params(
    search_text: str | None = None,
) -> dict[str, Any]:
    """Build request parameters for map service."""
    params: dict[str, Any] = {}
    params.update(config.lga_params())
    params["f"] = "pjson"
    if search_text:
        params["searchText"] = search_text
    return params


@cache
def lga_geometry(name: str):
    """Transform LGA name into geometry."""
    try:
        geometry = _get_geometry(name, "lganame", config.lga_url())
    except requests.ConnectionError:
        geometry = {}

    if not geometry:
        geometry = cache.dont_cache(geometry)
    return geometry


def _get_geometry(name: str, prop: str, url: str) -> str:
    """Pull geometry from map service."""
    # Handle names like "O'CONNELL"
    params = _arcgis_params(name)
    timeout = config.lga_timeout()
    log.info("Fetching zone geometry for %s", name)

    try:
        resp = requests.get(url, params=params, timeout=timeout).json()
    except requests.Timeout:
        log.warning("Fetch zone timeout for %s: %s", name, url)
        return ""

    name_attribute = config.lga_name()

    for item in resp["results"]:
        if item["attributes"][name_attribute] == name and "geometry" in item:
            break

    else:
        log.warning("Cannot find LGA geometry for %s", name)
        return ""

    coords = reduce(
        lambda acc, xy: [
            max(acc[0], xy[0]),
            max(acc[1], xy[1]),
            min(acc[2], xy[0]),
            min(acc[3], xy[1]),
        ],
        # the first ring is the most essential. But it may have sense to chain
        # all rings
        item["geometry"]["rings"][0],
        [-float("inf"), -float("inf"), float("inf"), float("inf")],
    )

    ref = item["geometry"]["spatialReference"]

    target_crs = CRS.from_epsg(4326)
    source_crs = CRS.from_epsg(ref["latestWkid"])
    # For ESRI-specific WKIDs that don't match EPSG(looks like we don't have
    # such, but may be useful in future) source_crs =
    # CRS.from_user_input(f"ESRI:{ref['wkid']}")
    transformer = Transformer.from_crs(source_crs, target_crs, always_xy=True)

    ne_lon, ne_lat = transformer.transform(coords[0], coords[1])
    sw_lon, sw_lat = transformer.transform(coords[2], coords[3])

    # To avoid the cases with very small areas such us with Syndey, when bbox
    # has coordinates:
    # 151.17480402422814,-33.92439090072223,151.2331074877883,-33.85364926147323;
    # in the end coordinates will be rounded to 151.2, -33.9, 151.2, -33.9 west
    # == east, north == south
    if round(ne_lon, 1) == round(sw_lon, 1):
        sw_lon = round(sw_lon, 1) + 0.1
    if round(ne_lat, 1) == round(sw_lat, 1):
        sw_lat = round(sw_lat, 1) + 0.1
    log.info("LGA geometry for %s successfully obtained", name)
    return f"{ne_lon},{ne_lat},{sw_lon},{sw_lat}"
