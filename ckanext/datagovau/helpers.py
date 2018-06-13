import logging
import os
import time

import ckan.lib as lib
import ckan.logic as logic
import ckan.model as model
import ckan.plugins.toolkit as toolkit
import ckanext.datastore as datastore_db
import ckanext.datastore.backend as datastore_backend
import feedparser
from ckan.lib import uploader, formatters
from pylons import config

log = logging.getLogger('ckanext_datagovau')

def get_user_datasets(user_dict):
    # Need to test packages carefully to make sure they haven't been purged from the DB (like what happens
    # in a harvest purge), as the activity list does not have the associated entries cleaned out.
    # [SXTPDFINXZCB-145]
    def pkg_test(input):
        try:
            result = input['data'].get('package')

            # Test just to catch an exception if need be
            data = logic.get_action('package_show')(context, {'id': input['data']['package']['id']})
        except:
            result = False
        return result

    context = {'model': model, 'user': user_dict['name']}
    created_datasets_list = user_dict['datasets']

    active_datasets_list = [logic.get_action('package_show')(context, {'id': x['data']['package']['id']}) for x in
                            lib.helpers.get_action('user_activity_list', {'id': user_dict['id']}) if pkg_test(x)]
    raw_list = sorted(active_datasets_list + created_datasets_list, key=lambda pkg: pkg['state'])
    filtered_dict = {}
    for dataset in raw_list:
        if dataset['id'] not in filtered_dict.keys():
            filtered_dict[dataset['id']] = dataset
    return filtered_dict.values()


def get_user_datasets_public(user_dict):
    return [pkg for pkg in get_user_datasets(user_dict) if pkg['state'] == 'active']


def get_ddg_site_statistics():
    def fetch_ddg_stats():
        stats = {'dataset_count': logic.get_action('package_search')({}, {"rows": 1})['count']}

        for fDict in \
                logic.get_action('package_search')({}, {"facet.field": ["unpublished"], "rows": 1})['search_facets'][
                    'unpublished'][
                    'items']:
            if fDict['name'] == "Unpublished datasets":
                stats['unpub_data_count'] = fDict['count']
                break

        stats['open_count'] = logic.get_action('package_search')({}, {"fq": "isopen:true", "rows": 1})['count']

        stats['api_count'] = logic.get_action('resource_search')({}, {"query": ["format:wms"]})['count'] + len(
            datastore_backend.get_all_resources_ids_in_datastore())

        if 'unpub_data_count' not in stats:
            stats['unpub_data_count'] = 0

        return stats

    if toolkit.asbool(config.get('ckanext.stats.cache_enabled', 'True')):
        from pylons import cache

        key = 'ddg_site_stats'
        res_stats = cache.get_cache('ddg_ext', type='memory').get_value(key=key,
                                                                        createfunc=fetch_ddg_stats,
                                                                        expiretime=toolkit.asint(
                                                                            config.get(
                                                                                'ckanext.stats.cache_fast_timeout',
                                                                                '600')))
    else:
        res_stats = fetch_ddg_stats()

    return res_stats


def get_resource_file_size(rsc):
    if rsc.get('url_type') == 'upload':
        upload = uploader.ResourceUpload(rsc)
        value = None
        try:
            value = os.path.getsize(upload.get_path(rsc['id']))
            value = formatters.localised_filesize(int(value))
        except Exception:
            # Sometimes values that can't be converted to ints can sneak
            # into the db. In this case, just leave them as they are.
            pass
        return value
    return None


def blogfeed():
    d = feedparser.parse('https://blog.data.gov.au/blogs/rss.xml')
    for entry in d.entries:
        entry.date = time.strftime("%a, %d %b %Y", entry.published_parsed)
    return d