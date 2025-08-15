from __future__ import annotations

import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib.search import rebuild


def reindex_organization_datasets(org_id: str) -> None:
    """Reindexes active datasets for an organization in Solr when needed.

    Processes datasets in batches of 50 to optimize performance for large organizations.
    """
    if not org_id:
        raise ValueError("Organisation id is required")

    dataset_ids = _get_active_dataset_ids(org_id)
    if not dataset_ids:
        return

    batch_size = 50
    for i in range(0, len(dataset_ids), batch_size):
        batch_ids = dataset_ids[i : i + batch_size]
        _reindex_batch(batch_ids, org_id)


def _get_active_dataset_ids(org_id: str) -> list[str]:
    """Fetches IDs of all active datasets belonging to an organization."""
    query = model.Session.query(model.Package.id).filter(
        model.Package.owner_org == org_id, model.Package.state == "active"
    )
    return [row[0] for row in query.all()]


def _reindex_batch(batch_ids: list[str], org_id: str) -> None:
    """Reindexes a batch of datasets in Solr if spatial coverage is unset.

    Searches the Solr index for the given dataset IDs and reindexes only those datasets
    lacking spatial coverage.
    """
    q = " OR ".join(f'id:"{id}"' for id in batch_ids)
    q_dict = {
        "q": q,
        "rows": len(batch_ids),
        "fl": "id,spatial_coverage",  # Optimized to fetch only needed fields
        "include_private": True,
    }

    results = tk.get_action("package_search")({"ignore_auth": True}, q_dict)["results"]

    for result in results:
        if result.get("spatial_coverage"):
            continue
        rebuild(result["id"], force=True)
