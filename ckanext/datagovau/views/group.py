from __future__ import annotations

import csv
from io import StringIO

from flask import Blueprint, make_response

import ckan.lib.base as base
import ckan.model as model
import ckan.plugins.toolkit as tk
from ckan.common import current_user
from ckan.types import Context

group = Blueprint(
    "dga_group",
    __name__,
    url_prefix="/group",
    url_defaults={"group_type": "group", "is_organization": False},
)
organization = Blueprint(
    "dga_organization",
    __name__,
    url_prefix="/organization",
    url_defaults={"group_type": "organization", "is_organization": True},
)


@group.route("/member_dump/<id>")
@organization.route("/member_dump/<id>")
def member_dump(id: str, group_type: str, is_organization: bool):
    """Fixes a CKAN bug when downloading CSVs of group members.

    The issue arises from writing a UTF-8 byte-order mark (BOM) to `output_stream`,
    which expects a string rather than bytes. Since the BOM is unnecessary for
    properly encoded UTF-8 output, removing it prevents the error while preserving
    correct encoding.
    """
    group_obj = model.Group.get(id)
    if not group_obj:
        base.abort(
            404,
            tk._("Organisation not found")
            if is_organization
            else tk._("Group not found"),
        )

    context: Context = {"user": current_user.name}

    try:
        action_name = (
            "organization_member_create" if is_organization else "group_member_create"
        )
        tk.check_access(action_name, context, {"id": id})
    except tk.NotAuthorized:
        base.abort(
            404, tk._(f"Not authorized to access {group_obj.title} members download")
        )

    try:
        members = tk.get_action("member_list")(
            context,
            {
                "id": id,
                "object_type": "user",
                "records_format": "csv",
                "include_total": False,
            },
        )
    except tk.ObjectNotFound:
        base.abort(404, tk._("Members not found"))

    results = [[tk._("Username"), tk._("Email"), tk._("Name"), tk._("Role")]]
    for uid, _user, role in members:
        user_obj = model.User.get(uid)
        if not user_obj:
            continue
        results.append(
            [
                user_obj.name,
                user_obj.email,  # type: ignore
                user_obj.fullname if user_obj.fullname else tk._("N/A"),
                role,
            ]
        )

    output_stream = StringIO()
    # output_stream.write(BOM_UTF8)  # type: ignore
    csv.writer(output_stream).writerows(results)

    file_name = "{org_id}-{members}".format(
        org_id=group_obj.name, members=tk._("members")
    )

    output_stream.seek(0)
    response = make_response(output_stream.read())
    output_stream.close()
    content_disposition = f'attachment; filename="{file_name}.csv"'
    content_type = b"text/csv; charset=utf-8"
    response.headers["Content-Type"] = content_type  # type: ignore
    response.headers["Content-Disposition"] = content_disposition

    return response
