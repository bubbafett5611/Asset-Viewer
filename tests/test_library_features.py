from __future__ import annotations

import json
import os
import time
from datetime import datetime, timedelta
from io import BytesIO

from PIL import Image
from PIL.PngImagePlugin import PngInfo

# test_asset_viewer puts backend/ on sys.path, so import it before the backend modules.
from test_asset_viewer import asset_root, client, make_png_bytes  # noqa: F401, I001  (pytest fixtures)
from services.asset_query import build_facets, generation_fields, parse_query, row_matches  # noqa: E402


def _bubba_png(path, color=(200, 30, 30), **fields) -> None:
    info = PngInfo()
    info.add_text("bubba_metadata", json.dumps(fields))
    if "prompt_graph" in fields:
        info.add_text("prompt", json.dumps(fields.pop("prompt_graph")))
    image = Image.new("RGB", (64, 64), color)
    buffer = BytesIO()
    image.save(buffer, format="PNG", pnginfo=info)
    path.write_bytes(buffer.getvalue())


# ---- query parser (pure) ---------------------------------------------------


def test_parse_query_fields_exclusions_sizes_and_dates():
    parsed = parse_query('red hair model:"my model" -lora:detail size>2mb on:2026-11-12 is:fav')
    assert parsed.terms == ["red", "hair"]
    assert parsed.fields == [("model", "my model")]
    assert parsed.excluded_fields == [("lora", "detail")]
    assert parsed.min_size == 2 * 1024 * 1024
    assert parsed.favorites_only is True
    start = datetime(2026, 11, 12).timestamp()
    assert parsed.after_ts == start
    assert parsed.before_ts == (datetime(2026, 11, 12) + timedelta(days=1)).timestamp()


def test_unbalanced_quotes_do_not_crash():
    assert parse_query('model:"unterminated').fields == [("model", "unterminated")]


def test_row_matching_uses_normalized_generation_fields():
    summary = {
        "metadata": {
            "bubba_metadata": {
                "model_name": "rimixkv2",
                "seed": 42,
                "sampler_name": "er_sde",
                "loras": ["styles\\Detail_Tweaker.safetensors"],
            }
        }
    }
    generation = generation_fields(summary)
    assert generation["loras"] == ["Detail_Tweaker"]
    row = {"name": "a.png", "relative_path": "batch/a.png", "extension": ".png", "size_bytes": 10, "modified_ts": 1}
    assert row_matches(parse_query("model:rimix lora:detail seed:42"), row, "a.png", generation)
    assert not row_matches(parse_query("seed:4"), row, "a.png", generation)  # seed is exact
    assert not row_matches(parse_query("-sampler:er_sde"), row, "a.png", generation)
    assert row_matches(parse_query("folder:batch ext:png"), row, "a.png", generation)
    assert row_matches(parse_query("model:=rimixkv2"), row, "a.png", generation)
    assert not row_matches(parse_query("model:=rimix"), row, "a.png", generation)  # := is whole-value


def test_build_facets_counts_values_and_days():
    rows = [
        {"modified_ts": time.time(), "generation": {"model": "m1", "loras": ["a", "b"], "sampler": "euler", "prompt": "1girl, (red hair:1.2), masterpiece"}},
        {"modified_ts": time.time(), "generation": {"model": "m1", "loras": ["a"], "sampler": "dpm", "prompt": "1girl"}},
        {"modified_ts": time.time(), "generation": {}},
    ]
    facets = build_facets(rows)
    assert facets["total"] == 3 and facets["with_generation"] == 2
    assert facets["models"][0] == {"value": "m1", "count": 2}
    assert facets["loras"][0] == {"value": "a", "count": 2}
    tags = {item["value"]: item["count"] for item in facets["prompt_tags"]}
    assert tags["1girl"] == 2 and tags["red hair"] == 1 and "masterpiece" not in tags
    assert facets["days"][0]["count"] == 3


# ---- API ---------------------------------------------------------------------


def test_smart_search_through_list_api(client, asset_root):  # noqa: F811
    _bubba_png(asset_root / "one.png", model_name="anima_v1", sampler_name="euler", seed=1)
    _bubba_png(asset_root / "two.png", model_name="nova_xl", sampler_name="euler", seed=2)
    _bubba_png(asset_root / "three.png", model_name="anima_v1", sampler_name="dpm", seed=3)

    def names(query):
        payload = client.get("/api/assets/list", query_string={"root": "test", "q": query, "sort_by": "name", "sort_dir": "asc"}).get_json()
        return [item["name"] for item in payload["assets"]]

    assert names("model:anima") == ["one.png", "three.png"]
    assert names("model:anima -sampler:dpm") == ["one.png"]
    assert names("seed:2") == ["two.png"]
    assert names("one") == ["one.png"]


def test_facets_endpoint(client, asset_root):  # noqa: F811
    _bubba_png(asset_root / "one.png", model_name="anima_v1", loras=["detail"])
    _bubba_png(asset_root / "two.png", model_name="anima_v1")
    client.get("/api/assets/list?root=test")

    facets = client.get("/api/assets/facets?root=test").get_json()["facets"]

    assert facets["models"] == [{"value": "anima_v1", "count": 2}]
    assert facets["loras"] == [{"value": "detail", "count": 1}]


