"""Desktop redesign regression tests. All API responses and media are synthetic."""

import os
import re

import pytest
from playwright.sync_api import sync_playwright, expect
from ui_fixture import ROOT, start_server, install_routes

if (ROOT / "build" / "browsers").exists():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "build" / "browsers"))


@pytest.fixture(scope="module")
def browser():
    with sync_playwright() as pw:
        instance = pw.chromium.launch()
        yield instance
        instance.close()


@pytest.fixture(scope="module")
def server_url():
    server, url = start_server()
    yield url
    server.shutdown()


@pytest.fixture
def ui(browser, server_url):
    context = browser.new_context(viewport={"width": 1440, "height": 900})
    page = context.new_page()
    errors = []
    page.on("pageerror", lambda error: errors.append(str(error)))
    state = install_routes(page)
    yield page, state, server_url
    context.close()
    assert not errors, errors


def open_media(page, url):
    page.goto(url)
    expect(page.locator(".asset-card").first).to_be_visible()


def capture(page, name):
    output = ROOT / "build" / "ui-redesign"
    output.mkdir(parents=True, exist_ok=True)
    page.screenshot(path=str(output / f"{name}.png"), animations="disabled")


@pytest.mark.parametrize("size", [(1024, 768), (1440, 900), (1920, 1080)])
def test_desktop_sections_fit(ui, size):
    page, _, url = ui
    page.set_viewport_size({"width": size[0], "height": size[1]})
    open_media(page, url)
    for section in ["Media", "Tag Browser", "Duplicates", "Stats", "Settings"]:
        page.get_by_role("button", name=section, exact=True).click()
        page.wait_for_timeout(150)
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth"), section
        assert page.locator(".app-workspace").evaluate("(el) => el.scrollWidth <= el.clientWidth + 1"), section
        # Every visible main control must stay within its section, including narrow desktop toolbars.
        for box in page.locator(".app-workspace button:visible, .app-workspace select:visible").evaluate_all(
            "(els) => els.map(el => {const r=el.getBoundingClientRect(); return {right:r.right, left:r.left, text:el.textContent}})"
        ):
            assert box["right"] <= size[0] + 1 and box["left"] >= 220, box
        capture(page, f"{size[0]}-{section.lower().replace(' ', '-')}")


def test_selection_inspector_and_dialogs(ui):
    page, _, url = ui
    open_media(page, url)
    cards = page.locator(".asset-card")
    cards.nth(0).click()
    expect(page.locator(".selection-bar")).to_contain_text("1 selected")
    expect(page.locator(".selection-check").first).to_be_visible()
    page.get_by_role("button", name="Inspector", exact=True).click()
    expect(page.locator(".asset-details-panel")).to_have_count(0)
    page.get_by_role("button", name="Tag Browser", exact=True).click()
    expect(page.locator(".tag-details-panel")).not_to_be_visible()
    page.get_by_role("button", name="Media", exact=True).click()
    page.get_by_role("button", name="Inspector", exact=True).click()
    cards.nth(0).click(modifiers=["Control"])
    cards.nth(2).click(modifiers=["Shift"])
    expect(page.locator(".selection-bar")).to_contain_text("3 selected")
    capture(page, "selection")
    expect(page.get_by_role("button", name="Compare", exact=True)).to_be_disabled()
    cards.nth(2).click(modifiers=["Control"])
    page.get_by_role("button", name="Compare", exact=True).click()
    expect(page.locator("dialog.compare-modal")).to_be_visible()
    assert page.evaluate("document.activeElement.closest('dialog') !== null")
    capture(page, "compare")
    page.keyboard.press("Escape")
    expect(page.locator("dialog.compare-modal")).to_have_count(0)
    expect(page.get_by_role("button", name="Compare", exact=True)).to_be_focused()
    page.get_by_role("button", name="Slideshow", exact=True).click()
    expect(page.locator("dialog.review-slideshow")).to_be_visible()
    page.keyboard.press("ArrowRight")
    page.get_by_role("button", name="Play", exact=True).click()
    expect(page.get_by_role("button", name="Pause", exact=True)).to_be_visible()
    capture(page, "slideshow")
    page.keyboard.press("Escape")
    expect(page.get_by_role("button", name="Slideshow", exact=True)).to_be_focused()
    page.get_by_role("button", name="Clear", exact=True).click()
    expect(page.locator(".selection-bar")).to_have_count(0)


