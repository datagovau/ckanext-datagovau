from __future__ import annotations

import json
from typing import Any, cast

from flask import Blueprint
from flask.views import MethodView

import ckan.lib.base as base
import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.common import current_user, g, request
from ckan.lib.helpers import Page
from ckan.lib.helpers import helper_functions as h
from ckan.logic import parse_params
from ckan.types import Context
from ckan.views.dataset import GroupView

from ckanext.metaexport.views import export

import ckanext.datagovau.logic.schema as schema

dataset = Blueprint(
    "dga_dataset",
    __name__,
    url_prefix="/dataset",
    url_defaults={"package_type": "dataset"},
)


class DgaGroupView(GroupView):
    """Combines features of the dataset group view and group index page.

    From the dataset group view: Supports adding and removing datasets from the group.
    From the group index page: Includes search, pagination, and sorting of groups.
    """

    def get(self, package_type: str, id: str) -> str:
        context, pkg_dict = self._prepare(id)
        context["is_member"] = True
        users_groups = tk.get_action("group_list_authz")(context, {"id": id})

        pkg_group_ids = {group["id"] for group in pkg_dict.get("groups", [])}

        user_group_ids = {group["id"] for group in users_groups}

        group_dropdown = [
            [group["id"], group["display_name"]]
            for group in users_groups
            if group["id"] not in pkg_group_ids
        ]

        g.group_dropdown = group_dropdown

        extra_vars: dict[str, Any] = {}
        page = tk.h.get_page_number(request.args) or 1
        items_per_page = tk.config.get("ckan.datasets_per_page")

        context = cast(
            Context,
            {
                "model": model,
                "session": model.Session,
                "user": current_user.name,
                "for_view": True,
                "with_private": False,
            },
        )

        q = request.args.get("q", "")
        sort_by = request.args.get("sort")
        extra_vars["q"] = q
        extra_vars["sort_by_selected"] = sort_by

        if current_user.is_authenticated:
            context["user_id"] = current_user.id  # type: ignore
            context["user_is_admin"] = current_user.sysadmin  # type: ignore

        try:
            data_dict_global_results: dict[str, Any] = {
                "all_fields": True,
                "q": q,
                "sort": sort_by,
                "type": "group",
            }
            global_results = tk.get_action("group_list")(
                context, data_dict_global_results
            )
            global_results = [
                group["id"] for group in global_results if group["id"] in pkg_group_ids
            ]
        except tk.ValidationError as e:
            if e.error_dict and e.error_dict.get("message"):
                msg: Any = e.error_dict["message"]
            else:
                msg = str(e)
            h.flash_error(msg)
            extra_vars["page"] = Page([], 0)
            extra_vars["group_type"] = "group"
            return base.render("package/group_list.html", extra_vars)

        data_dict_page_results: dict[str, Any] = {
            "all_fields": True,
            "q": q,
            "sort": sort_by,
            "type": "group",
            "limit": items_per_page,
            "offset": items_per_page * (page - 1),
            "include_extras": True,
        }
        page_results = tk.get_action("group_list")(context, data_dict_page_results)
        page_results = [group for group in page_results if group["id"] in pkg_group_ids]

        for group in page_results:
            group["user_member"] = group["id"] in user_group_ids

        extra_vars["page"] = Page(
            collection=global_results,
            page=page,
            url=tk.h.pager_url,
            item_count=len(global_results),
            items_per_page=items_per_page,
            id=id,
            package_type=package_type,
        )

        extra_vars["page"].items = page_results
        extra_vars["group_type"] = "group"
        extra_vars["dataset_type"] = "dataset"
        extra_vars["pkg_dict"] = pkg_dict
        extra_vars["group_dropdown"] = group_dropdown

        return base.render("package/group_list.html", extra_vars)


class SuggestDatasetView(MethodView):
    def post(self, package_type: str) -> Any:
        if tk.request.form.get("refresh"):
            return tk.render("package/snippets/suggest_dataset_form.html")

        data = parse_params(tk.request.form)
        errors = {}

        # if form wasn't submitted (input trigger), only validate the data
        if "submit" not in tk.request.form:
            data, errors = tk.navl_validate(data, schema.suggest_dataset(), {})
        else:
            try:
                tk.get_action("dga_suggest_dataset")(
                    {"user": current_user.name, "auth_user_obj": current_user}, data
                )
            except tk.ValidationError as e:
                errors = e.error_dict
            else:
                return tk.render("package/snippets/suggest_dataset_done.html")

        return tk.render(
            "package/snippets/suggest_dataset_form.html",
            extra_vars={"data": data, "errors": errors},
        )


class AskQuestionView(MethodView):
    def post(self, package_type: str, package_id: str) -> Any:
        data = parse_params(tk.request.form)
        errors = {}

        data["package_id"] = package_id

        if tk.request.form.get("refresh"):
            return tk.render(
                "package/snippets/ask_question_form.html",
                {
                    "data": {
                        "package_id": package_id,
                    }
                },
            )

        if "submit" not in tk.request.form:
            data, errors = tk.navl_validate(
                data,
                schema.ask_question(),
                {
                    "model": model,
                    "session": model.Session,
                },
            )
        else:
            try:
                tk.get_action("dga_ask_question")(
                    {"user": current_user.name, "auth_user_obj": current_user}, data
                )
            except tk.ValidationError as e:
                errors = e.error_dict
            else:
                return tk.render(
                    "package/snippets/ask_question_done.html", {"data": data}
                )

        return tk.render(
            "package/snippets/ask_question_form.html",
            extra_vars={"data": data, "errors": errors},
        )


dataset.add_url_rule("/groups/<id>", view_func=DgaGroupView.as_view("groups"))
dataset.add_url_rule("/dga-suggest", view_func=SuggestDatasetView.as_view("suggest"))
dataset.add_url_rule(
    "/dga-question/<package_id>", view_func=AskQuestionView.as_view("ask_question")
)


@dataset.route("/dga-load-facets", methods=["POST"])
def get_full_facet_list(package_type: str) -> str:
    form = tk.request.form
    if items := form.get("items"):
        items = json.loads(items)
    name = form.get("name")
    controller = form.get("controller")
    action = form.get("action")
    if extras := form.get("extras"):
        extras = json.loads(extras)
    return tk.render(
        "package/snippets/facet_items.html",
        extra_vars={
            "items": items,
            "name": name,
            "controller": controller,
            "action": action,
            "extras": extras,
            "hidden": True,
        },
    )


@dataset.route("/<id>/gmd")
def gmd(id: str, package_type: str):
    return export(id, "gmd")
