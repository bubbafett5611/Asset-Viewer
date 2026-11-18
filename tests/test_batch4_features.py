from __future__ import annotations

import json
from io import BytesIO

from PIL import Image
from PIL.PngImagePlugin import PngInfo

# test_asset_viewer puts backend/ on sys.path, so import it before the backend modules.
from test_asset_viewer import asset_root, client  # noqa: F401, I001  (pytest fixtures)
from services.copy_formats import a1111_parameters, copy_formats_from_png_info, lora_stack  # noqa: E402


def _png(path, color=(200, 30, 30), size=(64, 64), **chunks) -> None:
    info = PngInfo()
    for key, value in chunks.items():
        info.add_text(key, value if isinstance(value, str) else json.dumps(value))
    buffer = BytesIO()
    Image.new("RGB", size, color).save(buffer, format="PNG", pnginfo=info)
    path.write_bytes(buffer.getvalue())


BUBBA = {
    "model_name": "rimix",
    "seed": 42,
    "steps": 30,
    "cfg": 5.5,
    "sampler_name": "euler_ancestral",
    "scheduler": "karras",
    "positive_prompt": "1girl, red hair",
    "negative_prompt": "lowres",
    "width": 832,
    "height": 1216,
    "loras": ["styles\\Detail_Tweaker.safetensors", "chars/hero.safetensors"],
    "lora_strengths": [[0.8, 0.8], [1.0, 0.5]],
}


# ---- 1. copy formats -------------------------------------------------------


def test_lora_stack_strips_folders_and_orders_te_then_unet():
    assert lora_stack(BUBBA["loras"], BUBBA["lora_strengths"]) == "<lora:Detail_Tweaker:0.8> <lora:hero:0.5:1>"
    assert lora_stack(["a.safetensors"], []) == "<lora:a:1>"


def test_a1111_parameters_block():
    text = a1111_parameters(BUBBA)
    lines = text.splitlines()
    assert lines[0] == "1girl, red hair <lora:Detail_Tweaker:0.8> <lora:hero:0.5:1>"
    assert lines[1] == "Negative prompt: lowres"
    assert lines[2] == (
        "Steps: 30, Sampler: euler_ancestral_karras, CFG scale: 5.5, Seed: 42, Size: 832x1216, Model: rimix"
    )
    assert a1111_parameters({}) == ""


def test_copy_formats_prefer_bubba_and_fall_back_to_parameters_chunk():
    workflow = {"nodes": [{"id": 1}], "links": []}
    formats = copy_formats_from_png_info({"workflow": json.dumps(workflow), "bubba_metadata": json.dumps(BUBBA)})
    assert json.loads(formats["workflow"]) == workflow
    assert formats["lora_stack"].startswith("<lora:Detail_Tweaker:0.8>")
    only_a1111 = copy_formats_from_png_info({"parameters": "cat <lora:fur:0.7>\nSteps: 20"})
    assert only_a1111 == {"workflow": "", "parameters": "cat <lora:fur:0.7>\nSteps: 20", "lora_stack": "<lora:fur:0.7>"}
    # An API-format prompt graph is not a canvas workflow.
    assert copy_formats_from_png_info({"workflow": json.dumps({"3": {"class_type": "KSampler"}})})["workflow"] == ""


def test_copy_formats_endpoint_returns_full_untruncated_workflow(client, asset_root):  # noqa: F811
    big_workflow = {"nodes": [{"id": index, "title": "x" * 50} for index in range(100)], "links": []}
    _png(asset_root / "wf.png", workflow=big_workflow, bubba_metadata=BUBBA)
    payload = client.get("/api/assets/copy-formats", query_string={"path": str(asset_root / "wf.png")}).get_json()
    assert json.loads(payload["workflow"]) == big_workflow
    assert "Seed: 42" in payload["parameters"]
    assert client.get("/api/assets/copy-formats", query_string={"path": "C:/elsewhere/x.png"}).status_code == 400


