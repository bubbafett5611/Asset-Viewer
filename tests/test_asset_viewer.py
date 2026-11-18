from __future__ import annotations

from io import BytesIO
import json
import os
from pathlib import Path
import sqlite3
import sys
import threading
import time

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, "backend")

import server  # noqa: E402
from services import app_context  # noqa: E402
from services import asset_api  # noqa: E402
from services import asset_viewer_duplicates  # noqa: E402
from services import asset_viewer_metadata  # noqa: E402
from services import tag_api  # noqa: E402
from asset_viewer import AssetRoot  # noqa: E402
import runtime_paths  # noqa: E402
from settings_model import Settings  # noqa: E402


@pytest.fixture()
def asset_root(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    root.mkdir()
    monkeypatch.setattr(
        app_context,
        "ASSET_ROOTS",
        [AssetRoot(key="test", label="Test Assets", path=str(root))],
    )
    return root


@pytest.fixture()
def client(asset_root):
    server.app.config.update(TESTING=True)
    return server.app.test_client()


def make_png_bytes(color=(255, 0, 0, 255)):
    image = Image.new("RGBA", (16, 16), color)
    buffer = BytesIO()
    image.save(buffer, "PNG")
    buffer.seek(0)
    return buffer


def make_png_with_metadata(metadata):
    image = Image.new("RGBA", (16, 16), (0, 0, 255, 255))
    pnginfo = PngInfo()
    pnginfo.add_text("bubba_metadata", metadata)
    buffer = BytesIO()
    image.save(buffer, "PNG", pnginfo=pnginfo)
    buffer.seek(0)
    return buffer


def make_png_with_text_chunks(chunks):
    image = Image.new("RGBA", (16, 16), (0, 0, 255, 255))
    pnginfo = PngInfo()
    for key, value in chunks.items():
        pnginfo.add_text(key, value)
    buffer = BytesIO()
    image.save(buffer, "PNG", pnginfo=pnginfo)
    buffer.seek(0)
    return buffer


def make_png_with_repairable_prompt():
    prompt = {
        "1": {
            "class_type": "Checkpoint Loader (Simple)",
            "inputs": {"ckpt_name": "model.safetensors"},
        },
        "2": {
            "class_type": "CLIPTextEncode",
            "inputs": {"text": "negative", "clip": ["1", 1]},
        },
        "3": {
            "class_type": "Prompt (LoraManager)",
            "inputs": {
                "text": "positive",
                "trigger_words": ["4", 0],
                "clip": ["5", 1],
            },
        },
        "4": {
            "class_type": "TriggerWord Toggle (LoraManager)",
            "inputs": {
                "toggle_trigger_words": {
                    "__value__": [
                        {"text": "glowing", "active": True},
                        {"text": "inactive", "active": False},
                    ],
                },
            },
        },
        "5": {
            "class_type": "Lora Loader (LoraManager)",
            "inputs": {
                "loras": {"__value__": [{"name": "NeonLineart", "strength": "0.50", "active": True}]},
                "model": ["1", 0],
                "clip": ["1", 1],
            },
        },
        "6": {"class_type": "Sampler Selector (Image Saver)", "inputs": {"sampler_name": "dpmpp_2m_sde"}},
        "7": {"class_type": "Scheduler Selector (Image Saver)", "inputs": {"scheduler": "karras"}},
        "8": {"class_type": "easy seed", "inputs": {"seed": 12345}},
        "9": {
            "class_type": "iToolsKSampler",
            "inputs": {
                "seed": ["8", 0],
                "steps": 20,
                "cfg": 5.5,
                "sampler_name": ["6", 0],
                "scheduler": ["7", 0],
                "denoise": 0.75,
                "model": ["5", 0],
                "positive": ["3", 0],
                "negative": ["2", 0],
            },
        },
    }
    return make_png_with_text_chunks({"prompt": json.dumps(prompt), "workflow": "{}"})


def test_roots_uses_configured_asset_roots(client):
    response = client.get("/api/roots")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["roots"][0]["key"] == "test"
    assert payload["roots"][0]["label"] == "Test Assets"


def test_settings_api_loads_and_saves_nested_model(client, tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"general": {"asset_roots": ["C:/Assets"]}, "viewer": {"density": "large", "preview": true}}', encoding="utf-8")
    monkeypatch.setattr(app_context, "SETTINGS_FILE", settings_file)
    monkeypatch.setitem(Settings.model_config, "json_file", settings_file)

    response = client.get("/api/settings")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["settings"]["general"]["asset_roots"] == ["C:/Assets"]
    assert payload["settings"]["viewer"] == {"density": "large", "preview": True}
    assert "general" in payload["schema"]["properties"]
    assert "viewer" in payload["schema"]["properties"]
    assert payload["schema"]["properties"]["general"]["title"] == "General"
    assert payload["schema"]["properties"]["viewer"]["title"] == "Viewer"

    update = client.put(
        "/api/settings",
        json={
            "general": {"asset_roots": [str(tmp_path / "assets")]},
            "viewer": {"density": "compact", "preview": False},
        },
    )

    assert update.status_code == 200
    saved = json.loads(settings_file.read_text(encoding="utf-8"))
    assert saved["general"]["asset_roots"] == [str(tmp_path / "assets")]
    assert saved["viewer"]["density"] == "compact"


def test_settings_updates_do_not_break_active_asset_requests(asset_root, tmp_path, monkeypatch):
    settings_file = tmp_path / "settings.json"
    settings_file.write_text(
        json.dumps(
            {
                "general": {"asset_roots": [str(asset_root)]},
                "viewer": {"density": "large", "preview": True},
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(app_context, "SETTINGS_FILE", settings_file)
    monkeypatch.setitem(Settings.model_config, "json_file", settings_file)

    (asset_root / "concurrent.png").write_bytes(make_png_bytes().getvalue())

    original_scan_assets = asset_api.scan_assets

    def delayed_scan_assets(*args, **kwargs):
        time.sleep(0.01)
        return original_scan_assets(*args, **kwargs)

    monkeypatch.setattr(asset_api, "scan_assets", delayed_scan_assets)

    failures: list[str] = []

    def read_worker() -> None:
        with server.app.test_client() as worker_client:
            for _ in range(20):
                response = worker_client.get("/api/assets/list?limit=10")
                if response.status_code != 200:
                    failures.append(f"asset list status {response.status_code}")

    def update_worker() -> None:
        with server.app.test_client() as worker_client:
            for index in range(20):
                response = worker_client.put(
                    "/api/settings",
                    json={
                        "general": {"asset_roots": [str(asset_root)]},
                        "viewer": {
                            "density": "compact" if index % 2 else "large",
                            "preview": bool(index % 2),
                        },
                    },
                )
                if response.status_code != 200:
                    failures.append(f"settings update status {response.status_code}")

    readers = [threading.Thread(target=read_worker, daemon=True) for _ in range(3)]
    writer = threading.Thread(target=update_worker, daemon=True)

    for thread in readers:
        thread.start()
    writer.start()
    for thread in readers:
        thread.join()
    writer.join()

    assert not failures


def test_packaged_settings_path_uses_appdata(tmp_path, monkeypatch):
    appdata_dir = tmp_path / "AppData" / "Roaming"
    monkeypatch.setenv("APPDATA", str(appdata_dir))
    monkeypatch.delenv(runtime_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.delenv(runtime_paths.SETTINGS_FILE_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.delattr(sys, "_MEIPASS", raising=False)

    assert runtime_paths.settings_file() == appdata_dir / runtime_paths.APP_NAME / "settings.json"


def test_packaged_first_launch_copies_bundled_settings(tmp_path, monkeypatch):
    appdata_dir = tmp_path / "AppData" / "Roaming"
    bundle_dir = tmp_path / "bundle"
    bundle_dir.mkdir()
    bundled_settings = bundle_dir / "settings.json"
    bundled_settings.write_text(
        '{"general": {"asset_roots": ["C:/Assets"]}, "viewer": {"density": "large", "preview": false}}\n',
        encoding="utf-8",
    )
    monkeypatch.setenv("APPDATA", str(appdata_dir))
    monkeypatch.delenv(runtime_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.delenv(runtime_paths.SETTINGS_FILE_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", str(bundle_dir), raising=False)

    settings_path = runtime_paths.ensure_settings_file()

    assert settings_path == appdata_dir / runtime_paths.APP_NAME / "settings.json"
    assert settings_path.read_text(encoding="utf-8") == bundled_settings.read_text(encoding="utf-8")


def test_packaged_report_cache_uses_appdata(tmp_path, monkeypatch):
    appdata_dir = tmp_path / "AppData" / "Roaming"
    asset_root_path = tmp_path / "assets"
    asset_root_path.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata_dir))
    monkeypatch.delenv(runtime_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    cache_path = Path(
        asset_viewer_metadata._report_cache_path(
            str(asset_root_path),
            "folder_stats.json",
            lambda path, root: os.path.commonpath([path, root]) == root,
        )
    )

    assert cache_path.parent.parent == appdata_dir / runtime_paths.APP_NAME / "cache" / "reports"
    assert asset_root_path not in cache_path.parents


def test_packaged_asset_index_cache_uses_appdata(tmp_path, monkeypatch):
    appdata_dir = tmp_path / "AppData" / "Roaming"
    asset_root_path = tmp_path / "assets"
    asset_root_path.mkdir()
    monkeypatch.setenv("APPDATA", str(appdata_dir))
    monkeypatch.delenv(runtime_paths.DATA_DIR_ENV, raising=False)
    monkeypatch.setattr(sys, "frozen", True, raising=False)

    cache_path = runtime_paths.asset_index_cache_file(str(asset_root_path))

    assert cache_path.parent.parent == appdata_dir / runtime_paths.APP_NAME / "cache" / "asset-indexes"
    assert asset_root_path not in cache_path.parents


def test_asset_list_filters_sorts_and_paginates(client, asset_root):
    (asset_root / "b.png").write_bytes(make_png_bytes().getvalue())
    (asset_root / "a.txt").write_text("not an image", encoding="utf-8")

    response = client.get("/api/assets/list?root=test&ext=.png&limit=1&sort_by=name&sort_dir=desc")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["name"] for item in payload["assets"]] == ["b.png"]


def test_asset_list_filters_mp4_and_sorts_by_extension(client, asset_root):
    (asset_root / "clip.mp4").write_bytes(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00")
    (asset_root / "animation.gif").write_bytes(b"GIF89a")
    (asset_root / "still.png").write_bytes(make_png_bytes().getvalue())

    filtered = client.get("/api/assets/list?root=test&ext=.mp4&refresh_index=true")
    sorted_response = client.get("/api/assets/list?root=test&sort_by=extension&sort_dir=asc")

    assert [item["name"] for item in filtered.get_json()["assets"]] == ["clip.mp4"]
    assert [item["extension"] for item in sorted_response.get_json()["assets"]] == [
        ".gif",
        ".mp4",
        ".png",
    ]


def test_asset_list_creates_and_uses_index_cache(client, asset_root):
    (asset_root / "first.png").write_bytes(make_png_bytes().getvalue())

    first = client.get("/api/assets/list?root=test&limit=10&sort_by=name&sort_dir=asc")

    assert first.status_code == 200
    first_payload = first.get_json()
    assert first_payload["cache"] == {"used": False, "indexed": True}
    assert [item["name"] for item in first_payload["assets"]] == ["first.png"]
    assert (asset_root / ".asset_viewer_reports" / "asset_index.sqlite").exists()

    (asset_root / "second.png").write_bytes(make_png_bytes().getvalue())
    cached = client.get("/api/assets/list?root=test&limit=10&sort_by=name&sort_dir=asc")

    assert cached.status_code == 200
    cached_payload = cached.get_json()
    assert cached_payload["cache"] == {"used": True, "indexed": True}
    assert [item["name"] for item in cached_payload["assets"]] == ["first.png"]

    refreshed = client.get("/api/assets/list?root=test&limit=10&sort_by=name&sort_dir=asc&refresh_index=true")

    assert refreshed.status_code == 200
    refreshed_payload = refreshed.get_json()
    assert refreshed_payload["cache"] == {"used": False, "indexed": True}
    assert [item["name"] for item in refreshed_payload["assets"]] == ["first.png", "second.png"]


def test_asset_list_filters_by_folder(client, asset_root):
    nested = asset_root / "Batch A" / "Nested"
    nested.mkdir(parents=True)
    sibling = asset_root / "Batch B"
    sibling.mkdir()
    (asset_root / "root.png").write_bytes(make_png_bytes().getvalue())
    (nested / "nested.png").write_bytes(make_png_bytes().getvalue())
    (sibling / "sibling.png").write_bytes(make_png_bytes().getvalue())

    response = client.get("/api/assets/list?root=test&folder=Batch%20A&sort_by=name&sort_dir=asc")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["assets"]] == ["nested.png"]


def test_asset_folders_lists_root_and_subfolders(client, asset_root):
    (asset_root / "Batch A" / "Nested").mkdir(parents=True)
    (asset_root / "Batch B").mkdir()
    (asset_root / ".asset_viewer_reports").mkdir()
    (asset_root / ".asset_viewer_reports" / "asset_index.sqlite").write_text("", encoding="utf-8")
    (asset_root / "top.png").write_bytes(make_png_bytes().getvalue())
    (asset_root / "Batch A" / "a.png").write_bytes(make_png_bytes().getvalue())
    (asset_root / "Batch A" / "Nested" / "n1.png").write_bytes(make_png_bytes().getvalue())
    (asset_root / "Batch A" / "Nested" / "n2.png").write_bytes(make_png_bytes().getvalue())

    response = client.get("/api/assets/folders?root=test")

    assert response.status_code == 200
    payload = response.get_json()
    # file_count is recursive and ignores excluded report/trash folders.
    assert payload["folders"] == [
        {"path": "", "label": "root", "depth": 0, "file_count": 4},
        {"path": "Batch A", "label": "Batch A", "depth": 1, "file_count": 3},
        {"path": os.path.join("Batch A", "Nested"), "label": "Nested", "depth": 2, "file_count": 2},
        {"path": "Batch B", "label": "Batch B", "depth": 1, "file_count": 0},
    ]


def test_asset_list_reports_total_matches(client, asset_root):
    for index in range(5):
        (asset_root / f"item_{index}.png").write_bytes(make_png_bytes().getvalue())

    response = client.get("/api/assets/list?root=test&limit=2&offset=0")

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["assets"]) == 2
    assert payload["total"] == 5


def test_create_folder_under_selected_folder(client, asset_root):
    (asset_root / "Parent").mkdir()

    response = client.post(
        "/api/assets/folders",
        json={"root": "test", "parent": "Parent", "name": "New Batch"},
    )

    assert response.status_code == 201
    assert response.get_json()["folder"]["path"] == "Parent/New Batch"
    assert (asset_root / "Parent" / "New Batch").is_dir()


@pytest.mark.parametrize("name", ["../escape", ".asset_viewer_reports", ".."])
def test_create_folder_rejects_unsafe_names(client, asset_root, name):
    response = client.post(
        "/api/assets/folders",
        json={"root": "test", "parent": "", "name": name},
    )

    assert response.status_code == 400


def test_move_selected_assets_updates_files_and_index(client, asset_root):
    destination = asset_root / "Sorted"
    destination.mkdir()
    first = asset_root / "first.png"
    second = asset_root / "second.png"
    first.write_bytes(make_png_bytes().getvalue())
    second.write_bytes(make_png_bytes().getvalue())
    client.get("/api/assets/list?root=test")

    response = client.post(
        "/api/assets/move",
        json={"root": "test", "folder": "Sorted", "paths": [str(first), str(second)]},
    )

    assert response.status_code == 200
    payload = response.get_json()
    assert len(payload["moved"]) == 2
    assert not first.exists()
    assert (destination / "first.png").exists()
    listed = client.get("/api/assets/list?root=test&folder=Sorted&sort_by=name&sort_dir=asc").get_json()
    assert [item["name"] for item in listed["assets"]] == ["first.png", "second.png"]


def test_move_asset_renames_on_collision(client, asset_root):
    destination = asset_root / "Sorted"
    destination.mkdir()
    source = asset_root / "same.png"
    source.write_bytes(make_png_bytes().getvalue())
    (destination / "same.png").write_bytes(make_png_bytes().getvalue())

    response = client.post(
        "/api/assets/move",
        json={"root": "test", "folder": "Sorted", "paths": [str(source)]},
    )

    assert response.status_code == 200
    assert (destination / "same_1.png").exists()


def test_asset_list_defaults_to_most_recent_first(client, asset_root):
    older = asset_root / "older.png"
    newer = asset_root / "newer.png"
    older.write_bytes(make_png_bytes().getvalue())
    newer.write_bytes(make_png_bytes().getvalue())
    os.utime(older, (1000, 1000))
    os.utime(newer, (2000, 2000))

    response = client.get("/api/assets/list?root=test&limit=2")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["assets"]] == ["newer.png", "older.png"]


def test_asset_list_excludes_report_cache_files(client, asset_root):
    (asset_root / "visible.png").write_bytes(make_png_bytes().getvalue())
    report_dir = asset_root / ".asset_viewer_reports"
    report_dir.mkdir()
    (report_dir / "folder_stats.json").write_text('{"total_files": 1}', encoding="utf-8")
    (report_dir / "metadata_report.json").write_text('{"total_assets": 1}', encoding="utf-8")

    response = client.get("/api/assets/list?root=test&limit=10&sort_by=name")

    assert response.status_code == 200
    assert [item["name"] for item in response.get_json()["assets"]] == ["visible.png"]


def test_asset_list_includes_metadata_badges(client, asset_root):
    image_path = asset_root / "metadata.png"
    image_path.write_bytes(
        make_png_with_text_chunks({
            "bubba_metadata": '{"seed":"1"}',
            "workflow": "{}",
            "parameters": "Steps: 20",
        }).getvalue()
    )

    response = client.get("/api/assets/list?root=test&limit=1")

    assert response.status_code == 200
    badges = response.get_json()["assets"][0]["metadata_badges"]
    assert badges == [
        {"key": "bubba_metadata", "label": "Bubba"},
        {"key": "workflow", "label": "Workflow"},
        {"key": "parameters", "label": "Params"},
    ]


def test_asset_list_filters_metadata_badges(client, asset_root):
    (asset_root / "bubba.png").write_bytes(make_png_with_text_chunks({"bubba_metadata": '{"seed":"1"}'}).getvalue())
    (asset_root / "plain.png").write_bytes(make_png_bytes().getvalue())

    bubba = client.get("/api/assets/list?root=test&metadata_badges=bubba_metadata&sort_by=name")
    missing = client.get("/api/assets/list?root=test&metadata_badges=no_tracked_metadata&sort_by=name")

    assert [item["name"] for item in bubba.get_json()["assets"]] == ["bubba.png"]
    assert [item["name"] for item in missing.get_json()["assets"]] == ["plain.png"]


def test_metadata_health_report_counts_tracked_keys(client, asset_root):
    (asset_root / "full.png").write_bytes(
        make_png_with_text_chunks({
            "bubba_metadata": '{"seed":"1"}',
            "workflow": "{}",
            "parameters": "Steps: 20",
        }).getvalue()
    )
    (asset_root / "bad.png").write_bytes(make_png_with_text_chunks({"bubba_metadata": "not json"}).getvalue())
    (asset_root / "plain.png").write_bytes(make_png_bytes().getvalue())

    response = client.get("/api/assets/metadata/health?root=test")

    assert response.status_code == 200
    stats = response.get_json()["stats"]
    assert stats["total_assets"] == 3
    assert stats["bubba_metadata"] == 2
    assert stats["workflow"] == 1
    assert stats["parameters"] == 1
    assert stats["no_tracked_metadata"] == 1
    assert stats["invalid_bubba_metadata"] == 1


def test_folder_stats_counts_files_and_metadata(client, asset_root):
    (asset_root / "full.png").write_bytes(
        make_png_with_text_chunks({
            "bubba_metadata": '{"seed":"1"}',
            "workflow": "{}",
            "parameters": "Steps: 20",
        }).getvalue()
    )
    (asset_root / "model.safetensors").write_text("model", encoding="utf-8")
    (asset_root / "notes.txt").write_text("notes", encoding="utf-8")

    response = client.get("/api/assets/stats?root=test")

    assert response.status_code == 200
    stats = response.get_json()["stats"]
    assert stats["total_files"] == 3
    assert stats["image_files"] == 1
    assert stats["model_files"] == 1
    assert stats["other_files"] == 1
    assert stats["bubba_metadata"] == 1
    assert stats["workflow"] == 1
    assert stats["parameters"] == 1


def test_folder_stats_uses_persisted_report_until_refresh(client, asset_root):
    (asset_root / "one.png").write_bytes(make_png_bytes().getvalue())

    first = client.get("/api/assets/stats?root=test&refresh=true")

    assert first.status_code == 200
    first_payload = first.get_json()
    assert first_payload["cached"] is False
    assert first_payload["stats"]["total_files"] == 1
    assert "generated_at" in first_payload["stats"]

    cache_path = asset_root / ".asset_viewer_reports" / "folder_stats.json"
    assert cache_path.exists()

    (asset_root / "two.png").write_bytes(make_png_bytes().getvalue())
    cached = client.get("/api/assets/stats?root=test")

    assert cached.status_code == 200
    cached_payload = cached.get_json()
    assert cached_payload["cached"] is True
    assert cached_payload["stats"]["total_files"] == 1

    refreshed = client.get("/api/assets/stats?root=test&refresh=true")

    assert refreshed.status_code == 200
    refreshed_payload = refreshed.get_json()
    assert refreshed_payload["cached"] is False
    assert refreshed_payload["stats"]["total_files"] == 2


def test_metadata_report_can_load_cache_without_scanning(client, asset_root):
    (asset_root / "full.png").write_bytes(make_png_with_text_chunks({"bubba_metadata": '{"seed":"1"}'}).getvalue())

    missing = client.get("/api/assets/metadata/health?root=test&cache_only=true")

    assert missing.status_code == 200
    assert missing.get_json()["stats"] is None

    first = client.get("/api/assets/metadata/health?root=test&refresh=true")

    assert first.status_code == 200
    first_payload = first.get_json()
    assert first_payload["cached"] is False
    assert first_payload["stats"]["total_assets"] == 1
    assert "generated_at" in first_payload["stats"]

    (asset_root / "plain.png").write_bytes(make_png_bytes().getvalue())
    cached = client.get("/api/assets/metadata/health?root=test&cache_only=true")

    assert cached.status_code == 200
    cached_payload = cached.get_json()
    assert cached_payload["cached"] is True
    assert cached_payload["stats"]["total_assets"] == 1


def test_repair_metadata_reconstructs_bubba_metadata(client, asset_root):
    image_path = asset_root / "repairable.png"
    image_path.write_bytes(make_png_with_repairable_prompt().getvalue())

    response = client.post("/api/assets/metadata/repair", json={"path": str(image_path)})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["result"]["repaired"] is True
    repaired = payload["result"]["metadata"]
    assert repaired["model_name"] == "model.safetensors"
    assert repaired["seed"] == 12345
    assert repaired["steps"] == 20
    assert repaired["cfg"] == 5.5
    assert repaired["sampler_name"] == "dpmpp_2m_sde"
    assert repaired["scheduler"] == "karras"
    assert repaired["denoise"] == 0.75
    assert repaired["positive_prompt"] == "positive, glowing"
    assert repaired["negative_prompt"] == "negative"
    assert repaired["loras"] == ["NeonLineart:0.50"]
    assert {"key": "bubba_metadata", "label": "Bubba"} in payload["asset"]["metadata_badges"]

    with Image.open(image_path) as image:
        stored = json.loads(image.info["bubba_metadata"])
    assert stored["seed"] == 12345
    assert "prompt" in Image.open(image_path).info


@pytest.mark.parametrize(
    "query",
    [
        "limit=abc",
        "offset=abc",
        "min_size_bytes=abc",
        "max_size_bytes=abc",
        "modified_after_ts=abc",
    ],
)
def test_asset_list_rejects_invalid_numeric_params(client, query):
    response = client.get(f"/api/assets/list?root=test&{query}")

    assert response.status_code == 400


def test_duplicate_scan_finds_exact_pixel_and_near_matches(client, asset_root):
    exact_bytes = make_png_bytes((255, 0, 0, 255)).getvalue()
    (asset_root / "exact-a.png").write_bytes(exact_bytes)
    (asset_root / "exact-b.png").write_bytes(exact_bytes)

    (asset_root / "pixel-a.png").write_bytes(make_png_with_metadata('{"seed": "1"}').getvalue())
    (asset_root / "pixel-b.png").write_bytes(make_png_with_metadata('{"seed": "2"}').getvalue())

    (asset_root / "near-a.png").write_bytes(make_png_bytes((20, 20, 20, 255)).getvalue())
    (asset_root / "near-b.png").write_bytes(make_png_bytes((24, 24, 24, 255)).getvalue())

    response = client.get("/api/assets/duplicates?root=test&include_near=true&near_threshold=2")

    assert response.status_code == 200
    payload = response.get_json()
    kinds = {group["kind"] for group in payload["groups"]}
    assert {"exact", "pixel", "near"}.issubset(kinds)
    assert payload["summary"]["exact_groups"] >= 1
    assert payload["summary"]["pixel_groups"] >= 1
    assert payload["summary"]["near_groups"] >= 1

    exact_group = next(group for group in payload["groups"] if group["kind"] == "exact")
    assert {asset["name"] for asset in exact_group["assets"]} == {"exact-a.png", "exact-b.png"}


def test_duplicate_scan_reuses_cached_content_hashes(client, asset_root, monkeypatch):
    exact_bytes = make_png_bytes((255, 0, 0, 255)).getvalue()
    (asset_root / "cached-a.png").write_bytes(exact_bytes)
    (asset_root / "cached-b.png").write_bytes(exact_bytes)

    first = client.get("/api/assets/duplicates?root=test")

    assert first.status_code == 200
    assert first.get_json()["summary"]["exact_groups"] == 1

    index_path = asset_root / ".asset_viewer_reports" / "asset_index.sqlite"
    with sqlite3.connect(index_path) as connection:
        cached_hash_count = connection.execute(
            "SELECT COUNT(*) FROM assets WHERE content_hash IS NOT NULL"
        ).fetchone()[0]
    assert cached_hash_count == 2

    monkeypatch.setattr(asset_viewer_duplicates, "_sha256_file", lambda *args, **kwargs: None)
    second = client.get("/api/assets/duplicates?root=test")

    assert second.status_code == 200
    assert second.get_json()["summary"]["exact_groups"] == 1


def test_duplicate_scan_caches_large_dhash_values(client, asset_root, monkeypatch):
    (asset_root / "large-dhash-a.png").write_bytes(make_png_bytes((20, 20, 20, 255)).getvalue())
    (asset_root / "large-dhash-b.png").write_bytes(make_png_bytes((24, 24, 24, 255)).getvalue())
    large_dhash = 2**63 + 123

    monkeypatch.setattr(asset_viewer_duplicates, "_dhash", lambda *args, **kwargs: large_dhash)

    response = client.get("/api/assets/duplicates?root=test&include_near=true&near_threshold=2")

    assert response.status_code == 200
    index_path = asset_root / ".asset_viewer_reports" / "asset_index.sqlite"
    with sqlite3.connect(index_path) as connection:
        stored_dhashes = [
            row[0]
            for row in connection.execute(
                "SELECT dhash FROM assets WHERE dhash IS NOT NULL ORDER BY name"
            ).fetchall()
        ]
    assert stored_dhashes == [str(large_dhash), str(large_dhash)]


def test_duplicate_scan_rejects_invalid_numeric_params(client):
    response = client.get("/api/assets/duplicates?root=test&near_threshold=bad")

    assert response.status_code == 400


def test_duplicate_scan_stream_reports_progress_and_result(client, asset_root):
    exact_bytes = make_png_bytes((255, 0, 0, 255)).getvalue()
    (asset_root / "stream-a.png").write_bytes(exact_bytes)
    (asset_root / "stream-b.png").write_bytes(exact_bytes)

    response = client.get("/api/assets/duplicates/stream?root=test")

    assert response.status_code == 200
    body = response.get_data(as_text=True)
    assert '"type": "task"' in body
    assert '"type": "progress"' in body
    assert '"type": "result"' in body
    assert '"exact_groups": 1' in body


def test_duplicate_scan_task_status_reports_completion(client, asset_root):
    exact_bytes = make_png_bytes((255, 0, 0, 255)).getvalue()
    (asset_root / "status-a.png").write_bytes(exact_bytes)
    (asset_root / "status-b.png").write_bytes(exact_bytes)

    response = client.get("/api/assets/duplicates/stream?root=test", buffered=False)
    first_chunk = next(response.response).decode("utf-8")
    task_payload = json.loads(first_chunk)
    task_id = task_payload["task"]["task_id"]

    body = b"".join(response.response).decode("utf-8")
    assert '"type": "result"' in body

    status_response = client.get(f"/api/assets/duplicates/tasks/{task_id}")

    assert status_response.status_code == 200
    status_payload = status_response.get_json()
    assert status_payload["task_id"] == task_id
    assert status_payload["status"] == "completed"
    assert status_payload["result"]["summary"]["exact_groups"] == 1


def test_duplicate_scan_task_cancel_endpoint_stops_running_scan(client, asset_root, monkeypatch):
    (asset_root / "cancel-a.png").write_bytes(make_png_bytes().getvalue())
    (asset_root / "cancel-b.png").write_bytes(make_png_bytes().getvalue())

    from services.duplicate_scan_tasks import DuplicateScanCancelled

    def slow_scan_duplicate_assets(*args, **kwargs):
        progress_callback = kwargs.get("progress_callback")
        cancel_check = kwargs.get("cancel_check")
        for index in range(100):
            if cancel_check and cancel_check():
                raise DuplicateScanCancelled("cancelled")
            if progress_callback:
                progress_callback({"stage": "hashing", "completed": index, "total": 100, "percent": index, "message": f"step {index}"})
            time.sleep(0.01)
        return {
            "groups": [],
            "summary": {
                "groups": 0,
                "assets": 0,
                "exact_groups": 0,
                "pixel_groups": 0,
                "near_groups": 0,
                "scanned_assets": 0,
                "near_enabled": False,
            },
        }

    monkeypatch.setattr(asset_api, "scan_duplicate_assets", slow_scan_duplicate_assets)

    response = client.get("/api/assets/duplicates/stream?root=test", buffered=False)
    first_chunk = next(response.response).decode("utf-8")
    task_payload = json.loads(first_chunk)
    task_id = task_payload["task"]["task_id"]

    cancel_response = client.post(f"/api/assets/duplicates/tasks/{task_id}/cancel")
    assert cancel_response.status_code == 200
    assert cancel_response.get_json()["cancel_requested"] is True

    body = b"".join(response.response).decode("utf-8")
    assert '"type": "cancelled"' in body or '"type": "error"' in body

    status_response = client.get(f"/api/assets/duplicates/tasks/{task_id}")
    assert status_response.status_code == 200
    assert status_response.get_json()["status"] == "cancelled"


def test_details_and_thumbnail_for_image(client, asset_root):
    image_path = asset_root / "sample.png"
    image_path.write_bytes(make_png_bytes().getvalue())

    details = client.get("/api/assets/details", query_string={"path": str(image_path)})
    thumb = client.get("/api/assets/thumb", query_string={"path": str(image_path), "size": "64"})

    assert details.status_code == 200
    assert details.get_json()["asset"]["name"] == "sample.png"
    assert thumb.status_code == 200
    assert thumb.mimetype == "image/png"


def test_open_folder_resolves_file_within_root(client, asset_root, monkeypatch):
    image_path = asset_root / "sample.png"
    image_path.write_bytes(make_png_bytes().getvalue())
    opened = []

    monkeypatch.setattr(server.os, "startfile", opened.append, raising=False)

    response = client.post("/api/assets/open-folder", json={"path": str(image_path)})

    assert response.status_code == 200
    assert opened == [str(asset_root)]


def test_details_normalizes_bubba_nodes_metadata(client, asset_root):
    image_path = asset_root / "bubba.png"
    image_path.write_bytes(
        make_png_with_metadata(
            (
                '{"model_name":" model.safetensors ","clip_skip":"2","sampler_time_seconds":"1.25",'
                '"steps":"20","cfg":"7.5","sampler_name":"euler","scheduler":"karras",'
                '"denoise":"0.8","seed":"42","positive_prompt":" prompt ",'
                '"negative_prompt":" negative ","loras":"a.safetensors, b.safetensors",'
                '"lora_strengths":[[0.8,0.5]],"vae_name":"vae.safetensors","width":"832","height":1216,'
                '"notes":" note ","save_prefix":"Character/Scene","filepath":"Character/Scene"}'
            )
        ).getvalue()
    )

    response = client.get("/api/assets/details", query_string={"path": str(image_path)})

    assert response.status_code == 200
    embedded = response.get_json()["asset"]["metadata"]["metadata"]
    bubba = embedded["bubba_metadata"]
    assert bubba == {
        "model_name": "model.safetensors",
        "clip_skip": 2,
        "sampler_time_seconds": 1.25,
        "steps": 20,
        "cfg": 7.5,
        "sampler_name": "euler",
        "scheduler": "karras",
        "denoise": 0.8,
        "seed": 42,
        "positive_prompt": "prompt",
        "negative_prompt": "negative",
        "loras": ["a.safetensors", "b.safetensors"],
        "lora_strengths": [[0.8, 0.5], [1.0, 1.0]],
        "vae_name": "vae.safetensors",
        "clip_name": "",
        "width": 832,
        "height": 1216,
        "notes": "note",
        "save_prefix": "Character/Scene",
        "filepath": "Character/Scene",
    }

    has_generation = client.get("/api/assets/list?root=test&metadata_mode=has_generation")
    assert has_generation.status_code == 200
    assert [item["name"] for item in has_generation.get_json()["assets"]] == ["bubba.png"]


def test_file_access_rejects_paths_outside_roots(client, tmp_path):
    outside = tmp_path / "outside.txt"
    outside.write_text("secret", encoding="utf-8")

    response = client.get("/api/assets/file", query_string={"path": str(outside)})

    assert response.status_code == 400


def test_upload_rejects_non_images_and_delete_removes_uploaded_image(client, asset_root):
    invalid = {
        "files": (BytesIO(b"not an image"), "bad.png"),
    }
    invalid_response = client.post("/bubba/assets/upload?root=test", data=invalid, content_type="multipart/form-data")

    assert invalid_response.status_code == 200
    assert invalid_response.get_json()["uploaded"] == []
    assert invalid_response.get_json()["skipped"][0]["error"] == "Invalid image file"

    valid = {
        "files": (make_png_bytes(), "upload.png"),
    }
    upload_response = client.post("/bubba/assets/upload?root=test", data=valid, content_type="multipart/form-data")

    assert upload_response.status_code == 200
    uploaded = upload_response.get_json()["uploaded"]
    assert uploaded[0]["name"] == "upload.png"
    assert (asset_root / "upload.png").exists()

    delete_response = client.post("/bubba/assets/delete", json={"path": uploaded[0]["path"]})

    assert delete_response.status_code == 200
    assert delete_response.get_json()["deleted"] == [uploaded[0]["path"]]
    assert not (asset_root / "upload.png").exists()


def test_upload_accepts_mp4_media(client, asset_root):
    mp4 = {
        "files": (
            BytesIO(b"\x00\x00\x00\x18ftypisom\x00\x00\x00\x00"),
            "clip.mp4",
        )
    }

    response = client.post(
        "/bubba/assets/upload?root=test",
        data=mp4,
        content_type="multipart/form-data",
    )

    assert response.status_code == 200
    assert response.get_json()["uploaded"][0]["extension"] == ".mp4"
    assert (asset_root / "clip.mp4").exists()


def test_delete_safe_mode_moves_file_to_trash(client, asset_root):
    image_path = asset_root / "safe.png"
    image_path.write_bytes(make_png_bytes().getvalue())

    response = client.post("/bubba/assets/delete", json={"path": str(image_path), "safe_delete": True})

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["deleted"] == [str(image_path)]
    assert payload["moved"][0]["destination"]
    assert not image_path.exists()
    assert os.path.exists(payload["moved"][0]["destination"])


def test_undo_restores_safe_deleted_file_to_original_path(client, asset_root):
    image_path = asset_root / "Batch" / "keep.png"
    image_path.parent.mkdir()
    image_path.write_bytes(make_png_bytes().getvalue())
    moved = client.post("/bubba/assets/delete", json={"path": str(image_path), "safe_delete": True}).get_json()["moved"]

    response = client.post("/api/assets/restore", json={"items": moved})

    assert response.status_code == 200
    assert response.get_json()["errors"] == []
    assert image_path.exists()
    assert not os.path.exists(moved[0]["destination"])


def test_restore_rejects_sources_outside_trash(client, asset_root):
    outside = asset_root / "not_trash.png"
    outside.write_bytes(make_png_bytes().getvalue())

    response = client.post(
        "/api/assets/restore",
        json={"items": [{"path": str(asset_root / "copy.png"), "destination": str(outside)}]},
    )

    assert response.status_code == 200
    assert response.get_json()["restored"] == []
    assert outside.exists()
    assert not (asset_root / "copy.png").exists()


def test_favorites_flag_filter_and_follow_moves(client, asset_root):
    (asset_root / "Dest").mkdir()
    for name in ("a.png", "b.png", "c.png"):
        (asset_root / name).write_bytes(make_png_bytes().getvalue())
    client.get("/api/assets/list?root=test")  # build the index
    starred = str(asset_root / "b.png")

    assert client.post("/api/assets/favorite", json={"paths": [starred], "favorite": True}).status_code == 200

    listed = client.get("/api/assets/list?root=test&sort_by=name&sort_dir=asc").get_json()["assets"]
    assert [item.get("favorite", False) for item in listed] == [False, True, False]
    favorites = client.get("/api/assets/list?root=test&favorites=1").get_json()
    assert [item["name"] for item in favorites["assets"]] == ["b.png"]
    assert favorites["total"] == 1
    assert client.get(f"/api/assets/details?path={starred}").get_json()["asset"]["favorite"] is True

    client.post("/api/assets/move", json={"root": "test", "folder": "Dest", "paths": [starred]})
    moved = client.get("/api/assets/list?root=test&favorites=1").get_json()["assets"]
    assert [item["relative_path"] for item in moved] == [os.path.join("Dest", "b.png")]

    client.post("/api/assets/favorite", json={"paths": [moved[0]["path"]], "favorite": False})
    assert client.get("/api/assets/list?root=test&favorites=1").get_json()["assets"] == []


def test_tags_are_paged_and_search_normalizes_spaces(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    danbooru_csv = source_dir / "danbooru_tags_pt20_202605.csv"
    danbooru_csv.write_text(
        "name,category,count,aliases\n"
        "red_hair,0,10,red hair|scarlet_hair\n"
        "blue_hair,0,7,azure hair\n",
        encoding="utf-8",
    )
    e621_csv = source_dir / "e621_tags_pt20_202605.csv"
    e621_csv.write_text(
        "name,category,count,aliases\n"
        "solo,1,99,alone\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(tag_api, "frontend_root", lambda: source_dir)
    monkeypatch.setattr(tag_api, "user_data_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(tag_api, "_download_missing_source_tag_lists", lambda: None)
    monkeypatch.setattr(tag_api, "_tag_list_ready", False)
    server.app.config.update(TESTING=True)

    with server.app.test_client() as test_client:
        page = test_client.get("/api/tags?limit=2")
        search = test_client.get("/api/tags?q=red%20hair")
        invalid = test_client.get("/api/tags?limit=bad")

    assert page.status_code == 200
    assert page.get_json()["total"] == 3
    assert [tag["name"] for tag in page.get_json()["tags"]] == ["red_hair", "blue_hair"]
    assert search.status_code == 200
    assert [tag["name"] for tag in search.get_json()["tags"]] == ["red_hair"]
    assert invalid.status_code == 400


def test_tags_can_load_danbooru_and_e621_source_csvs(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    danbooru_csv = source_dir / "danbooru_tags_pt20_202605.csv"
    danbooru_csv.write_text(
        "name,category,count,aliases\n"
        "red_hair,0,10,scarlet_hair\n",
        encoding="utf-8",
    )
    e621_csv = source_dir / "e621_tags_pt20_202605.csv"
    e621_csv.write_text(
        "name,category,count,aliases\n"
        "canine,1,22,dog\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(tag_api, "frontend_root", lambda: source_dir)
    monkeypatch.setattr(tag_api, "user_data_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(tag_api, "_download_missing_source_tag_lists", lambda: None)
    monkeypatch.setattr(tag_api, "_tag_list_ready", False)
    server.app.config.update(TESTING=True)

    with server.app.test_client() as test_client:
        all_tags = test_client.get("/api/tags?limit=10")
        general_tags = test_client.get("/api/tags?category=general")
        artist_tags = test_client.get("/api/tags?category=artist")

    assert all_tags.status_code == 200
    payload = all_tags.get_json()
    assert payload["total"] == 2
    assert {tag["name"] for tag in payload["tags"]} == {"red_hair", "canine"}
    assert {tag["source"] for tag in payload["tags"]} == {"danbooru", "e621"}
    assert set(payload["categories"]) == {"general", "artist"}

    assert general_tags.status_code == 200
    assert [tag["name"] for tag in general_tags.get_json()["tags"]] == ["red_hair"]

    assert artist_tags.status_code == 200
    assert [tag["name"] for tag in artist_tags.get_json()["tags"]] == ["canine"]


def test_tags_can_parse_headerless_pt20_source_csvs(tmp_path, monkeypatch):
    source_dir = tmp_path / "sources"
    source_dir.mkdir()
    danbooru_csv = source_dir / "danbooru_2026-04-01_pt20-ia-dd.csv"
    danbooru_csv.write_text(
        "1girl,0,7641780,sole_female\n"
        "highres,5,7237856,high_resolution\n",
        encoding="utf-8",
    )
    e621_csv = source_dir / "e621_2026-04-01_pt20-ia-ed.csv"
    e621_csv.write_text(
        "anthro,0,4156082,anthropomorphic\n"
        "male,0,3093404,boy\n",
        encoding="utf-8",
    )

    monkeypatch.setattr(tag_api, "frontend_root", lambda: source_dir)
    monkeypatch.setattr(tag_api, "user_data_dir", lambda: tmp_path / "appdata")
    monkeypatch.setattr(tag_api, "_download_missing_source_tag_lists", lambda: None)
    monkeypatch.setattr(tag_api, "_tag_list_ready", False)
    server.app.config.update(TESTING=True)

    with server.app.test_client() as test_client:
        response = test_client.get("/api/tags?limit=10")

    assert response.status_code == 200
    payload = response.get_json()
    assert payload["total"] == 4
    assert {tag["name"] for tag in payload["tags"]} == {"1girl", "highres", "anthro", "male"}
    assert set(payload["categories"]) == {"general", "meta"}
