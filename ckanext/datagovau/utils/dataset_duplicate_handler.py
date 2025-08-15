from __future__ import annotations

import logging
from typing import Any

import sqlalchemy as sa

import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib.search.query import solr_literal

log = logging.getLogger(__name__)


def get_metaphone_cluster(title: str) -> list[str]:
    """Find datasets with similar phonetic encoding based on title.

    Args:
        title (str): Title to find similar phonetic matches
    """
    # Use dmetaphone for phonetic matching
    metaphone_key = sa.func.dmetaphone(title)

    query = sa.select(sa.func.array_agg(model.Package.id).label("dataset_ids")).where(
        sa.func.dmetaphone(model.Package.title) == metaphone_key
    )
    cluster = model.Session.scalar(query)

    # if we have just one dataset in cluster, it's an original and cluster
    # essentially does not exist
    if len(cluster) < 2:
        return []

    return cluster


def find_copies(
    pkg_dict: dict[str, Any],
    similarity_threshold: float = 1.0,
) -> dict[str, Any]:
    """Detect potential duplicate datasets.

    Logic is based on phonetic similarity and resource comparison.
    Compares the current dataset's title, notes, and original_name against
    other datasets' metadata and resources, applying a similarity threshold
    to identify duplicates.
    """
    original_name = pkg_dict.get("original_name")
    title = pkg_dict["title"]
    notes = pkg_dict["notes"]

    # Get metaphone cluster for potential duplicates
    dataset_ids = get_metaphone_cluster(title)

    # If no cluster found, return early
    if not dataset_ids:
        return {"is_original": True, "original": pkg_dict, "duplicates": []}

    # Construct refined query for exact matching
    refined_query = (
        sa.select(
            model.Package.id.label("dataset_id"),
            sa.func.count(model.Resource.id).label("resource_count"),
            sa.func.array_remove(
                sa.func.coalesce(
                    sa.func.array_agg(model.Resource.format),
                    sa.cast(sa.text("ARRAY[]"), sa.ARRAY(sa.String)),
                ),
                None,
            ).label("resource_formats"),
        )
        .select_from(model.Package)
        .outerjoin(
            model.Resource,
            model.Resource.package_id == model.Package.id,
        )
        .join(
            model.PackageExtra,
            sa.and_(
                model.PackageExtra.package_id == model.Package.id,
                model.PackageExtra.key == "original_name",
            ),
        )
        .where(
            sa.and_(
                # Filter by previously found cluster IDs
                model.Package.id.in_(set(dataset_ids) - {pkg_dict.get("id")}),
            )
        )
        .group_by(
            model.Package.id,
            model.PackageExtra.value,
        )
        .having(
            sa.and_(
                # Apply strict similarity conditions
                sa.func.strict_word_similarity(model.Package.title, title)
                == similarity_threshold,
                sa.func.strict_word_similarity(model.Package.notes, notes)
                == similarity_threshold,
                sa.func.strict_word_similarity(model.PackageExtra.value, original_name)
                == similarity_threshold,
            )
        )
    )
    duplicates = [
        {
            "dataset_id": dataset_id,
            "resource_count": resource_count,
            "resource_formats": resource_formats,
        }
        for dataset_id, resource_count, resource_formats in model.Session.execute(
            refined_query
        )
    ]

    if not duplicates:
        return {"is_original": True, "original": pkg_dict, "duplicates": []}

    valid_duplicates = compare_resources(pkg_dict, duplicates)

    return set_duplicate_relationships(pkg_dict, valid_duplicates)


def compare_resources(
    pkg_dict: dict[str, Any],
    duplicates: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """Compare resources of the current dataset with potential duplicates."""
    resource_count = len(pkg_dict["resources"])
    resource_formats = sorted([r["format"] for r in pkg_dict["resources"]])

    return [
        duplicate
        for duplicate in duplicates
        if resource_count == duplicate["resource_count"]
        and resource_formats == sorted(duplicate["resource_formats"])
    ]


def set_duplicate_relationships(
    pkg_dict: dict[str, Any],
    duplicates: list[dict[str, Any]],
) -> dict[str, Any]:
    """Determine if the current dataset is the original.

    If dataset determine their relationships.
    """
    if not duplicates:
        return {"is_original": True, "original": pkg_dict, "duplicates": []}

    # candidates = [pkg_dict] + [
    #     tk.get_action("package_show")({}, {"id": d["dataset_id"]}) for d in duplicates
    # ]

    fq = "id:({})".format(
        " OR ".join(solr_literal(d["dataset_id"]) for d in duplicates)
    )
    result = tk.get_action("package_search")(
        {},
        {
            "fq": fq,
            # this line can detect 1000 duplicates at most, which is far more
            # that we expect in real life so there is no need to write a loop
            # here
            "rows": len(duplicates),
        },
    )
    candidates = [pkg_dict] + result["results"]

    # Sort the candidates by duplicate_score to find the original
    sorted_candidates = sorted(candidates, key=lambda x: x["duplicate_score"])
    original_dataset = sorted_candidates.pop(0)

    # Determine if the current dataset is the original
    is_original = pkg_dict["id"] == original_dataset["id"]

    # Return the relationship details
    return {
        "is_original": is_original,
        "original": original_dataset,
        "duplicates": sorted_candidates,
    }
