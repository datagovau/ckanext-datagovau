from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk

IGNORE_WORKFLOW = "ckanext.datagovau.spatialingestor.ignore_workflow"
LGA_TIMEOUT = "ckanext.datagovau.lga_service.timeout"
LGA_URL = "ckanext.datagovau.lga_service.search_url"
LGA_PARAMS = "ckanext.datagovau.lga_service.search_params"
LGA_NAME = "ckanext.datagovau.lga_service.name_attribute"
ANONYMOUS_SUGGESTION = "ckanext.datagovau.suggest_dataset.allow_anonymous"
ANONYMOUS_QUESTION = "ckanext.datagovau.ask_question.allow_anonymous"
SUGGEST_DATASET_EMAILS = "ckanext.datagovau.suggest_dataset.emails"


def ignore_si_workflow() -> bool:
    """Skip spatial ingestion after dataset modifications."""
    return tk.config[IGNORE_WORKFLOW]


def lga_timeout() -> int:
    """Request timeout for map service."""
    return tk.config[LGA_TIMEOUT]


def anonymous_suggestion() -> bool:
    """Allow anonymous users to suggest datasets."""
    return tk.config[ANONYMOUS_SUGGESTION]


def anonymous_question() -> bool:
    """Allow anonymous users to ask questions."""
    return tk.config[ANONYMOUS_QUESTION]


def lga_url() -> str:
    """URL of the ArcGIS search endpoint that returns list of LGA details."""
    return tk.config[LGA_URL]


def lga_params() -> dict[str, Any]:
    """Parameters for LGA search service."""
    return tk.config[LGA_PARAMS]


def lga_name() -> str:
    """The attribute inside LGA service's response, that contains LGA name."""
    return tk.config[LGA_NAME]


def suggest_dataset_emails() -> list[str]:
    """The list of email addresses that will receive 'suggest a dataset' emails."""
    return tk.config[SUGGEST_DATASET_EMAILS]
