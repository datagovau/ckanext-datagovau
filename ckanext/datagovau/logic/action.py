from __future__ import annotations

import itertools
import logging
from typing import Any, cast

import sqlalchemy as sa

import ckan.plugins.toolkit as tk
from ckan import model, types
from ckan.lib.jobs import connect_to_redis, enqueue
from ckan.lib.search.query import solr_literal
from ckan.logic import validate

from ckanext.mailcraft.utils import get_mailer

import ckanext.datagovau.utils as utils
from ckanext.datagovau import config
from ckanext.datagovau.jobs import reindex_organization_datasets
from ckanext.datagovau.utils.lga import lga_geometry

from . import schema

log = logging.getLogger(__name__)

AUTOCOMPLETE_LIMIT: int = 6
ARCHIVAL_KEY = "ckanext:dga:fresh_archivals"


@validate(schema.extract_resource)
def dga_extract_resource(context: types.Context, data_dict: dict[str, Any]):
    """Extract ZIP-resource into additional resoruces.

    Args:
        id(str): ID of the ZIP resource with `zip_extract` flag
        tmp_dir(str, optional): temporal folder for extraction artifacts.
    """
    from ckanext.datagovau.utils.zip import extract_resource, update_resource

    resource = tk.get_action("resource_show")(context, {"id": data_dict["id"]})
    dataset = tk.get_action("package_show")(context, {"id": resource["package_id"]})

    if "zip" not in resource["format"].lower():
        raise tk.ValidationError({"id": ["Not a ZIP resource"]})

    if not tk.asbool(resource.get("zip_extract")):
        raise tk.ValidationError({"id": ["Extraction is not enabled"]})

    with utils.temp_dir(resource["id"], data_dict["tmp_dir"]) as path:
        for result in extract_resource(resource, path):
            update_resource(*result, resource, dataset, dict(context))


@tk.side_effect_free
def dga_advanced_search_config(
    context: types.Context, data_dict: dict[str, Any]
) -> dict[str, Any]:
    """Configuration for advanced search fields."""
    return tk.h.advanced_search_form_config()


@tk.side_effect_free
def dga_search_autocomplete(
    context: types.Context, data_dict: dict[str, Any]
) -> dict[str, Any]:
    q = tk.get_or_bust(data_dict, "q")
    words = q.lower().split()

    if not words:
        return {
            "datasets": [],
            "categories": [],
        }
    # use only first two words. Otherwise we'll mess with
    # distributions of relevant suggestions per word
    datasets = _autocomplete_datasets(words)
    categories = _autocomplete_categories(words)
    return {
        "datasets": datasets,
        "categories": categories,
    }


def _autocomplete_datasets(terms: list[str]) -> list[dict[str, Any]]:
    """Return limited number of autocomplete suggestions."""
    combined, *others = _datasets_by_terms(terms, include_combined=True)

    # Combine and dedup all the results
    other: list[dict[str, str]] = [
        item
        for item, _ in itertools.groupby(
            sorted(
                filter(None, itertools.chain(*itertools.zip_longest(*others))),
                key=lambda i: i["title"],
            ),
        )
        if item not in combined
    ]

    return [
        {
            "href": tk.h.url_for("dataset.read", id=item["name"]),
            "label": item["title"],
            "type": "Dataset",
        }
        for item in combined + other[: AUTOCOMPLETE_LIMIT - len(combined)]
    ]


def _datasets_by_terms(
    terms: list[str],
    include_combined: bool = False,
    limit: int = AUTOCOMPLETE_LIMIT,
) -> list[list[dict[str, str]]]:
    """Get list of search result iterables.

    When include_combined is set to True, prepend list with results from
    combined search for all the terms, i.e results that includes every term from
    the list of provided values. Can be used for building more relevant
    suggestions.

    """
    terms = [solr_literal(term) for term in terms]
    if include_combined:
        terms = [" ".join(terms)] + terms

    return [
        tk.get_action("package_search")(
            {},
            {
                "include_private": True,
                "rows": limit,
                "fl": "name,title",
                "q": f"title:({term}) OR title_ngram:({term})",
            },
        )["results"]
        for term in terms
    ]


_facet_type_to_label = {
    "organization": tk._("Organisations"),
    "groups": tk._("Groups"),
    "tags": tk._("Tags"),
    "res_format": tk._("Formats"),
    "license_id": tk._("Licenses"),
}


def _autocomplete_categories(terms: list[str]) -> list[dict[str, Any]]:
    facets = tk.get_action("package_search")(
        {},
        {
            "rows": 0,
            "facet.field": [
                "organization",
                "tags",
                "topic",
                "member_countries",
                "res_format",
                "type",
                "license_id",
            ],
        },
    )["search_facets"]

    categories: list[list[dict[str, Any]]] = []
    for facet in facets.values():
        group: list[tuple[int, dict[str, Any]]] = []
        for item in facet["items"]:
            # items with the highest number of matches will have higher priority in
            # suggestion list
            matches = 0
            for term in terms:
                if term in item["display_name"].lower():
                    matches += 1
            if not matches:
                continue

            group.append(
                (
                    matches,
                    {
                        "href": tk.h.url_for(
                            "dataset.search",
                            **{facet["title"]: item["name"]},
                        ),
                        "label": item["display_name"],
                        "type": _facet_type_to_label[facet["title"]],
                        "count": item["count"],
                    },
                ),
            )
        categories.append(
            [
                item
                for _, item in sorted(
                    group,
                    key=lambda i: (i[0], i[1]["count"]),
                    reverse=True,
                )
            ],
        )
    return sorted(
        itertools.islice(
            filter(None, itertools.chain(*itertools.zip_longest(*categories))),
            AUTOCOMPLETE_LIMIT,
        ),
        key=lambda item: item["type"],
    )


