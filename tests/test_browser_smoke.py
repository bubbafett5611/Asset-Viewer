from __future__ import annotations

import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests

playwright = pytest.importorskip("playwright.sync_api")


BASE_URL = "http://127.0.0.1:5001"
ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def live_server():
    process = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import sys; "
                f"sys.path.insert(0, {str(ROOT / 'backend')!r}); "
                "import server; "
                "server.app.run(host='127.0.0.1', port=5001, debug=False, use_reloader=False)"
            ),
        ],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        for _ in range(40):
            try:
                if requests.get(f"{BASE_URL}/api/roots", timeout=0.5).ok:
                    break
            except requests.RequestException:
                time.sleep(0.25)
        else:
            pytest.fail("Asset Viewer server did not start on port 5001")
        yield BASE_URL
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()


def test_browser_smoke_loads_core_flows(live_server):
    errors = []
    with playwright.sync_playwright() as pw:
        browser = pw.chromium.launch()
        page = browser.new_page()
        page.on("console", lambda message: errors.append(message.text) if message.type == "error" else None)
        page.goto(live_server, wait_until="load")

        assert page.title() == "Bubba Media Viewer"
        page.get_by_role("button", name="Media").click()
        page.get_by_role("searchbox", name="Search").fill("Challenge")
        page.get_by_text("Loaded", exact=False).wait_for(timeout=5000)

        page.get_by_role("button", name="Tag Browser").click()
        page.get_by_role("searchbox", name="Tag Search").fill("red hair")
        page.get_by_text("Showing", exact=False).wait_for(timeout=5000)

        browser.close()

    assert errors == []
