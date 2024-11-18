"""Resource operations specific for DGA.

Provides all sort of data extraction(zip, spatial) and submission(geoserver).

"""

from __future__ import annotations

import logging
from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk

log = logging.getLogger(__name__)


class ResourcePlugin(p.SingletonPlugin):
    p.implements(p.IActions)

    def get_actions(self):
        return {
            "resource_create": resource_create,
            "resource_update": resource_update,
        }


@tk.chained_action
def resource_create(next_, context, data_dict):
    result = next_(context, data_dict)

    if _is_extractable(result):
        _schedule_unzip(result)

    return result


@tk.chained_action
def resource_update(next_, context, data_dict):
    result = next_(context, data_dict)

    if _is_extractable(result):
        _schedule_unzip(result)

    return result


def _is_extractable(resource: dict[str, Any]) -> bool:
    """Check if resource can be zip-extracted."""
    return "zip" in resource["format"].lower() and tk.asbool(
        resource.get("zip_extract")
    )


def _schedule_unzip(resource: dict[str, Any]):
    """Enqueue extraction task."""
    id_ = resource["id"]
    tk.enqueue_job(_call_unzip, [id_], title=f"ZIP-extraction of {id_}")


def _call_unzip(id_: str):
    """Wrapper for enqueuing action as a background task."""
    user = tk.get_action("get_site_user")({"ignore_auth": True}, {})
    tk.get_action("dga_extract_resource")({"user": user["name"]}, {"id": id_})
