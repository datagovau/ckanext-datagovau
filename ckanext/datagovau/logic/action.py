from __future__ import annotations

import logging
from typing import Any

import ckan.plugins.toolkit as tk
from ckan.logic import validate

from ckanext.datagovau.utils import temp_dir

from . import schema

log = logging.getLogger(__name__)


@validate(schema.get_package_stats)
@tk.side_effect_free
def dga_get_package_stats(context, data_dict):
    tk.check_access("dga_get_package_stats", context, data_dict)

    user: dict[str, Any] = tk.get_action("get_site_user")({"ignore_auth": True}, {})
    context["user"] = user["name"]

    try:
        stats = tk.get_action("flakes_flake_lookup")(
            context,
            {"name": "dga_ga_stats"},
        )["data"]
    except tk.ObjectNotFound as err:
        raise tk.ObjectNotFound(tk._("No dataset statistics")) from err

    if "id" not in data_dict:
        return stats

    pkg_id_or_name: str = data_dict["id"]
    pkg = context["model"].Package.get(pkg_id_or_name)
    pkg_stats: dict[str, dict[str, int]] = stats.get(pkg.id)

    if not pkg_stats:
        raise tk.ObjectNotFound(
            tk._(f"No statistics for the specific dataset: {pkg_id_or_name}")
        )

    return pkg_stats


@validate(schema.extract_resource)
def dga_extract_resource(context, data_dict):
    """Extract ZIP-resource into additional resoruces.

    Args:
        id(str): ID of the ZIP resource with `zip_extract` flag
        tmp_dir(str, optional): temporal folder for extraction artifacts.
    """
    from ckanext.datagovau.utils.zip import extract_resource, update_resource

    resource = tk.get_action("resource_show")(context, {"id": data_dict["id"]})
    dataset = tk.get_action("package_show")(context, {"id": resource["package_id"]})

    if "zip" not in resource["format"].lower():
        raise tk.ValidationError({"id": ["Not a ZIP resource"]})

    if not tk.asbool(resource.get("zip_extract")):
        raise tk.ValidationError({"id": ["Extraction is not enabled"]})

    with temp_dir(resource["id"], data_dict["tmp_dir"]) as path:
        for result in extract_resource(resource, path):
            update_resource(*result, resource, dataset, context.copy())