# ---- 2. cull mode ----------------------------------------------------------


def test_parse_query_rating_filters():
    from services.asset_query import parse_query

    assert parse_query("is:keep").rating_filter == {"keep"}
    assert parse_query("is:unrated -is:reject").rating_filter == {"unrated"}
    assert parse_query("-is:reject").rating_exclude == {"reject"}
    assert not parse_query("is:reject").is_empty


def test_ratings_filter_follow_moves_and_survive_trash_restore(client, asset_root):  # noqa: F811
    for name in ("a.png", "b.png", "c.png"):
        _png(asset_root / name)
    (asset_root / "Keep").mkdir()
    client.get("/api/assets/list?root=test")
    a, b = str(asset_root / "a.png"), str(asset_root / "b.png")
    assert client.post("/api/assets/rating", json={"paths": [a], "rating": "keep"}).status_code == 200
    client.post("/api/assets/rating", json={"paths": [b], "rating": "reject"})
    assert client.post("/api/assets/rating", json={"paths": [a], "rating": "maybe"}).status_code == 400

    def names(query):
        payload = client.get("/api/assets/list", query_string={"root": "test", "q": query, "sort_by": "name", "sort_dir": "asc"})
        return [item["name"] for item in payload.get_json()["assets"]]

    assert names("is:keep") == ["a.png"]
    assert names("is:reject") == ["b.png"]
    assert names("is:unrated") == ["c.png"]
    assert names("-is:reject") == ["a.png", "c.png"]
    listed = {item["name"]: item.get("rating") for item in client.get("/api/assets/list?root=test").get_json()["assets"]}
    assert listed == {"a.png": "keep", "b.png": "reject", "c.png": None}
    assert client.get("/api/assets/details", query_string={"path": a}).get_json()["asset"]["rating"] == "keep"

    # Moving keeps the rating attached.
    client.post("/api/assets/move", json={"root": "test", "folder": "Keep", "paths": [a]})
    assert names("is:keep") == ["a.png"]
    moved = client.get("/api/assets/list", query_string={"root": "test", "q": "is:keep"}).get_json()["assets"][0]
    assert moved["relative_path"].startswith("Keep")

    # "Trash all rejects" = safe delete; Undo restores the file with its rating.
    trashed = client.post("/bubba/assets/delete", json={"paths": [b], "safe_delete": True}).get_json()["moved"]
    assert not (asset_root / "b.png").exists() and names("is:reject") == []
    client.post("/api/assets/restore", json={"items": trashed})
    assert names("is:reject") == ["b.png"]

    client.post("/api/assets/rating", json={"paths": [b], "rating": None})
    assert names("is:reject") == []


# ---- 3. XY sweep grid ------------------------------------------------------


def test_parse_legacy_notes_keeps_commas_inside_values():
    from services.sweep_groups import parse_legacy_notes

    assert parse_legacy_notes("XY sweep cfg=4, cfg=6 | steps=15, steps=20") == (["cfg=4", "cfg=6"], ["steps=15", "steps=20"])
    assert parse_legacy_notes("XY sweep positive_suffix=red hair, positive_suffix=blue eyes, smile") == (
        ["positive_suffix=red hair", "positive_suffix=blue eyes, smile"],
        [],
    )
    assert parse_legacy_notes("just notes") is None


