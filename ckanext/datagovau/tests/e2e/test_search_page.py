from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright
def test_presence_of_the_location_filter(page: Page):
    """When location selected user sees filter-pill on search form."""
    page.goto("/dataset")

    page.get_by_label("Expand map").click()
    page.get_by_label("West bounding longitude").fill("1")
    page.get_by_label("East bounding longitude").fill("2")
    page.get_by_label("South bounding latitude").fill("3")

    north = page.get_by_label("North bounding latitude")
    north.fill("4")
    # search button activates after field looses focus
    north.blur()

    page.get_by_label("Apply spatial search").click()

    expect(page.locator(".filter-list")).to_have_text(
        "Location extent: West longitude 1.0°, South latitude 3.0°,"
        " East longitude 2.0°, North latitude 4.0°"
    )
