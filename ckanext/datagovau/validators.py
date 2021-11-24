import logging

from ckanext.toolbelt.decorators import Collector
from ckanext.agls.utils import details_for_gaz_id

log = logging.getLogger(__name__)
validator, get_validators = Collector("dga").split()


@validator
def spatial_from_coverage(key, data, errors, context):
    coverage = data[("spatial_coverage",)]
    if not coverage:
        return
    id_ = coverage.split(":")[0]
    try:
        details = details_for_gaz_id(id_)
    except KeyError as e:
        log.warning("Cannot get details for GazId %s: %s", id_, e)
        return None

    if details:
        data[key] = details["geojson"]