def test_sweep_endpoint_uses_sweep_id_and_index(client, asset_root):  # noqa: F811
    import os

    sweep = {"sweep_id": "abc123", "sweep_x_labels": ["cfg=4", "cfg=6"], "sweep_y_labels": ["steps=10", "steps=20"], "notes": "XY sweep x"}
    order = [3, 0, 2, 1]  # saved out of order on purpose
    for position, index in enumerate(order):
        _png(asset_root / f"cell_{position}.png", bubba_metadata={**BUBBA, **sweep, "sweep_index": index})
    _png(asset_root / "sheet.png", size=(140, 140), bubba_metadata={**BUBBA, **sweep, "sweep_index": -1})
    _png(asset_root / "other.png", bubba_metadata={**BUBBA, **sweep, "sweep_id": "zzz", "sweep_index": 0})
    client.get("/api/assets/list?root=test")
    group = client.get("/api/assets/sweep", query_string={"path": str(asset_root / "cell_2.png")}).get_json()["sweep"]
    assert group["source"] == "sweep_id" and (group["columns"], group["rows"]) == (2, 2)
    assert [os.path.basename(cell["path"]) for cell in group["cells"]] == ["cell_1.png", "cell_3.png", "cell_2.png", "cell_0.png"]
    assert (group["cells"][3]["x"], group["cells"][3]["y"]) == ("cfg=6", "steps=20")
    assert group["sheet"]["name"] == "sheet.png"
    assert client.get("/api/assets/sweep", query_string={"path": str(asset_root / "sheet.png")}).status_code == 200


def test_sweep_endpoint_groups_legacy_notes_by_save_time(client, asset_root):  # noqa: F811
    import os
    import time

    notes = "XY sweep cfg=4, cfg=6, cfg=8"
    now = time.time()
    paths = []
    for run, offset in enumerate((0, 3600)):  # two runs with identical notes, an hour apart
        for index in range(3):
            path = asset_root / f"run{run}_{index}.png"
            _png(path, bubba_metadata={**BUBBA, "notes": notes})
            os.utime(path, (now - 7200 + offset + index, now - 7200 + offset + index))
            paths.append(path)
        sheet = asset_root / f"run{run}_sheet.png"
        _png(sheet, size=(200, 80), bubba_metadata={**BUBBA, "notes": notes})
        os.utime(sheet, (now - 7200 + offset + 5, now - 7200 + offset + 5))
    _png(asset_root / "plain.png", bubba_metadata=BUBBA)
    client.get("/api/assets/list?root=test")
    group = client.get("/api/assets/sweep", query_string={"path": str(paths[4])}).get_json()["sweep"]
    assert group["source"] == "notes" and group["rows"] == 1
    assert [cell["name"] for cell in group["cells"]] == ["run1_0.png", "run1_1.png", "run1_2.png"]
    assert [cell["x"] for cell in group["cells"]] == ["cfg=4", "cfg=6", "cfg=8"]
    assert group["sheet"]["name"] == "run1_sheet.png"
    assert client.get("/api/assets/sweep", query_string={"path": str(asset_root / "plain.png")}).status_code == 404


# ---- 4. Send to Discord / Immich ---------------------------------------------


def _bubba_user_dir(tmp_path, immich_url="http://127.0.0.1:9/api"):
    user = tmp_path / "comfy_user"
    (user / "bubba_nodes" / "discord").mkdir(parents=True, exist_ok=True)
    (user / "bubba_nodes" / "immich").mkdir(parents=True, exist_ok=True)
    (user / "bubba_nodes" / "discord" / "webhook_profiles.json").write_text(
        json.dumps({"Image Feed": "https://discord.com/api/webhooks/123/secret-token"}), encoding="utf-8"
    )
    (user / "bubba_nodes" / "immich" / "settings.json").write_text(
        json.dumps({"url": immich_url, "api_key": "immich-secret"}), encoding="utf-8"
    )
    return user


def test_send_targets_hide_secrets(client, tmp_path, monkeypatch):  # noqa: F811
    from services import library_api

    monkeypatch.setattr(library_api, "_comfyui_user_dir", lambda: "")
    assert client.get("/api/send/targets").get_json()["configured"] is False
    user = _bubba_user_dir(tmp_path)
    monkeypatch.setattr(library_api, "_comfyui_user_dir", lambda: str(user))
    response = client.get("/api/send/targets")
    payload = response.get_json()
    assert [target["id"] for target in payload["targets"]] == ["discord:Image Feed", "immich"]
    assert "secret" not in response.get_data(as_text=True)


