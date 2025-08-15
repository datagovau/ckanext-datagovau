from __future__ import annotations

import logging

from flask import Blueprint

log = logging.getLogger(__name__)
utils = Blueprint("dga_utils", __name__)


@utils.route("/webassets/<path:path>.<any(css,js):ext>.map")
def fake_static_map(path: str, ext: str):
    """Stub for requests to external map files.

    Because static files are served via webassets, there is no way to give
    access to a map file that is kept next to its static files. As result,
    either use inline maps, or get empty response from this endpoint.

    """
    log.debug("Map files accessed at /webassets/%s.%s.map", path, ext)

    return ""
