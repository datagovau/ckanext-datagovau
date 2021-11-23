from __future__ import annotations

from typing import Any
import ckan.plugins as p
import ckan.plugins.toolkit as toolkit

import ckanext.datagovau.helpers as helpers

# Get new, click-based commands
from ckanext.datagovau.cli import get_commands

import ckan.lib.dictization.model_save as model_save
import ckan.logic.auth.create as create
import ckan.authz as authz
import ckan.logic as logic

def datagovau_check_group_auth(context, data_dict):
    if not data_dict:
        return True

    model = context['model']
    user = context['user']
    pkg = context.get("package")

    group_blobs = data_dict.get('groups', [])
    groups = set()
    for group_blob in group_blobs:
        # group_blob might be a dict or a group_ref
        if isinstance(group_blob, dict):
            # use group id by default, but we can accept name as well
            id = group_blob.get('id') or group_blob.get('name')
            if not id:
                continue
        else:
            id = group_blob
        grp = model.Group.get(id)
        if grp is None:
            raise logic.NotFound(_('Group was not found.'))
        groups.add(grp)

    if pkg:
        pkg_groups = pkg.get_groups()

        groups = groups - set(pkg_groups)
    groups = []
    for group in groups:
        if not authz.has_user_permission_for_group_or_org(
                group.id, user, 'manage_group'):
            return False

    return True

create._check_group_auth = datagovau_check_group_auth


def datagovau_package_membership_list_save(group_dicts, package, context):

    allow_partial_update = context.get("allow_partial_update", False)
    if group_dicts is None and allow_partial_update:
        return

    capacity = 'public'
    model = context["model"]
    session = context["session"]
    user = context.get('user')

    members = session.query(model.Member) \
        .filter(model.Member.table_id == package.id) \
        .filter(model.Member.capacity != 'organization')

    group_member = dict(
        (member.group, member)
        for member in
        members)
    groups = set()
    for group_dict in group_dicts or []:
        id = group_dict.get("id")
        name = group_dict.get("name")
        capacity = group_dict.get("capacity", "public")
        if capacity == 'organization':
            continue
        if id:
            group = session.query(model.Group).get(id)
        else:
            group = session.query(model.Group).filter_by(name=name).first()
        if group:
            groups.add(group)

    ## need to flush so we can get out the package id
    model.Session.flush()

    # Remove any groups we are no longer in
    for group in set(group_member.keys()) - groups:
        member_obj = group_member[group]
        if member_obj and member_obj.state == 'deleted':
            continue

        # Bypass authorization to enable datasets to be removed from AGIFT classification
        member_obj.capacity = capacity
        member_obj.state = 'deleted'
        session.add(member_obj)

    # Add any new groups
    for group in groups:
        member_obj = group_member.get(group)
        if member_obj and member_obj.state == 'active':
            continue

        # Bypass authorization to enable datasets to be added to AGIFT classification
        member_obj = group_member.get(group)
        if member_obj:
            member_obj.capacity = capacity
            member_obj.state = 'active'
        else:
            member_obj = model.Member(table_id=package.id,
                                      table_name='package',
                                      group=group,
                                      capacity=capacity,
                                      group_id=group.id,
                                      state='active')
        session.add(member_obj)

model_save.package_membership_list_save = datagovau_package_membership_list_save


class DataGovAuPlugin(p.SingletonPlugin,
                      toolkit.DefaultDatasetForm):
    '''An example IDatasetForm CKAN plugin.

    Uses a tag vocabulary to add a custom metadata field to datasets.

    '''
    p.implements(p.IConfigurer, inherit=False)
    p.implements(p.ITemplateHelpers, inherit=False)
    p.implements(p.IPackageController, inherit=True)
    p.implements(p.IFacets, inherit=True)

    # IClick commands.
    p.implements(p.IClick)

    def get_commands(self):
        return get_commands()

    def dataset_facets(self, facets, package_type):
        if 'jurisdiction' in facets:
            facets['jurisdiction'] = 'Jurisdiction'
        if 'unpublished' in facets:
            facets['unpublished'] = 'Published Status'
        return facets

    def before_search(self, search_params):
        """
        IPackageController::before_search.

        Add default sorting to package_search.
        """
        if 'sort' not in search_params:
            search_params['sort'] = 'extras_harvest_portal asc, score desc, metadata_modified desc'
        return search_params

    def after_search(self, search_results, data_dict):
        if 'unpublished' in search_results['facets']:
            search_results['facets']['unpublished']['Published datasets'] = search_results['count'] - \
                                                                            search_results['facets']['unpublished'].get("true", 0)
            if 'true' in search_results['facets']['unpublished']:
                search_results['facets']['unpublished']['Unpublished datasets'] = \
                    search_results['facets']['unpublished']['true']
                del search_results['facets']['unpublished']['true']
            restructured_facet = {
                'title': 'unpublished',
                'items': []
            }
            for key_, value_ in search_results['facets']['unpublished'].items():
                new_facet_dict = {}
                new_facet_dict['name'] = key_
                new_facet_dict['display_name'] = key_
                new_facet_dict['count'] = value_
                restructured_facet['items'].append(new_facet_dict)
            search_results['search_facets']['unpublished'] = restructured_facet

        return search_results

    def update_config(self, config):
        toolkit.add_template_directory(config, 'templates')
        toolkit.add_resource("assets", "datagovau")
        toolkit.add_public_directory(config, "assets")


    def get_helpers(self) -> dict[str, Any]:
        return helpers.get_helpers()