def test_send_requires_confirmation_and_known_target(client, asset_root, tmp_path, monkeypatch):  # noqa: F811
    from services import library_api, send_targets

    monkeypatch.setattr(library_api, "_comfyui_user_dir", lambda: str(_bubba_user_dir(tmp_path)))
    monkeypatch.setattr(send_targets, "_open", lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("network used")))
    _png(asset_root / "a.png")
    path = str(asset_root / "a.png")
    assert client.post("/api/send", json={"target": "immich", "paths": [path]}).status_code == 400
    assert client.post("/api/send", json={"target": "discord:Nope", "paths": [path], "confirmed": True}).status_code == 400
    assert client.post("/api/send", json={"target": "immich", "paths": ["C:/outside.png"], "confirmed": True}).status_code == 400


def test_send_to_discord_posts_multipart_batches(client, asset_root, tmp_path, monkeypatch):  # noqa: F811
    from services import library_api, send_targets

    monkeypatch.setattr(library_api, "_comfyui_user_dir", lambda: str(_bubba_user_dir(tmp_path)))
    requests = []

    class _Response:
        status = 200

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def read(self):
            return b"{}"

    def fake_open(request, timeout):
        requests.append(request)
        return _Response()

    monkeypatch.setattr(send_targets, "_open", fake_open)
    paths = []
    for index in range(12):
        _png(asset_root / f"img{index}.png", bubba_metadata=BUBBA)
        paths.append(str(asset_root / f"img{index}.png"))
    payload = client.post(
        "/api/send", json={"target": "discord:Image Feed", "paths": paths, "message": "fresh batch", "confirmed": True}
    ).get_json()
    assert payload == {"sent": 12, "messages": 2, "destination": "Discord · Image Feed"}
    assert len(requests) == 2
    assert requests[0].full_url == "https://discord.com/api/webhooks/123/secret-token?wait=true"
    first_body = requests[0].data.decode("latin-1")
    assert first_body.count('name="files[') == 10 and '"content": "fresh batch"' in first_body
    assert requests[1].data.decode("latin-1").count('name="files[') == 2

    # A single image gets a generation embed.
    requests.clear()
    client.post("/api/send", json={"target": "discord:Image Feed", "paths": paths[:1], "confirmed": True})
    assert "Seed: 42" in requests[0].data.decode("latin-1")


