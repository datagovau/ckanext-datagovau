from __future__ import annotations

import inspect
import os
from typing import Any

import dominate.tags as tags
from markupsafe import Markup

import ckan.plugins.toolkit as tk
from ckan import authz
from ckan.lib.helpers import Page

from ckanext.toolbelt.magic import (
    conjure_fast_group_activities,
    reveal_readonly_scheming_fields,  # type: ignore
)
from ckanext.xloader.plugin import xloaderPlugin

__version__ = "3.0.0"

###############################################################################
#      Faster computation of new activities for dashboard icon in header      #
###############################################################################
conjure_fast_group_activities()
###############################################################################
#                                     End                                     #
###############################################################################

###############################################################################
#           Add readonly fields to dataset: slow index but fast read          #
###############################################################################
reveal_readonly_scheming_fields(
    {
        ("duplicate_score",): "",
        ("original_harvest_source",): {},
    }
)
###############################################################################
#                                     End                                     #
###############################################################################


###############################################################################
#                 Catch XLoader error when resource is deleted                #
###############################################################################
def _dga_xnotify(self: xloaderPlugin, entity: Any, operation: str):
    try:
        return _original_xnotify(self, entity, operation)
    except tk.ObjectNotFound:
        # resource has `deleted` state
        pass


_original_xnotify: Any = xloaderPlugin.notify
xloaderPlugin.notify = _dga_xnotify
###############################################################################
#                                     End                                     #
###############################################################################


###############################################################################
#                       Anyone can add datasets to group                      #
###############################################################################
_original_permission_check = authz.has_user_permission_for_group_or_org


def _dga_permission_check(
    group_id: str | None,
    user_name: str | None,
    permission: str,
) -> bool:
    stack = inspect.stack()
    # Bypass authorization to enable datasets to be removed from/added to AGIFT
    # classification
    if stack[1].function == "package_membership_list_save":
        return True
    return _original_permission_check(group_id, user_name, permission)


authz.has_user_permission_for_group_or_org = _dga_permission_check
###############################################################################
#                                     End                                     #
###############################################################################


###############################################################################
#                    Customize markup of pagination widget                    #
###############################################################################
def dga_update_pager(self: Page, *args: Any, **kwargs: Any) -> Markup:
    """Override CKAN default pagination method with custom implementation.

    Returns:
        Customized pagination Markup
    """
    # Create the wrapper div
    div: Any = tags.div(cls="pagination-wrapper")
    with div as wrapper:
        tags.ul(
            "$link_previous ~3~ $link_next", cls="pagination justify-content-center"
        )

    def _arrow_link(
        page_attr: str, active_svg: str, disabled_svg: str, label: str
    ) -> str:
        """Create accessible previous and next links."""
        page_num = getattr(self, page_attr)
        page_param = kwargs.get("page_param", "page")

        if page_num:
            link_params = {}
            link_params.update(self.kwargs)
            link_params.update(kwargs)
            link_params[page_param] = page_num

            if self._url_generator is not None:
                url_generator = self._url_generator
            else:
                from ckan.lib.helpers import pager_url as url_generator
            url = url_generator(**link_params)

            a_tag = tags.a(
                _render_svg(active_svg),
                href=url,
                **{"class": "page-link", "aria-label": label},
            )
            return str(tags.li(a_tag, cls="page-item"))

        # Disabled: use alternate SVG and disable interaction
        a_tag = tags.a(
            _render_svg(disabled_svg),
            href="#",
            **{"class": "page-link", "aria-hidden": "true", "tabindex": "-1"},
        )
        return str(tags.li(a_tag, cls="page-item disabled"))

    link_previous = _arrow_link(
        "previous_page",
        "arrow-left.svg",
        "arrow-left-grey.svg",
        "Previous page",
    )
    link_next = _arrow_link(
        "next_page",
        "arrow-right.svg",
        "arrow-right-grey.svg",
        "Next page",
    )

    custom_params: dict[str, Any] = {
        "format": str(wrapper)
        .replace("$link_previous", link_previous)
        .replace("$link_next", link_next),
        "curpage_attr": {"class": "page-item active"},
        "link_attr": {"class": "page-link"},
    }
    custom_params.update(kwargs)

    return super(Page, self).pager(*args, **custom_params)


def _render_svg(file_name: str) -> Markup:
    """Reads and returns the contents of an SVG file from the public/images directory.

    :return: The SVG file content as a Markup string
    or an empty string if file not found.
    """
    static_path = os.path.join(os.path.dirname(__file__), "public", "images", file_name)
    try:
        with open(static_path, encoding="utf-8") as svg_file:
            return Markup(svg_file.read())
    except FileNotFoundError:
        # Return an empty Markup string to avoid serialization errors
        return Markup("")


# Monkey patch the Page class to use our custom pager method
Page.pager = dga_update_pager
###############################################################################
#                                     End                                     #
###############################################################################
