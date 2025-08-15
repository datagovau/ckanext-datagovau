from __future__ import annotations

import ckan.plugins.toolkit as tk
from ckan import model, types
from ckan.authz import is_authorized
from ckan.logic.auth import restrict_anon

from ckanext.datagovau import config


def dga_extract_resource(context: types.Context, data_dict: types.DataDict):
    return is_authorized("resource_update", context, data_dict)


@tk.chained_auth_function
def search_tweaks_field_relevance_promote(
    next_auth: types.Any,
    context: types.Context,
    data_dict: types.DataDict,
) -> types.AuthResult:
    if data_dict and (pkg := model.Package.get(data_dict.get("id"))):
        return is_authorized("organization_update", context, {"id": pkg.owner_org})

    return {"success": False}


def dga_suggest_dataset(context: types.Context, data_dict: types.DataDict):
    if config.anonymous_suggestion():
        return {"success": True}

    return restrict_anon(context)


@tk.auth_allow_anonymous_access
def site_read(context: types.Context, data_dict: types.DataDict):
    """This function was removed in CKAN v2.11 but ckanext-security needs it."""
    return {"success": True}


@tk.chained_auth_function
def harvest_source_create(
    next_auth: types.Any, context: types.Context, data_dict: types.DataDict
):
    return {"success": False}


@tk.chained_auth_function
def harvest_source_update(
    next_auth: types.Any, context: types.Context, data_dict: types.DataDict
):
    return {"success": False}


@tk.chained_auth_function
def package_create(
    next_auth: types.Any, context: types.Context, data_dict: types.DataDict
):
    if _is_harvester_action():
        return {"success": False}
    return next_auth(context, data_dict)


@tk.chained_auth_function
def package_update(
    next_auth: types.Any, context: types.Context, data_dict: types.DataDict
):
    if _is_harvester_action():
        return {"success": False}
    return next_auth(context, data_dict)


def _is_harvester_action():
    if tk.get_endpoint()[0] == "harvest":
        return True

    if tk.request.is_json and tk.request.json.get("type") == "harvest":
        return True
