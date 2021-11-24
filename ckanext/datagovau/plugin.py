from __future__ import annotations

import inspect
from typing import Any
import ckan.plugins as p
import ckan.plugins.toolkit as tk

import ckanext.datagovau.helpers as helpers

import ckan.authz as authz

from . import validators, cli

_original_permission_check = authz.has_user_permission_for_group_or_org
def _dga_permission_check(group_id, user_name, permission):
    stack = inspect.stack()
    # Bypass authorization to enable datasets to be removed from/added to AGIFT
    # classification
    if stack[1].function == "package_membership_list_save":
        return True
    return _original_permission_check(group_id, user_name, permission)
authz.has_user_permission_for_group_or_org = _dga_permission_check


class DataGovAuPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer, inherit=False)
    p.implements(p.ITemplateHelpers)
    p.implements(p.IValidators)
    p.implements(p.IClick)
    p.implements(p.IPackageController, inherit=True)

    # IClick

    def get_commands(self):
        return cli.get_commands()

    # IConfigurer

    def update_config(self, config):
        tk.add_template_directory(config, 'templates')
        tk.add_resource("assets", "datagovau")
        tk.add_public_directory(config, "assets")


    # ITemplateHelpers

    def get_helpers(self) -> dict[str, Any]:
        return helpers.get_helpers()

    # IValidators

    def get_validators(self):
        return validators.get_validators()

    # IPackageController

    def before_index(self, pkg_dict):
        pkg_dict["unpublished"] = tk.asbool(pkg_dict.get("unpublished"))
        return pkg_dict