def test_collections_lifecycle_and_filter(client, asset_root):  # noqa: F811
    (asset_root / "Keep").mkdir()
    for name in ("a.png", "b.png", "c.png"):
        (asset_root / name).write_bytes(make_png_bytes().getvalue())
    client.get("/api/assets/list?root=test")
    a, b = str(asset_root / "a.png"), str(asset_root / "b.png")

    created = client.post("/api/collections", json={"root": "test", "name": "  Keepers ", "paths": [a]})
    assert created.status_code == 201
    collection = created.get_json()["collection"]
    assert collection["name"] == "Keepers"

    client.post(f"/api/collections/{collection['id']}/items", json={"root": "test", "paths": [b], "action": "add"})
    listed = client.get(f"/api/assets/list?root=test&collection={collection['id']}&sort_by=name&sort_dir=asc").get_json()
    assert [item["name"] for item in listed["assets"]] == ["a.png", "b.png"]
    assert client.get("/api/collections?root=test").get_json()["collections"][0]["count"] == 2

    # Membership follows a moved file.
    client.post("/api/assets/move", json={"root": "test", "folder": "Keep", "paths": [a]})
    listed = client.get(f"/api/assets/list?root=test&collection={collection['id']}").get_json()
    assert sorted(item["relative_path"] for item in listed["assets"]) == sorted([os.path.join("Keep", "a.png"), "b.png"])

    client.post(f"/api/collections/{collection['id']}/items", json={"root": "test", "paths": [b], "action": "remove"})
    assert client.patch(f"/api/collections/{collection['id']}", json={"root": "test", "name": "Best"}).status_code == 200
    collections = client.get("/api/collections?root=test").get_json()["collections"]
    assert collections == [{"id": collection["id"], "name": "Best", "count": 1}]

    assert client.delete(f"/api/collections/{collection['id']}?root=test").status_code == 200
    assert client.get("/api/collections?root=test").get_json()["collections"] == []
    assert client.delete(f"/api/collections/{collection['id']}?root=test").status_code == 404


def test_similar_images_rank_closest_first(client, asset_root):  # noqa: F811
    def gradient(path, flip=False, noise=0):
        image = Image.new("L", (64, 64))
        for x in range(64):
            for y in range(64):
                value = (x * 4 + (noise if (x + y) % 7 == 0 else 0)) % 256
                image.putpixel((63 - x if flip else x, y), value)
        image.save(path)

    gradient(asset_root / "base.png")
    gradient(asset_root / "near.png", noise=40)
    gradient(asset_root / "opposite.png", flip=True)
    client.get("/api/assets/list?root=test")

    payload = client.get("/api/assets/list", query_string={"root": "test", "similar_to": str(asset_root / "base.png")}).get_json()

    names = [item["name"] for item in payload["assets"]]
    assert names[0] == "base.png" and payload["assets"][0]["similarity"] == 100
    assert "near.png" in names
    assert "opposite.png" not in names


def test_changes_endpoint_counts_new_files(client, asset_root):  # noqa: F811
    (asset_root / "old.png").write_bytes(make_png_bytes().getvalue())
    since = client.get("/api/assets/list?root=test").get_json()["server_time"]
    time.sleep(0.05)
    (asset_root / "fresh.png").write_bytes(make_png_bytes().getvalue())

    from services import asset_api

    asset_api._last_refresh.clear()
    payload = client.get(f"/api/assets/changes?root=test&since={since}").get_json()

    assert payload["new_count"] == 1


def test_comfy_queue_requires_embedded_workflow(client, asset_root):  # noqa: F811
    (asset_root / "plain.png").write_bytes(make_png_bytes().getvalue())

    response = client.post("/api/comfy/queue", json={"path": str(asset_root / "plain.png")})

    assert response.status_code == 422
    assert "workflow" in response.get_json()["error"]


def test_comfy_queue_posts_prompt_graph(client, asset_root, monkeypatch):  # noqa: F811
    graph = {"3": {"class_type": "KSampler", "inputs": {"seed": 7}}}
    _bubba_png(asset_root / "wf.png", prompt_graph=graph, model_name="m")
    sent = {}

    class FakeResponse:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def read(self):
            return json.dumps({"prompt_id": "abc", "number": 4}).encode()

    def fake_urlopen(request, timeout=0):
        sent["url"] = request.full_url
        sent["body"] = json.loads(request.data)
        return FakeResponse()

    from services import asset_api

    monkeypatch.setattr(asset_api.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setattr(asset_api, "_comfyui_url", lambda: "http://127.0.0.1:8188")

    response = client.post("/api/comfy/queue", json={"path": str(asset_root / "wf.png")})

    assert response.status_code == 200
    assert response.get_json()["number"] == 4
    assert sent["url"] == "http://127.0.0.1:8188/prompt"
    assert sent["body"]["prompt"] == graph