def test_send_to_immich_uploads_to_fake_server(client, asset_root, tmp_path, monkeypatch):  # noqa: F811
    import threading
    from http.server import BaseHTTPRequestHandler, HTTPServer

    from services import library_api

    received = []

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            received.append((self.path, self.headers.get("x-api-key"), body))
            reply = json.dumps({"id": f"asset-{len(received)}", "status": "created"}).encode()
            self.send_response(201)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(reply)))
            self.end_headers()
            self.wfile.write(reply)

        def log_message(self, *args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        user = _bubba_user_dir(tmp_path, immich_url=f"http://127.0.0.1:{server.server_port}/api")
        monkeypatch.setattr(library_api, "_comfyui_user_dir", lambda: str(user))
        for name in ("a.png", "b.png"):
            _png(asset_root / name)
        paths = [str(asset_root / "a.png"), str(asset_root / "b.png")]
        response = client.post("/api/send", json={"target": "immich", "paths": paths, "confirmed": True})
        assert response.status_code == 200, response.get_json()
        assert response.get_json()["asset_ids"] == ["asset-1", "asset-2"]
        assert [item[0] for item in received] == ["/api/assets", "/api/assets"]
        assert all(item[1] == "immich-secret" for item in received)
        assert b'name="assetData"; filename="a.png"' in received[0][2]
        assert b'name="deviceId"' in received[0][2]
    finally:
        server.shutdown()
        server.server_close()


# ---- 5. NSFW detection -------------------------------------------------------


def _nudenet(label, score, box=(0.2, 0.2, 0.4, 0.4)):
    return {"label": label, "score": score, "box": list(box), "source": "nudenet"}


def _wd(label, score):
    return {"label": label, "score": score, "box": [0, 0, 1, 1], "source": "wd"}


def test_classify_presets_and_location_only_yolo():
    from services.nsfw_detect import classify, resolve_options, thresholds

    assert thresholds(75) == (0.4, 0.5) and thresholds(50) == (0.55, 0.65) and thresholds(33) == (0.652, 0.752)
    exposed = [_nudenet("FEMALE_BREAST_EXPOSED", 0.6)]
    assert classify(exposed, **resolve_options("cautious"))["rating"] == "nsfw"
    assert classify(exposed, **resolve_options("strict"))["rating"] == "questionable"
    # YOLO boxes never decide: clothed bodies stay SFW...
    yolo = [{"label": "breast", "score": 0.95, "box": [0.1, 0.1, 0.3, 0.3], "source": "yolo"}]
    assert classify(yolo + [_nudenet("FEMALE_BREAST_COVERED", 0.9)], **resolve_options("cautious"))["rating"] == "sfw"
    # ...but they are blurred as location evidence once the image is NSFW.
    result = classify(yolo + [_nudenet("FEMALE_GENITALIA_EXPOSED", 0.9)], **resolve_options("strict"))
    assert result["rating"] == "nsfw" and len(result["regions"]) == 2
    # Strict counts only the tagger's explicit rating; Cautious also counts nudity tags.
    nude_tag = [_wd("tag:nude", 0.8)]
    assert classify(nude_tag, **resolve_options("strict"))["rating"] == "sfw"
    assert classify(nude_tag, **resolve_options("cautious"))["rating"] == "nsfw"
    assert classify([_wd("rating:explicit", 0.9)], **resolve_options("strict"))["rating"] == "nsfw"
    # See-through switch: covered regions get blurred only when it is on.
    see_through = [_wd("tag:see-through", 0.8), _nudenet("FEMALE_BREAST_COVERED", 0.7)]
    assert classify(see_through, sensitivity=50, see_through=False, tagger="nudity")["rating"] == "questionable"
    on = classify(see_through, sensitivity=50, see_through=True, tagger="nudity")
    assert on["rating"] == "nsfw" and on["regions"][0]["label"] == "FEMALE_BREAST_COVERED"


def test_nsfw_list_uses_metadata_first_then_scan_cache_and_filters(client, asset_root, tmp_path, monkeypatch):  # noqa: F811
    from services import nsfw_scan_tasks
    from settings_model import Settings

    settings_file = tmp_path / "settings.json"
    settings_file.write_text("{}", encoding="utf-8")
    monkeypatch.setitem(Settings.model_config, "json_file", settings_file)  # default (strict) preset

    _png(
        asset_root / "saved.png",
        bubba_metadata={**BUBBA, "content_rating": "nsfw", "nsfw_score": 0.9, "nsfw_regions": [_nudenet("FEMALE_BREAST_EXPOSED", 0.9)]},
    )
    _png(asset_root / "old_nude.png", color=(250, 10, 10))
    _png(asset_root / "old_safe.png", color=(10, 250, 10))
    client.get("/api/assets/list?root=test")

    def names(query):
        payload = client.get("/api/assets/list", query_string={"root": "test", "q": query, "sort_by": "name", "sort_dir": "asc"})
        return [item["name"] for item in payload.get_json()["assets"]]

    assert names("is:nsfw") == ["saved.png"]
    assert names("is:unscanned") == ["old_nude.png", "old_safe.png"]
    status = client.get("/api/nsfw/status?root=test").get_json()
    assert status["pending"] == 2 and status["settings"]["nsfw_preset"] == "strict"

    class FakeAnalyzer:
        def analyze(self, image):
            red = image.convert("RGB").getpixel((0, 0))[0] > 200
            return [_nudenet("FEMALE_GENITALIA_EXPOSED", 0.95)] if red else [_nudenet("FEMALE_BREAST_COVERED", 0.5)]

    seen = []
    task = nsfw_scan_tasks.start_scan(str(asset_root), asset_root, lambda model_dir: seen.append(model_dir) or FakeAnalyzer(), background=False)
    assert task.snapshot()["status"] == "completed" and task.done == 2
    assert names("is:nsfw") == ["old_nude.png", "saved.png"]
    assert names("is:sfw") == ["old_safe.png"]
    assert names("-is:nsfw") == ["old_safe.png"]
    assert client.get("/api/nsfw/status?root=test").get_json()["pending"] == 0
    listed = {item["name"]: item.get("nsfw") for item in client.get("/api/assets/list?root=test").get_json()["assets"]}
    assert listed["saved.png"]["source"] == "metadata" and listed["old_nude.png"]["source"] == "scan"
    assert listed["old_nude.png"]["regions"][0]["box"] == [0.16, 0.16, 0.44, 0.44]  # padded for safety
    details = client.get("/api/assets/details", query_string={"path": str(asset_root / "old_nude.png")}).get_json()["asset"]
    assert details["nsfw"]["rating"] == "nsfw"

    # Editing a file invalidates its cached scan.
    _png(asset_root / "old_nude.png", color=(250, 10, 10), size=(65, 64))
    client.get("/api/assets/list?root=test&refresh_index=true")
    assert names("is:unscanned") == ["old_nude.png"]


def test_nsfw_settings_endpoint_applies_presets(client, tmp_path, monkeypatch):  # noqa: F811
    from services import app_context
    from settings_model import Settings

    settings_file = tmp_path / "settings.json"
    settings_file.write_text('{"general": {"asset_roots": []}}', encoding="utf-8")
    monkeypatch.setattr(app_context, "SETTINGS_FILE", settings_file)
    monkeypatch.setitem(Settings.model_config, "json_file", settings_file)
    saved = client.post("/api/nsfw/settings", json={"nsfw_preset": "cautious"}).get_json()["settings"]
    assert (saved["nsfw_sensitivity"], saved["nsfw_see_through"]) == (75, True)
    saved = client.post("/api/nsfw/settings", json={"nsfw_preset": "custom", "nsfw_sensitivity": 90, "preview": True}).get_json()["settings"]
    assert (saved["nsfw_preset"], saved["nsfw_sensitivity"], saved["preview"]) == ("custom", 90, True)
    assert json.loads(settings_file.read_text(encoding="utf-8"))["viewer"]["nsfw_sensitivity"] == 90
    assert client.post("/api/nsfw/settings", json={"nsfw_sensitivity": 500}).status_code == 400

    from services.nsfw_settings import current_nsfw_options

    assert current_nsfw_options() == {"sensitivity": 90.0, "see_through": True, "tagger": "nudity"}


def test_bubba_metadata_passes_sweep_and_rating_fields_through():
    from services.asset_viewer_metadata import coerce_bubba_metadata

    coerced = coerce_bubba_metadata(
        {**BUBBA, "sweep_id": "abc", "sweep_x_labels": ["cfg=4"], "sweep_index": "2", "content_rating": "NSFW", "nsfw_score": 3, "nsfw_regions": [{"label": "x"}, "junk"]}
    )
    assert (coerced["sweep_id"], coerced["sweep_index"], coerced["sweep_x_labels"], coerced["sweep_y_labels"]) == ("abc", 2, ["cfg=4"], [])
    assert (coerced["content_rating"], coerced["nsfw_score"], coerced["nsfw_regions"]) == ("nsfw", 1.0, [{"label": "x"}])
    assert "sweep_id" not in coerce_bubba_metadata(BUBBA)