@validate(schema.suggest_dataset)
def dga_suggest_dataset(context: types.Context, data_dict: types.DataDict) -> bool:
    """Send a dataset suggestion email to configured recipients or site admins."""
    tk.check_access("dga_suggest_dataset", context, data_dict)

    recipients = config.suggest_dataset_emails() or utils.get_sysadmins_emails()

    get_mailer().mail_recipients(
        subject="Dataset suggestion",
        recipients=recipients,
        body=tk.render("emails/suggest_dataset.txt", extra_vars=data_dict),
        body_html=tk.render("emails/suggest_dataset.html", extra_vars=data_dict),
    )

    return True


@validate(schema.ask_question)
def dga_ask_question(context: types.Context, data_dict: types.DataDict) -> bool:
    """Ask a question about a dataset."""
    tk.check_access("dga_suggest_dataset", context, data_dict)

    package = tk.get_action("package_show")(context, {"id": data_dict["package_id"]})
    contact_point = package.get("contact_point")

    data_dict.update(
        {
            "package": {
                "url": tk.h.url_for("dataset.read", id=package["name"], _external=True),
                "title": package["title"],
                "publisher": model.User.get(package["creator_user_id"]).display_name,  # type: ignore
            }
        }
    )
    get_mailer().mail_recipients(
        subject="Question about a dataset",
        recipients=[contact_point] if contact_point else utils.get_sysadmins_emails(),
        body=tk.render("emails/ask_question.txt", extra_vars=data_dict),
        body_html=tk.render("emails/ask_question.html", extra_vars=data_dict),
    )

    return True


@tk.side_effect_free
def dga_lga_geometry_show(context: types.Context, data_dict: dict[str, Any]):
    """Translate LGA name into coordinates.

    Args:
        lga_name (str): name of LGA
    """
    lga_name = tk.get_or_bust(data_dict, "lga_name")
    lga_geom = lga_geometry(lga_name)
    return {"geometry": lga_geom}


@tk.chained_action
def package_update(next_action: Any, context: types.Context, data_dict: dict[str, Any]):
    """Modifications of the original action.

    * track changes of the archived state
    """
    old_package = tk.get_action("package_show")(tk.fresh_context(context), data_dict)

    result = next_action(context, data_dict)
    if context.get("return_id_only"):
        return result

    initial = old_package.get("archived")

    final = result.get("archived")

    if initial != final:
        _handle_archival(result["id"], final)

    return result


def _handle_archival(id: str, state: bool):
    conn = connect_to_redis()
    if state:
        conn.sadd(ARCHIVAL_KEY, id)
    else:
        conn.srem(ARCHIVAL_KEY, id)


@tk.side_effect_free
def dga_notify_about_archival(
    context: types.Context, data_dict: dict[str, Any]
) -> list[str]:
    """Send notification to curators of archived datasets."""
    tk.check_access("sysadmin", context, data_dict)

    conn = connect_to_redis()
    ids = [v.decode() for v in cast("set[bytes]", conn.smembers(ARCHIVAL_KEY))]

    if not ids:
        return []

    stmt = (
        sa.select(
            sa.func.array_agg(model.Package.title),
            sa.func.array_agg(model.Package.name),
            model.Group.title,
            model.GroupExtra.value,
        )
        .select_from(model.Group)
        .join(model.Package, model.Package.owner_org == model.Group.id)
        .join(
            model.GroupExtra,
            sa.and_(
                model.Group.id == model.GroupExtra.group_id,
                model.GroupExtra.key == "email",
            ),
        )
        .where(model.Package.id.in_(ids), model.Package.state == "active")
        .group_by(model.Group.title, model.GroupExtra.value)
    )
    mailer = get_mailer()
    for titles, names, recipient, email in model.Session.execute(stmt):
        datasets = [
            (title, tk.h.url_for("dataset.read", id=name, _external=True))
            for title, name in zip(titles, names)
        ]

        subject = "Dataset archival"
        email_dict: dict[str, Any] = {
            "subject": subject,
            "datasets": datasets,
            "recipient": recipient,
        }
        mailer.mail_recipients(
            subject=subject,
            recipients=[email],
            body=tk.render("emails/archived_datasets.txt", extra_vars=email_dict),
            body_html=tk.render("emails/archived_datasets.html", extra_vars=email_dict),
        )

    conn.delete(ARCHIVAL_KEY)
    return list(ids)


@tk.chained_action
def organization_update(
    next_action: types.Action, context: types.Context, data_dict: dict[str, Any]
) -> dict[str, Any]:
    """Triggers dataset reindexing if organization spatial coverage changes.

    Compares the organization's spatial coverage before and after an update. If a
    change is detected, it enqueues a job to reindex all active datasets for that
    organization.
    """
    spatial_coverage_before = tk.get_action("organization_show")(
        {}, {"id": data_dict["id"]}
    ).get("spatial_coverage")

    result = next_action(context, data_dict)

    spatial_coverage_after = tk.get_action("organization_show")(
        {}, {"id": data_dict["id"]}
    ).get("spatial_coverage")

    if spatial_coverage_before != spatial_coverage_after:
        enqueue(reindex_organization_datasets, kwargs={"org_id": result["id"]})
    return result