def test_filters_saved_views_and_no_matches(ui):
    page, _, url = ui
    open_media(page, url)
    page.get_by_role("searchbox", name="Search", exact=True).fill("Alpine")
    expect(page.locator(".asset-card")).to_have_count(3)
    page.get_by_role("button", name="Saved views", exact=True).click()
    page.get_by_role("textbox", name="Saved view name").fill("Alpine studies")
    page.get_by_role("button", name="Save view", exact=True).click()
    page.get_by_role("button", name="Remove search filter").click()
    expect(page.locator(".asset-card")).to_have_count(18)
    page.get_by_role("button", name="Alpine studies", exact=True).click()
    expect(page.locator(".asset-card")).to_have_count(3)
    page.reload()
    expect(page.get_by_role("button", name="Alpine studies", exact=True)).to_be_visible()
    page.get_by_role("button", name="Archive", exact=True).click()
    expect(page.get_by_role("button", name="Alpine studies", exact=True)).to_have_count(0)
    page.get_by_role("searchbox", name="Search", exact=True).fill("not found")
    expect(page.get_by_role("heading", name="No matching media")).to_be_visible()
    capture(page, "no-matches")
    page.get_by_role("button", name="Clear filters", exact=True).click()
    expect(page.locator(".asset-card")).to_have_count(18)
    expect(page.locator(".media-breadcrumb")).to_contain_text("Archive")


@pytest.mark.parametrize(
    "condition,heading",
    [
        ("root_error", "Could not load libraries"),
        ("no_roots", "Add your first library"),
        ("empty", "This folder has no media"),
        ("asset_error", "Could not load media"),
    ],
)
def test_empty_and_error_recovery(ui, condition, heading):
    page, state, url = ui
    state[condition] = True
    page.goto(url)
    expect(page.get_by_role("heading", name=heading)).to_be_visible()
    capture(page, condition)
    if condition == "no_roots":
        page.get_by_role("button", name="Open settings").click()
        expect(page.get_by_role("heading", name="Settings", exact=True)).to_be_visible()
    elif condition.endswith("error"):
        state[condition] = False
        page.get_by_role("button", name="Retry", exact=True).click()
        expect(page.locator(".asset-card")).to_have_count(18)


def test_refresh_pagination_virtualization_and_root_safety(ui):
    page, state, url = ui
    state["count"] = 360
    open_media(page, url)
    expect(page.locator(".asset-card")).to_have_count(120)
    state["asset_error"] = True
    page.get_by_role("button", name="Refresh", exact=True).click()
    expect(page.get_by_role("button", name="Retry", exact=True)).to_be_visible()
    expect(page.locator(".asset-card")).to_have_count(120)
    state["asset_error"] = False
    page.get_by_role("button", name="Retry", exact=True).click()
    expect(page.get_by_role("button", name="Retry", exact=True)).to_have_count(0)
    state["page_error"] = True
    page.get_by_role("button", name="Load More", exact=True).click()
    expect(page.get_by_role("button", name="Retry", exact=True)).to_be_visible()
    assert state["offsets"][-1] == 120
    state["page_error"] = False
    page.get_by_role("button", name="Retry", exact=True).click()
    expect(page.locator(".asset-card")).to_have_count(240)
    assert state["offsets"][-1] == 120
    page.get_by_role("button", name="Load More", exact=True).click()
    expect(page.locator(".asset-list")).to_have_class(re.compile("virtualized"))
    page.locator(".asset-list").evaluate("(el) => el.scrollTop = 1000")
    page.get_by_role("button", name="Inspector", exact=True).click()
    expect(page.locator(".asset-card").first).to_be_visible()
    for density, height in [("compact", 228), ("comfortable", 270), ("large", 318)]:
        page.get_by_role("combobox", name="Density", exact=True).select_option(density)
        page.wait_for_timeout(100)
        positions = page.locator(".asset-card").evaluate_all(
            "(els) => [...new Set(els.map(el => Math.round(el.getBoundingClientRect().top)))]"
        )
        assert abs(positions[1] - positions[0] - height) <= 1
    capture(page, "virtualized-large")
    page.locator(".asset-card").first.click()
    page.get_by_role("button", name="Archive", exact=True).click()
    expect(page.locator(".selection-bar")).to_have_count(0)
    expect(page.locator(".media-breadcrumb")).to_contain_text("Archive")


def test_keyboard_menus_and_reduced_motion(ui):
    page, _, url = ui
    page.emulate_media(reduced_motion="reduce")
    open_media(page, url)
    page.locator(".asset-card").first.click()
    before = page.locator(".asset-card").first.bounding_box()
    page.locator(".asset-card").first.hover()
    assert page.locator(".asset-card").first.bounding_box() == before
    page.locator(".selection-bar summary").filter(has_text="Export").click()
    page.get_by_role("button", name="Export JSON", exact=True).focus()
    page.keyboard.press("Escape")
    expect(page.locator(".selection-bar summary").filter(has_text="Export")).to_be_focused()
    page.get_by_role("button", name="Keyboard shortcuts", exact=False).click()
    expect(page.locator("dialog.shortcuts-modal")).to_be_visible()
    page.keyboard.press("Escape")
    expect(page.locator("dialog.shortcuts-modal")).to_have_count(0)
    expect(page.get_by_role("button", name="Keyboard shortcuts", exact=False)).to_be_focused()


