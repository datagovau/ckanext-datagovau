from __future__ import annotations

import json
import logging
from typing import Any

from slugify import slugify

import ckan.plugins.toolkit as tk

from ckanext.harvest_basket.harvesters import CustomCKANHarvester

log = logging.getLogger(__name__)


class DgaCKANHarvester(CustomCKANHarvester):
    """Child harvester that rewrites owner_org logic.

    It re‑assigns each harvested package to a local organisation derived from the
    remote dataset's org *plus* the harvest source title.
    """

    def _show_package(self, guid: str) -> dict[str, Any] | None:
        try:
            return tk.get_action("package_show")(
                tk.fresh_context(self.base_context), {"id": guid}
            )
        except tk.ObjectNotFound:
            log.error("Package %s disappeared after import", guid)
            return None

    def _show_org(self, org_id_or_name: str) -> dict[str, Any] | None:
        try:
            return tk.get_action("organization_show")(
                tk.fresh_context(self.base_context), {"id": org_id_or_name}
            )
        except tk.ObjectNotFound:
            return None

    def _create_org(self, org_dict: dict[str, Any]) -> str:
        created = tk.get_action("organization_create")(
            tk.fresh_context(self.base_context), org_dict
        )
        return created["id"]

    def _ensure_local_org(
        self,
        remote_org: dict[str, Any],
        parent_org: dict[str, Any],
        suffix: str,
    ) -> str:
        """Return the id of a local org.

        Local org mirrors *remote_org* but is unique per harvest source.
        Create it if missing.
        """
        name = tk.h.truncate(
            slugify(f"{remote_org.get('title', 'org')}-{suffix}"), 100, indicator=""
        )
        existing = self._show_org(name)
        if existing:
            return existing["id"]

        new_org = {
            "name": name,
            "title": remote_org.get("title") or parent_org["title"],
            "description": remote_org.get("description") or parent_org["description"],
            "jurisdiction": parent_org.get("jurisdiction"),
            "spatial_coverage": parent_org.get("spatial_coverage"),
            "website": parent_org.get("website"),
            "email": parent_org.get("email"),
            "telephone": parent_org.get("telephone"),
            "groups": [{"name": parent_org["name"], "capacity": "public"}],
        }
        return self._create_org(new_org)

    def import_stage(self, harvest_object: dict[str, Any]) -> dict[str, Any]:
        result = super().import_stage(harvest_object)

        if result is False:
            return result

        self.base_context = {
            "user": self._get_user_name(),
            "ignore_auth": True,
        }

        pkg_dict = self._show_package(harvest_object.guid)
        if not pkg_dict:
            return result

        try:
            remote_org = json.loads(harvest_object.content).get("organization") or {}
        except ValueError:
            log.warning("Harvest object %s has invalid JSON content", harvest_object.id)
            return result

        if not remote_org:
            log.info(
                "No organisation info on remote dataset %s; keeping original org",
                pkg_dict["id"],
            )
            return result

        parent_org = self._show_org(pkg_dict["owner_org"])
        if not parent_org:
            log.error("Parent organisation %s vanished", pkg_dict["owner_org"])
            return result

        local_org_id = self._ensure_local_org(
            remote_org,
            parent_org,
            suffix=harvest_object.source.title,
        )

        if local_org_id != pkg_dict["owner_org"]:
            log.info("Starting re-assigning")
            try:
                tk.get_action("package_patch")(
                    tk.fresh_context(self.base_context),
                    {"id": pkg_dict["id"], "owner_org": local_org_id},
                )
            except tk.ValidationError as e:
                log.error(e)
            log.info(
                "Re‑assigned %s to organisation %s", pkg_dict["name"], local_org_id
            )

        return result
