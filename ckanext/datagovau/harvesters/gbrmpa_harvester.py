from __future__ import annotations

import json
import logging
import urllib
from typing import Any

from ckan.plugins import toolkit as tk

from ckanext.harvest.harvesters.ckanharvester import ContentFetchError, SearchError
from ckanext.harvest.model import HarvestObject
from ckanext.harvest_basket.harvesters.base_harvester import BasketBasicHarvester

log = logging.getLogger(__name__)


class GbrmpaHarvester(BasketBasicHarvester):
    SRC_ID = "GBRMPA ArcGIS"
    BASE_URL = "/sharing/rest/content/groups/5a574fa198254bcf856d2fe0e77d8cca/search"
    PORTIONS = 60
    PARAMS = {
        "enriched": "true",
        "q": urllib.parse.quote_plus(
            """-typekeywords:("MapAreaPackage")-type:("Map Area" OR "Indoors Map
            Configuration" OR "Code Attachment")"""
        ),
        "displaySublayers": "true",
        "displayHighlights": "true",
        "displayServiceProperties": "true",
        "f": "json",
    }

    def info(self):
        return {
            "name": "gbrmpa_arcgis",
            "title": "GBRMPA",
            "description": "Harvests datasets from remote GBRMPA Geoportal",
        }

    def gather_stage(self, harvest_job: Any):
        source_url = self._get_src_url(harvest_job)

        self._set_config(harvest_job.source.config)
        log.info("%s: gather stage started: %s", self.SRC_ID, source_url)

        try:
            pkg_dicts = self._search_datasets(source_url)
        except SearchError as e:
            log.error("%s: searching for datasets failed: %s", self.SRC_ID, e)
            self._save_gather_error(
                f"{self.SRC_ID}: unable to search the remote ArcGIS portal "
                f"for datasets: {harvest_job}"
            )
            return []

        if not pkg_dicts:
            log.error("%s: searching returns empty result.", self.SRC_ID)
            self._save_gather_error(
                f"{self.SRC_ID}: no datasets found at remote portal: {source_url}",
                harvest_job,
            )
            return []

        try:
            package_ids = set()
            object_ids = []

            for pkg_dict in pkg_dicts:
                pkg_id: str = pkg_dict["id"]
                if pkg_id in package_ids:
                    log.debug(
                        "%s: discarding duplicate dataset %s. "
                        "Probably, due to datasets being changed "
                        "in process of harvesting",
                        self.SRC_ID,
                        pkg_id,
                    )
                    continue

                package_ids.add(pkg_id)

                log.info(
                    "%s: creating harvest_object for package: %s", self.SRC_ID, pkg_id
                )
                obj = HarvestObject(
                    guid=pkg_id, job=harvest_job, content=json.dumps(pkg_dict)
                )
                obj.save()
                object_ids.append(obj.id)

            return object_ids
        except Exception as e:
            log.debug(
                "%s: the error occured during the gather stage: %s", self.SRC_ID, e
            )
            self._save_gather_error(f"{e}", harvest_job)
            return []

    def _search_datasets(self, source_url: str) -> list[dict[str, Any]]:
        services_dicts = []
        max_datasets = tk.asint(self.config.get("max_datasets", 0))

        start = 1
        total = self.PORTIONS
        self.PARAMS["num"] = self.PORTIONS

        while start < total and start != -1:
            self.PARAMS["start"] = start
            log.info(
                "%s: gathering remote dataset from %s by %s",
                self.SRC_ID,
                start,
                self.PORTIONS,
            )

            result = self._fetch_arcgis_data(source_url + self.BASE_URL, self.PARAMS)
            log.debug("result: '%s'", result)

            if datasets := result.get("results", []):
                services_dicts.extend(datasets)

            if "nextStart" in result:
                start = result["nextStart"]
            else:
                break

            total = result.get("total", 0)

            if max_datasets and len(services_dicts) == max_datasets:
                break

        return services_dicts

    def _fetch_arcgis_data(self, url: str, params: dict[str, str]):
        """Search datasets on GBRMPA Geoportal portal."""
        try:
            encoded_params = urllib.parse.urlencode(params, doseq=True)
            full_url = f"{url}?{encoded_params}"
            resp = self._make_request(full_url)
        except ContentFetchError:
            log.debug("%s: Can't fetch the data. Access denied.", self.SRC_ID)
            return {}

        try:
            content = json.loads(resp.text)

        except ValueError as e:
            log.debug(
                "%s: Can't fetch the data. JSON object is corrupted: %s", self.SRC_ID, e
            )
            return {}

        return content

    def fetch_stage(self, harvest_object: HarvestObject):
        self.source_url = harvest_object.source.url.strip("/")
        package_dict = json.loads(harvest_object.content)
        self._pre_map_stage(package_dict, self.source_url)
        harvest_object.content = json.dumps(package_dict)
        return True

    def _pre_map_stage(self, pkg_data: dict[str, Any], source_url: str):
        pkg_data["licen"] = self._resources_fetch(pkg_data)
        pkg_data["resources"] = self._resources_fetch(pkg_data)
        pkg_data["extras"] = []

    def _resources_fetch(self, pkg_data: dict[str, Any]):
        if "url" in pkg_data:
            return [
                {
                    "url": pkg_data["url"],
                    "format": "ArcGIS GeoServices REST API",
                    "mimetype": "application/json",
                    "name": "ArcGIS GeoService",
                }
            ]
        return []