def test_resizing_long_names_and_broken_thumbnails(ui):
    page, state, url = ui
    state.update(long_name=True, broken_thumbnail=True)
    page.set_viewport_size({"width": 1024, "height": 768})
    open_media(page, url)
    expect(page.locator(".asset-thumb-fallback").first).to_be_visible()
    page.locator(".asset-card").first.click()
    separator = page.get_by_role("separator", name="Resize details panel width")
    separator.focus()
    for _ in range(8):
        page.keyboard.press("ArrowRight")
    assert round(page.locator(".asset-details-panel").bounding_box()["width"]) == 280
    for _ in range(12):
        page.keyboard.press("ArrowLeft")
    assert page.locator(".assets-panel").bounding_box()["width"] >= 420
    assert page.locator(".asset-details-panel").evaluate("(el) => el.scrollWidth <= el.clientWidth")
    expect(page.locator(".details-scroll summary").filter(has_text="Generation")).to_be_visible()
    page.locator(".details-scroll summary").filter(has_text="Generation").click()
    page.locator(".details-scroll summary").filter(has_text="Embedded metadata").click()
    capture(page, "long-name-fallback")


def test_loading_and_delete_dialog_are_explicit(ui):
    page, _, url = ui
    held = []
    page.route("**/api/assets/list?**", lambda route: held.append(route))
    page.goto(url)
    expect(page.get_by_role("heading", name="Loading media…")).to_be_visible()
    expect(page.get_by_role("heading", name="No matching media")).to_have_count(0)
    capture(page, "loading")
    page.unroute("**/api/assets/list?**")
    for route in held:
        try:
            route.fallback()
        except Exception:
            pass  # A newer initial request can abort its predecessor.
    expect(page.locator(".asset-card").first).to_be_visible()
    page.locator(".asset-card").first.click()
    page.locator(".selection-bar").get_by_role("button", name="Delete", exact=True).click()
    expect(page.locator("dialog.delete-confirm-modal")).to_be_visible()
    capture(page, "delete-confirmation")
    assert page.evaluate("document.activeElement.closest('dialog') !== null")
    page.keyboard.press("Escape")
    expect(page.locator("dialog.delete-confirm-modal")).to_have_count(0)
    expect(page.locator(".selection-bar").get_by_role("button", name="Delete", exact=True)).to_be_focused()


def test_duplicate_scan_results(ui):
    page, _, url = ui
    open_media(page, url)
    page.get_by_role("button", name="Duplicates", exact=True).click()
    page.get_by_role("button", name="Scan", exact=True).click()
    expect(page.locator(".duplicate-group")).to_have_count(1)
    capture(page, "duplicate-results")


def test_video_playback_and_review_blur(ui):
    page, state, url = ui
    # Record a short synthetic canvas clip; no external media or real library is used.
    clip = page.evaluate("""async () => {
      const canvas = document.createElement('canvas'); canvas.width=160; canvas.height=120;
      const ctx=canvas.getContext('2d'); const stream=canvas.captureStream(10);
      const recorder=new MediaRecorder(stream, {mimeType:'video/webm'}); const chunks=[];
      recorder.ondataavailable=e=>chunks.push(e.data);
      const done=new Promise(resolve=>recorder.onstop=resolve); recorder.start();
      let frame=0; const timer=setInterval(()=>{ctx.fillStyle=frame++ % 2 ? '#bd93f9' : '#282a36';ctx.fillRect(0,0,160,120);},80);
      await new Promise(resolve=>setTimeout(resolve,800)); recorder.stop(); await done;
      clearInterval(timer); stream.getTracks().forEach(track=>track.stop());
      return Array.from(new Uint8Array(await new Blob(chunks).arrayBuffer()));
    }""")
    state["video"] = bytes(clip)
    open_media(page, url)
    page.locator(".asset-card").first.click()
    video = page.locator(".preview-frame video")
    expect(video).to_be_visible()
    video.evaluate("(el) => el.play()")
    assert video.evaluate("(el) => !el.paused && el.error === null")
    page.get_by_role("checkbox", name="Blur", exact=True).check()
    page.get_by_role("button", name="Slideshow", exact=True).click()
    expect(page.locator(".review-stage video")).to_have_class("review-blurred")
    page.locator(".review-stage video").evaluate("(el) => el.play()")
    assert page.locator(".review-stage video").evaluate("(el) => el.controls && !el.paused")
    page.keyboard.press("Escape")
    expect(page.get_by_role("button", name="Slideshow", exact=True)).to_be_focused()


def test_theme_contrast(ui):
    page, _, url = ui
    open_media(page, url)
    tokens = page.evaluate(
        "Object.fromEntries(['--text','--muted','--accent','--panel','--panel-strong','--bg-2'].map(key=>[key,getComputedStyle(document.documentElement).getPropertyValue(key).trim()]))"
    )

    def luminance(color):
        channels = [int(color[i : i + 2], 16) / 255 for i in (1, 3, 5)]
        linear = [c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in channels]
        return sum(c * weight for c, weight in zip(linear, [0.2126, 0.7152, 0.0722]))

    for foreground in ["--text", "--muted", "--accent"]:
        for background in ["--panel", "--panel-strong", "--bg-2"]:
            ratio = (luminance(tokens[foreground]) + 0.05) / (luminance(tokens[background]) + 0.05)
            assert ratio >= 4.5, (foreground, background, ratio)
