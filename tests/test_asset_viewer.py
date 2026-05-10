from __future__ import annotations

from io import BytesIO
import json
import os
import sys

import pytest
from PIL import Image
from PIL.PngImagePlugin import PngInfo

sys.path.insert(0, "backend")

import server  # noqa: E402
from asset_viewer import AssetRoot  # noqa: E402


@pytest.fixture()
def asset_root(tmp_path, monkeypatch):
    root = tmp_path / "assets"
    root.mkdir()
    monkeypatch.setattr(
        server,
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
    monkeypatch.setattr(server, "SETTINGS_FILE", settings_file)
    monkeypatch.setitem(server.Settings.model_config, "json_file", settings_file)

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


def test_asset_list_filters_sorts_and_paginates(client, asset_root):
    (asset_root / "b.png").write_bytes(make_png_bytes().getvalue())
    (asset_root / "a.txt").write_text("not an image", encoding="utf-8")

    response = client.get("/api/assets/list?root=test&ext=.png&limit=1&sort_by=name&sort_dir=desc")

    assert response.status_code == 200
    payload = response.get_json()
    assert [item["name"] for item in payload["assets"]] == ["b.png"]


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
    assert '"type": "progress"' in body
    assert '"type": "result"' in body
    assert '"exact_groups": 1' in body


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
                '"filepath":"Character/Scene"}'
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


def test_tags_are_paged_and_search_normalizes_spaces(tmp_path, monkeypatch):
    tag_csv = tmp_path / "tags.csv"
    tag_csv.write_text(
        "name,category,count,aliases\n"
        "red_hair,0,10,red hair|scarlet_hair\n"
        "blue_hair,0,7,azure hair\n"
        "solo,0,99,alone\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(server, "TAG_LIST_LOCAL", tag_csv)
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
