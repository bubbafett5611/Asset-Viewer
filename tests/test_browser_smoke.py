from __future__ import annotations

import pytest
from playwright import sync_api as playwright
from ui_fixture import start_server, install_routes


@pytest.fixture(scope="module")
def live_server():
    server, url = start_server()
    try:
        yield url
    finally:
        server.shutdown()


def test_browser_smoke_loads_core_flows(live_server):
    errors = []
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        install_routes(page)
        page.goto(live_server, wait_until="load")

        assert page.title() == "Bubba Media Viewer"
        page.get_by_role("button", name="Media").click()
        page.get_by_role("searchbox", name="Search").fill("Challenge")
        page.locator(".media-feedback").get_by_text("Loaded", exact=False).wait_for(timeout=5000)

        page.get_by_role("button", name="Tag Browser").click()
        page.get_by_role("searchbox", name="Tag Search").fill("red hair")
        page.get_by_text("Showing", exact=False).wait_for(timeout=5000)

        browser.close()

    assert errors == []
