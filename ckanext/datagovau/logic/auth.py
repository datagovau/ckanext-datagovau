from ckan.authz import is_authorized


def dga_get_package_stats(context, data_dict):
    return is_authorized("sysadmin", context, data_dict)


def dga_extract_resource(context, data_dict):
    return is_authorized("resource_update", context, data_dict)
