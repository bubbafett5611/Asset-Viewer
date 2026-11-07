"""Synthetic, network-isolated browser fixture for UI tests and screenshots."""

from functools import partial
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from threading import Thread
from urllib.parse import urlparse, parse_qs
import json
import os

ROOT = Path(__file__).resolve().parents[1]
if (ROOT / "build" / "browsers").exists():
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / "build" / "browsers"))


class QuietHandler(SimpleHTTPRequestHandler):
    extensions_map = {**SimpleHTTPRequestHandler.extensions_map, ".js": "application/javascript"}

    def log_message(self, *args):
        pass


def start_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), partial(QuietHandler, directory=str(ROOT / "frontend")))
    Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}/asset_viewer_vue.html"


def assets(count=18, root="studio"):
    names = ["Alpine study", "Evening coastline", "Forest light", "Desert forms", "Winter ridge", "Quiet lake"]
    return [
        dict(
            path=f"{root}/renders/study-{i:03}.png",
            name=f"{names[i % 6]} — {i:03}.png",
            relative_path=f"renders/study-{i:03}.png",
            extension=".png",
            size_bytes=1048576 + i * 2048,
            modified_ts=1780000000 + i,
            metadata_badges=[{"key": "parameters", "label": "Params"}],
        )
        for i in range(count)
    ]


def install_routes(page, state=None):
    state = state if state is not None else {}

    def route(request):
        url = urlparse(request.request.url)
        query = parse_qs(url.query)
        path = url.path
        if not url.hostname or url.hostname != "127.0.0.1":
            request.fulfill(status=200, body="")
            return
        if not path.startswith(("/api/", "/bubba/")):
            request.continue_()
            return
        data = {}
        if path == "/api/settings":
            data = {
                "settings": {
                    "general": {"asset_roots": ["studio"], "check_for_updates": False},
                    "viewer": {"density": "comfortable", "preview": False},
                },
                "schema": {
                    "properties": {
                        "general": {
                            "type": "object",
                            "properties": {"asset_roots": {"type": "array", "items": {"type": "string"}}},
                        },
                        "viewer": {
                            "type": "object",
                            "properties": {
                                "density": {"enum": ["compact", "comfortable", "large"]},
                                "preview": {"type": "boolean"},
                            },
                        },
                    }
                },
            }
        elif path == "/api/roots":
            if state.get("root_error"):
                request.fulfill(status=503, json={"error": "Offline"})
                return
            data = {
                "roots": []
                if state.get("no_roots")
                else [{"key": "studio", "label": "Studio library"}, {"key": "archive", "label": "Archive"}]
            }
        elif path == "/api/app/info":
            data = {"version": "0.1.1"}
        elif path == "/api/assets/folders":
            data = {
                "folders": [
                    {"path": "", "label": "All folders"},
                    {"path": "renders", "label": "renders"},
                    {"path": "renders/landscapes", "label": "landscapes"},
                    {"path": "references", "label": "references"},
                ]
            }
        elif path == "/api/assets/list":
            offset = int(query.get("offset", ["0"])[0])
            state.setdefault("offsets", []).append(offset)
            if state.get("asset_error") or state.get("page_error") and offset > 0:
                request.fulfill(status=503, json={"error": "Offline"})
                return
            items = assets(state.get("count", 18), query.get("root", ["studio"])[0])
            if state.get("video"):
                items[0].update(path="studio/review.mp4", extension=".mp4", name="Review clip.mp4")
            if state.get("long_name"):
                items[0]["name"] = "A-very-long-descriptive-filename-" * 8 + ".png"
            search = query.get("q", [""])[0].lower()
            items = [a for a in items if search in a["name"].lower()]
            if state.get("empty") or query.get("ext", [""])[0] == ".webp":
                items = []
            data = {"assets": items[offset : offset + int(query.get("limit", ["120"])[0])]}
        elif path == "/api/assets/details":
            selected = query.get("path", [""])[0]
            item = next((a for a in assets(state.get("count", 18)) if a["path"] == selected), assets(1)[0])
            if state.get("long_name"):
                item["name"] = "A-very-long-descriptive-filename-" * 8 + ".png"
            data = {
                "asset": {
                    **item,
                    "path": selected,
                    "width": 1024,
                    "height": 768,
                    "metadata": {
                        "format": "PNG",
                        "keys": ["parameters"],
                        "metadata": {
                            "generation": {
                                "seed": 42,
                                "steps": 24,
                                "positive_prompt": "Quiet landscape, soft evening light",
                            },
                            "parameters": "Quiet landscape, soft evening light\nSteps: 24, Seed: 42",
                        },
                    },
                }
            }
        elif path in ("/api/assets/thumb", "/api/assets/file"):
            identifier = query.get("path", [""])[0]
            if identifier.endswith(".mp4") and state.get("video"):
                request.fulfill(content_type="video/webm", body=state["video"])
                return
            if state.get("broken_thumbnail") and path.endswith("/thumb"):
                request.fulfill(status=404, body="Not found")
                return
            i = sum(map(ord, identifier)) % 6
            colors = ["#668a8d", "#b78c76", "#71856c", "#b9a481", "#8491ad", "#739ca6"]
            svg = f'<svg xmlns="http://www.w3.org/2000/svg" width="640" height="480" viewBox="0 0 640 480"><rect width="640" height="480" fill="{colors[i]}"/><circle cx="460" cy="130" r="52" fill="#eee0b9"/><path d="M0 360L170 130L310 320L420 210L640 370V480H0Z" fill="#384955"/><path d="M0 410L220 280L400 390L550 300L640 350V480H0Z" fill="#26333e"/></svg>'
            request.fulfill(content_type="image/svg+xml", body=svg)
            return
        elif path == "/api/tags":
            data = {
                "tags": [
                    {"name": name, "category": "general", "count": 1200 - i * 100, "aliases": "", "source": "local"}
                    for i, name in enumerate(["landscape", "mountain", "forest", "sunset", "water", "cloud"])
                ],
                "total": 6,
                "categories": ["general"],
            }
        elif path == "/api/assets/stats" or path == "/api/assets/metadata/health":
            data = {
                "stats": {
                    "total_files": 18,
                    "total_bytes": 18874368,
                    "image_files": 18,
                    "total_assets": 18,
                    "png_assets": 18,
                    "parameters": 15,
                    "no_tracked_metadata": 3,
                }
            }
        elif path == "/api/assets/duplicates/stream":
            data = {
                "type": "result",
                "groups": [{"id": "group-1", "kind": "exact", "count": 2, "assets": assets(2)}],
                "summary": {"groups": 1, "assets": 2},
            }
            request.fulfill(content_type="application/x-ndjson", body=json.dumps(data) + "\n")
            return
        request.fulfill(json=data)

    page.route("**/*", route)
    return state


def capture_demo():
    from playwright.sync_api import sync_playwright, expect

    server, url = start_server()
    output = ROOT / "docs"
    output.mkdir(parents=True, exist_ok=True)
    try:
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 900})
            install_routes(page)
            page.goto(url)
            page.locator(".asset-card").first.wait_for()
            page.locator(".asset-card").nth(0).click()
            expect(page.locator(".metadata-status")).to_contain_text("Generation data")
            page.get_by_role("button", name="Saved views", exact=True).click()
            page.get_by_role("textbox", name="Saved view name").fill("Recent renders")
            page.get_by_role("button", name="Save view", exact=True).click()
            page.locator(".media-breadcrumb").click()
            page.screenshot(path=str(output / "media-viewer.png"), animations="disabled")
            browser.close()
    finally:
        server.shutdown()


if __name__ == "__main__":
    capture_demo()
