from __future__ import annotations

import pytest
from playwright.sync_api import Page, expect


@pytest.mark.playwright()
def test_search_page(page: Page):
    page.goto("/")
    page.get_by_role("link", name="Datasets").click()
    expect(page).to_have_url("/dataset/")
