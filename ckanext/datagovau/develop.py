"""Things that are used on local instances for development."""

from __future__ import annotations

from typing import Any

import ckan.plugins.toolkit as tk


def static_header_links(type: str) -> list[dict[str, Any]]:
    if type == "main":
        return [
            {
                "label": "Datasets",
                "href": tk.h.url_for("dataset.search", _external=True),
            },
            {
                "label": "Organisations",
                "href": tk.h.url_for("organization.index", _external=True),
            },
            {
                "label": "About",
                "href": "/about",
            },
        ]

    if type == "publishers":
        return [
            {
                "label": "Login",
                "href": tk.h.url_for("user.login", _external=True),
            },
            {
                "label": "User Guide",
                "href": "/user-guide",
            },
        ]

    if type == "footer":
        return [
            {
                "label": "Accessibility",
                "href": "/accessibility",
            },
            {
                "label": "Copyright",
                "href": "/copyright",
            },
            {
                "label": "Disclaimers",
                "href": "/disclaimers",
            },
        ]

    if type == "developers":
        return [
            {
                "label": "CKAN Documentation",
                "href": "https://ckan.org/",
            },
        ]

    if type == "site":
        return [
            {
                "label": "About",
                "href": r"\/about",
            },
            {
                "label": "Privacy Policy",
                "href": r"\/policy",
            },
            {
                "label": "Recent Developments",
                "href": r"\/recent-developments",
            },
            {
                "label": "Give feedback",
                "href": r"\/give-feedback",
            },
            {
                "label": "Contact us",
                "href": r"\/contact\/feedback",
            },
        ]

    return []
