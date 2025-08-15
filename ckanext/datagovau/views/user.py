from __future__ import annotations

from typing import Any

from flask import Blueprint, flash
from markupsafe import Markup, escape

import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan import types
from ckan.logic import parse_params
from ckan.views.user import RegisterView

import ckanext.activity.logic.action as activity_action
import ckanext.activity.model.activity as model_activity
import ckanext.activity.views as activity_views
from ckanext.activity.logic.schema import default_activity_list_schema
from ckanext.activity.logic.validators import object_id_validators

user = Blueprint("dga_user", __name__)


@user.route("/user/activity/<id>")
def user_activity(id: str):
    """Render this user's public activity stream page."""
    context = types.Context()

    params = parse_params(tk.request.args)

    try:
        tk.check_access("user_show", context, {"id": id})
        tk.check_access("user_activity_list", context, {"id": id})
    except tk.NotAuthorized:
        tk.abort(403, tk._("Not authorized to see this page"))

    extra_vars = activity_views._extra_template_variables(context, {"id": id})  # pyright: ignore[reportPrivateUsage]

    user = model.User.get(id)
    if user is None:
        tk.abort(404, tk._("User not found"))

    limit = activity_views._get_activity_stream_limit()  # pyright: ignore[
    # reportPrivateUsage]

    data_dict: dict[str, Any] = {
        "id": id,
        "after": params.get("after"),
        "before": params.get("before"),
    }

    data, _errors = tk.navl_validate(data_dict, default_activity_list_schema(), context)

    q = model_activity._user_activity_query(user.id, data["limit"])  # pyright: ignore[reportPrivateUsage]
    q = model_activity._filter_activities_by_permission_labels(
        # pyright: ignore[reportPrivateUsage]
        q,
        activity_action._get_user_permission_labels(context),
        # pyright: ignore[reportPrivateUsage]
    )

    if offset := data.get("offset"):
        q = q.offset(offset)

    if after := data.get("after"):
        q = q.filter(model_activity.Activity.timestamp > after)
    if before := data.get("before"):
        q = q.filter(model_activity.Activity.timestamp < before)

    activity_types = [at] if (at := params.get("activity_type")) else None

    if activity_types:
        q = model_activity._filter_activitites_from_type(
            # pyright: ignore[reportPrivateUsage]
            q,
            include=True,
            types=activity_types,
        )

    activity_stream = model_activity.activity_list_dictize(q, {})

    has_more = len(activity_stream) > limit
    # remove the extra item if exists
    if has_more:
        if after:
            activity_stream.pop(0)
        else:
            activity_stream.pop()

    older_activities_url = activity_views._get_older_activities_url(
        # pyright: ignore[reportPrivateUsage]
        has_more,
        activity_stream,
        id=id,
    )

    newer_activities_url = activity_views._get_newer_activities_url(
        # pyright: ignore[reportPrivateUsage]
        has_more,
        activity_stream,
        id=id,
    )

    extra_vars.update(
        {
            "id": id,
            "activity_stream": activity_stream,
            "newer_activities_url": newer_activities_url,
            "older_activities_url": older_activities_url,
            "activity_types": list(object_id_validators),
        }
    )
    return tk.render("user/activity_stream.html", extra_vars)


@user.route("/user/sysadmin", methods=["POST"])
def sysadmin():
    """Replace flash_success with flash_warning."""
    username = tk.request.form.get("username")
    status = tk.asbool(tk.request.form.get("status"))

    try:
        context: types.Context = {
            "user": tk.current_user.name,
            "auth_user_obj": tk.current_user,
        }
        data_dict: dict[str, Any] = {"id": username, "sysadmin": status}
        user = tk.get_action("user_patch")(context, data_dict)
    except tk.NotAuthorized:
        return tk.base.abort(403, tk._("Not authorized to promote user to sysadmin"))
    except tk.ObjectNotFound:
        tk.h.flash_error(tk._("User not found"))
        return tk.h.redirect_to("admin.index")
    except tk.ValidationError as e:
        tk.h.flash_error(e.message or e.error_summary or e.error_dict)
        return tk.h.redirect_to("admin.index")

    if status:
        tk.h.flash_success(tk._("Promoted {} to sysadmin").format(user["display_name"]))
    else:
        _flash_warning(
            tk._("Revoked sysadmin permission from {}").format(user["display_name"])
        )
    return tk.h.redirect_to("admin.index")


def _flash_warning(message: Any, allow_html: bool = False) -> None:
    """Show a flash message of type success."""
    message = Markup(message) if allow_html else escape(message)
    flash(message, category="alert-warning")


class DgaRegisterView(RegisterView):
    """Force user logout to setup OTP after account creation."""

    def post(self):
        # do not logout sysadmin who created an account for another user
        active_user = tk.current_user.is_authenticated
        result = super().post()
        if not active_user and tk.current_user.is_authenticated:
            tk.logout_user()
            return tk.redirect_to("user.login")

        return result


user.add_url_rule("/user/register", view_func=DgaRegisterView.as_view("register"))
