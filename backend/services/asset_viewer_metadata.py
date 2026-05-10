from __future__ import annotations

import json
import os
import struct
import time
from pathlib import Path
from typing import Any

from pydantic import BaseModel

ALLOWED_UPLOAD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".onnx"}
REPORT_CACHE_DIRNAME = ".asset_viewer_reports"
FOLDER_STATS_REPORT_FILE = "folder_stats.json"
METADATA_REPORT_FILE = "metadata_report.json"
BADGE_KEY_BUBBA_METADATA = "bubba_metadata"
BADGE_KEY_WORKFLOW = "workflow"
BADGE_KEY_PARAMETERS = "parameters"
METADATA_BADGE_LABELS = {
    BADGE_KEY_BUBBA_METADATA: "Bubba",
    BADGE_KEY_WORKFLOW: "Workflow",
    BADGE_KEY_PARAMETERS: "Params",
}

BUBBA_METADATA_DEFAULTS: dict[str, Any] = {
    "model_name": "",
    "clip_skip": 0,
    "sampler_time_seconds": 0.0,
    "steps": 0,
    "cfg": 0.0,
    "sampler_name": "",
    "scheduler": "",
    "denoise": 0.0,
    "seed": 0,
    "positive_prompt": "",
    "negative_prompt": "",
    "loras": [],
    "filepath": "",
}


def _sanitize_text(value: Any, max_len: int = 600) -> str:
    text = str(value or "").strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _safe_json_dumps(payload: Any) -> str:
    try:
        return json.dumps(payload, ensure_ascii=False)
    except Exception:
        return "{}"


def _parse_json_text(value: Any) -> Any:
    if not isinstance(value, str):
        return None
    try:
        return json.loads(value)
    except Exception:
        return None


def _coerce_non_negative_int(value: Any) -> int:
    try:
        parsed = int(value)
        return parsed if parsed >= 0 else 0
    except Exception:
        return 0


def _coerce_non_negative_float(value: Any, max_value: float | None = None) -> float:
    try:
        parsed = max(0.0, float(value))
    except Exception:
        return 0.0
    if max_value is not None:
        return min(parsed, max_value)
    return parsed


def _coerce_loras(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item or "").strip()]
    if isinstance(value, str):
        return [item.strip() for item in value.split(",") if item.strip()]
    return []


def coerce_bubba_metadata(value: Any) -> dict[str, Any]:
    payload = _parse_json_text(value) if isinstance(value, str) else value
    if not isinstance(payload, dict):
        payload = {}

    normalized = dict(BUBBA_METADATA_DEFAULTS)
    for key in ["model_name", "sampler_name", "scheduler", "positive_prompt", "negative_prompt", "filepath"]:
        normalized[key] = _sanitize_text(payload.get(key, ""), max_len=6000 if key.endswith("_prompt") else 800)

    for key in ["steps", "seed", "clip_skip"]:
        normalized[key] = _coerce_non_negative_int(payload.get(key))

    for key in ["cfg", "sampler_time_seconds"]:
        normalized[key] = _coerce_non_negative_float(payload.get(key))
    normalized["denoise"] = _coerce_non_negative_float(payload.get("denoise"), max_value=1.0)
    normalized["loras"] = _coerce_loras(payload.get("loras"))
    return normalized


def has_bubba_generation_metadata(metadata: Any) -> bool:
    if not isinstance(metadata, dict):
        return False
    return any(metadata.get(key) != default for key, default in BUBBA_METADATA_DEFAULTS.items() if key != "filepath")


def _extract_generation_from_a1111_parameters(raw: Any) -> dict[str, Any]:
    import re

    if not isinstance(raw, str):
        return {}

    text = raw.strip()
    if not text:
        return {}

    fields: dict[str, str] = {}
    patterns = {
        "steps": r"\bSteps:\s*([^,\n]+)",
        "sampler_name": r"\bSampler:\s*([^,\n]+)",
        "cfg": r"\bCFG scale:\s*([^,\n]+)",
        "seed": r"\bSeed:\s*([^,\n]+)",
        "model_name": r"\bModel(?: hash|):\s*([^,\n]+)",
    }
    for key, pattern in patterns.items():
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            fields[key] = _sanitize_text(match.group(1), max_len=400)

    if "Negative prompt:" in text:
        before, after = text.split("Negative prompt:", 1)
        positive = before.split("\n", 1)[0].strip()
        negative = after.split("\n", 1)[0].strip()
        if positive:
            fields["positive_prompt"] = _sanitize_text(positive, max_len=6000)
        if negative:
            fields["negative_prompt"] = _sanitize_text(negative, max_len=6000)

    return fields


def _extract_generation_from_png_info(info: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(info, dict):
        return {}
    # Keep extraction pragmatic for this phase: parse A1111 parameters and existing serialized generation payloads.
    generation_payload = _parse_json_text(info.get("generation"))
    if isinstance(generation_payload, dict):
        return generation_payload
    return _extract_generation_from_a1111_parameters(info.get("parameters"))


def _parse_safetensors_header(path: str, max_header_bytes: int = 4 * 1024 * 1024) -> dict[str, Any]:
    try:
        with open(path, "rb") as handle:
            raw_len = handle.read(8)
            if len(raw_len) != 8:
                return {}
            header_len = struct.unpack("<Q", raw_len)[0]
            if header_len <= 0 or header_len > max_header_bytes:
                return {}
            header_bytes = handle.read(int(header_len))
            if len(header_bytes) != int(header_len):
                return {}
            payload = json.loads(header_bytes.decode("utf-8", errors="replace"))
            if not isinstance(payload, dict):
                return {}
            metadata = payload.get("__metadata__", {})
            return metadata if isinstance(metadata, dict) else {}
    except Exception:
        return {}


def parse_png_metadata(path: str, image_module=None) -> dict[str, Any]:
    if image_module is None:
        return {}

    try:
        with image_module.open(path) as img:
            info = getattr(img, "info", {}) or {}
    except Exception:
        return {}

    if not isinstance(info, dict):
        return {}

    cleaned: dict[str, Any] = {}
    for key, value in info.items():
        normalized_key = str(key)
        if normalized_key == "bubba_metadata":
            coerced = coerce_bubba_metadata(value)
            if has_bubba_generation_metadata(coerced) or coerced.get("filepath"):
                cleaned[normalized_key] = coerced
            continue
        if isinstance(value, (str, int, float, bool)):
            cleaned[normalized_key] = _sanitize_text(value)
        elif isinstance(value, dict):
            cleaned[normalized_key] = _safe_json_dumps(value)

    generation = _extract_generation_from_png_info(info)
    if generation:
        cleaned["generation"] = generation
    return cleaned


def detect_metadata_badges(extension: str, path: str, image_module=None) -> list[dict[str, str]]:
    if extension.lower() != ".png" or image_module is None:
        return []

    try:
        with image_module.open(path) as img:
            info = getattr(img, "info", {}) or {}
    except Exception:
        return []

    if not isinstance(info, dict):
        return []

    keys = {str(key).lower() for key in info.keys()}
    badges: list[dict[str, str]] = []
    for key in (BADGE_KEY_BUBBA_METADATA, BADGE_KEY_WORKFLOW, BADGE_KEY_PARAMETERS):
        if key in keys:
            badges.append({"key": key, "label": METADATA_BADGE_LABELS[key]})
    return badges


def metadata_badge_keys_for_file(extension: str, path: str, image_module=None) -> set[str]:
    return {badge["key"] for badge in detect_metadata_badges(extension, path, image_module=image_module)}


def has_invalid_bubba_metadata(path: str, image_module=None) -> bool:
    if image_module is None:
        return False
    try:
        with image_module.open(path) as img:
            info = getattr(img, "info", {}) or {}
    except Exception:
        return False
    if "bubba_metadata" not in info:
        return False
    return _parse_json_text(info.get("bubba_metadata")) is None


def repair_png_bubba_metadata(path: str, image_module=None, pnginfo_cls=None, overwrite: bool = False) -> dict[str, Any]:
    if image_module is None or pnginfo_cls is None:
        raise RuntimeError("Pillow is required to repair PNG metadata.")

    abs_path = os.path.abspath(path)
    if Path(abs_path).suffix.lower() != ".png":
        raise ValueError("Bubba Metadata repair only supports PNG files.")

    with image_module.open(abs_path) as img:
        info = dict(getattr(img, "info", {}) or {})
        existing = info.get("bubba_metadata")
        existing_payload = _parse_json_text(existing) if isinstance(existing, str) else existing
        if not overwrite and isinstance(existing_payload, dict) and has_bubba_generation_metadata(coerce_bubba_metadata(existing_payload)):
            return {
                "repaired": False,
                "reason": "Bubba Metadata already exists.",
                "metadata": coerce_bubba_metadata(existing_payload),
            }

        generation = _extract_generation_from_png_info(info)
        if not generation:
            raise ValueError("No recoverable generation metadata found in prompt or parameters chunks.")

        metadata = coerce_bubba_metadata({**generation, "filepath": abs_path})
        if not has_bubba_generation_metadata(metadata):
            raise ValueError("Recovered metadata did not contain generation fields.")

        pnginfo = pnginfo_cls()
        for key, value in info.items():
            if str(key) == "bubba_metadata":
                continue
            if isinstance(value, str):
                pnginfo.add_text(str(key), value)
        pnginfo.add_text("bubba_metadata", json.dumps(metadata, ensure_ascii=False))

        temp_path = f"{abs_path}.repairing"
        img.save(temp_path, format="PNG", pnginfo=pnginfo)

    os.replace(temp_path, abs_path)
    return {"repaired": True, "metadata": metadata}


def summarize_metadata(extension: str, path: str, image_module=None) -> dict[str, Any]:
    ext = extension.lower()
    if ext == ".safetensors":
        metadata = _parse_safetensors_header(path)
        summary = {
            "format": "safetensors",
            "keys": sorted([str(key) for key in metadata.keys()]),
        }
        if metadata:
            summary["metadata"] = {str(key): _sanitize_text(value, max_len=800) for key, value in metadata.items()}
        return summary

    if ext == ".png":
        metadata = parse_png_metadata(path, image_module=image_module)
        summary = {
            "format": "png",
            "keys": sorted([str(key) for key in metadata.keys()]),
        }
        if metadata:
            summary["metadata"] = metadata
        return summary

    return {}


def _report_cache_path(root: str, filename: str, is_path_within_root_fn) -> str:
    normalized_root = os.path.abspath(root)
    cache_dir = os.path.join(normalized_root, REPORT_CACHE_DIRNAME)
    cache_path = os.path.abspath(os.path.join(cache_dir, filename))
    if not is_path_within_root_fn(cache_path, normalized_root):
        raise PermissionError("Report cache path is outside selected root.")
    return cache_path


def _load_report_cache(root: str, filename: str, model_cls: type[BaseModel], is_path_within_root_fn) -> BaseModel | None:
    cache_path = _report_cache_path(root, filename, is_path_within_root_fn)
    if not os.path.exists(cache_path):
        return None
    try:
        return model_cls.model_validate_json(Path(cache_path).read_text(encoding="utf-8"))
    except Exception:
        return None


def _save_report_cache(root: str, filename: str, report: BaseModel, is_path_within_root_fn) -> None:
    cache_path = _report_cache_path(root, filename, is_path_within_root_fn)
    os.makedirs(os.path.dirname(cache_path), exist_ok=True)
    Path(cache_path).write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


def build_metadata_report(root: str, metadata_report_cls, scan_assets_fn, image_module=None, limit: int = 10000):
    normalized_root = os.path.abspath(root)
    assets = scan_assets_fn(root=normalized_root, limit=limit, include_metadata=False, sort_by="name", sort_dir="asc")
    stats = metadata_report_cls(total_assets=len(assets))
    for asset in assets:
        extension = str(asset.get("extension") or "").lower()
        path = str(asset.get("path") or "")
        if extension == ".png":
            stats.png_assets += 1
        keys = {badge.get("key") for badge in asset.get("metadata_badges", []) if isinstance(badge, dict)}
        if BADGE_KEY_BUBBA_METADATA in keys:
            stats.bubba_metadata += 1
        if BADGE_KEY_WORKFLOW in keys:
            stats.workflow += 1
        if BADGE_KEY_PARAMETERS in keys:
            stats.parameters += 1
        if extension == ".png" and not keys:
            stats.no_tracked_metadata += 1
        if extension == ".png" and path and has_invalid_bubba_metadata(path, image_module=image_module):
            stats.invalid_bubba_metadata += 1
    return stats


def metadata_health_report(root: str, metadata_report_cls, scan_assets_fn, is_path_within_root_fn, image_module=None, limit: int = 10000, refresh: bool = False, cache_only: bool = False):
    if not refresh:
        cached = _load_report_cache(root, METADATA_REPORT_FILE, metadata_report_cls, is_path_within_root_fn)
        if isinstance(cached, metadata_report_cls):
            return cached, True
        if cache_only:
            return None, False
    report = build_metadata_report(root, metadata_report_cls, scan_assets_fn, image_module=image_module, limit=limit)
    _save_report_cache(root, METADATA_REPORT_FILE, report, is_path_within_root_fn)
    return report, False


def build_folder_stats_report(root: str, folder_stats_cls, is_path_within_root_fn, image_module=None):
    normalized_root = os.path.abspath(root)
    stats = folder_stats_cls(generated_at=time.time())
    if not os.path.isdir(normalized_root):
        return stats

    for current_dir, dirnames, filenames in os.walk(normalized_root):
        dirnames[:] = [name for name in dirnames if name not in {".asset_viewer_trash", REPORT_CACHE_DIRNAME}]
        for filename in filenames:
            abs_path = os.path.join(current_dir, filename)
            if not is_path_within_root_fn(abs_path, normalized_root):
                continue
            try:
                stat = os.stat(abs_path)
            except OSError:
                continue
            extension = Path(filename).suffix.lower()
            stats.total_files += 1
            stats.total_bytes += int(stat.st_size)
            if extension in ALLOWED_UPLOAD_IMAGE_EXTENSIONS:
                stats.image_files += 1
            elif extension in MODEL_EXTENSIONS:
                stats.model_files += 1
            else:
                stats.other_files += 1

            if extension == ".png":
                keys = metadata_badge_keys_for_file(extension, abs_path, image_module=image_module)
                if BADGE_KEY_BUBBA_METADATA in keys:
                    stats.bubba_metadata += 1
                if BADGE_KEY_WORKFLOW in keys:
                    stats.workflow += 1
                if BADGE_KEY_PARAMETERS in keys:
                    stats.parameters += 1
                if not keys:
                    stats.no_tracked_metadata += 1
                if has_invalid_bubba_metadata(abs_path, image_module=image_module):
                    stats.invalid_bubba_metadata += 1
    return stats


def folder_stats_report(root: str, folder_stats_cls, is_path_within_root_fn, image_module=None, refresh: bool = False, cache_only: bool = False):
    if not refresh:
        cached = _load_report_cache(root, FOLDER_STATS_REPORT_FILE, folder_stats_cls, is_path_within_root_fn)
        if isinstance(cached, folder_stats_cls):
            return cached, True
        if cache_only:
            return None, False
    report = build_folder_stats_report(root, folder_stats_cls, is_path_within_root_fn, image_module=image_module)
    _save_report_cache(root, FOLDER_STATS_REPORT_FILE, report, is_path_within_root_fn)
    return report, False
