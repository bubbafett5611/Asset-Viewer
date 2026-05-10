from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import logging
import os
import re
import struct
import time
from typing import Any, Callable

from pydantic import BaseModel, Field

try:
	from PIL import Image
	from PIL.PngImagePlugin import PngInfo
except Exception:  # pragma: no cover - Pillow is expected in Comfy runtime but keep fallback.
	Image = None
	PngInfo = None


ALLOWED_UPLOAD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
NEAR_DUPLICATE_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}
MODEL_EXTENSIONS = {".safetensors", ".ckpt", ".pt", ".pth", ".onnx"}
REPORT_CACHE_DIRNAME = ".asset_viewer_reports"
FOLDER_STATS_REPORT_FILE = "folder_stats.json"
METADATA_REPORT_FILE = "metadata_report.json"
METADATA_MODE_ALL = "all"
METADATA_MODE_HAS_GENERATION = "has_generation"
METADATA_MODE_MISSING_GENERATION = "missing_generation"
METADATA_MODE_HAS_BUBBA_METADATA = "has_bubba_metadata"
METADATA_MODE_MISSING_BUBBA_METADATA = "missing_bubba_metadata"
METADATA_MODE_HAS_WORKFLOW = "has_workflow"
METADATA_MODE_MISSING_WORKFLOW = "missing_workflow"
VALID_METADATA_MODES = {
	METADATA_MODE_ALL,
	METADATA_MODE_HAS_GENERATION,
	METADATA_MODE_MISSING_GENERATION,
	METADATA_MODE_HAS_BUBBA_METADATA,
	METADATA_MODE_MISSING_BUBBA_METADATA,
	METADATA_MODE_HAS_WORKFLOW,
	METADATA_MODE_MISSING_WORKFLOW,
}
BADGE_KEY_BUBBA_METADATA = "bubba_metadata"
BADGE_KEY_WORKFLOW = "workflow"
BADGE_KEY_PARAMETERS = "parameters"
BADGE_KEY_NO_TRACKED_METADATA = "no_tracked_metadata"
VALID_METADATA_BADGE_KEYS = {
	BADGE_KEY_BUBBA_METADATA,
	BADGE_KEY_WORKFLOW,
	BADGE_KEY_PARAMETERS,
	BADGE_KEY_NO_TRACKED_METADATA,
}
METADATA_BADGE_LABELS = {
	BADGE_KEY_BUBBA_METADATA: "Bubba",
	BADGE_KEY_WORKFLOW: "Workflow",
	BADGE_KEY_PARAMETERS: "Params",
}

logger = logging.getLogger("bubba.asset_viewer")

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


@dataclass(frozen=True)
class AssetRoot:
	key: str
	label: str
	path: str


class FolderStatsReport(BaseModel):
	generated_at: float = Field(default_factory=time.time)
	total_files: int = 0
	total_bytes: int = 0
	image_files: int = 0
	model_files: int = 0
	other_files: int = 0
	bubba_metadata: int = 0
	workflow: int = 0
	parameters: int = 0
	no_tracked_metadata: int = 0
	invalid_bubba_metadata: int = 0


class MetadataReport(BaseModel):
	generated_at: float = Field(default_factory=time.time)
	total_assets: int = 0
	png_assets: int = 0
	bubba_metadata: int = 0
	workflow: int = 0
	parameters: int = 0
	no_tracked_metadata: int = 0
	invalid_bubba_metadata: int = 0


def _safe_real_path(path: str) -> str:
	return os.path.normcase(os.path.realpath(path))


def _is_path_within_root(path: str, root: str) -> bool:
	path_real = _safe_real_path(path)
	root_real = _safe_real_path(root)
	try:
		return os.path.commonpath([path_real, root_real]) == root_real
	except ValueError:
		return False


def _report_cache_path(root: str, filename: str) -> str:
	normalized_root = os.path.abspath(root)
	cache_dir = os.path.join(normalized_root, REPORT_CACHE_DIRNAME)
	cache_path = os.path.abspath(os.path.join(cache_dir, filename))
	if not _is_path_within_root(cache_path, normalized_root):
		raise PermissionError("Report cache path is outside selected root.")
	return cache_path


def _load_report_cache(root: str, filename: str, model_cls: type[BaseModel]) -> BaseModel | None:
	cache_path = _report_cache_path(root, filename)
	if not os.path.exists(cache_path):
		return None
	try:
		return model_cls.model_validate_json(Path(cache_path).read_text(encoding="utf-8"))
	except Exception:
		return None


def _save_report_cache(root: str, filename: str, report: BaseModel) -> None:
	cache_path = _report_cache_path(root, filename)
	os.makedirs(os.path.dirname(cache_path), exist_ok=True)
	Path(cache_path).write_text(report.model_dump_json(indent=2) + "\n", encoding="utf-8")


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


def _coerce_bubba_metadata(value: Any) -> dict[str, Any]:
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


def _has_bubba_generation_metadata(metadata: Any) -> bool:
	if not isinstance(metadata, dict):
		return False
	return any(metadata.get(key) != default for key, default in BUBBA_METADATA_DEFAULTS.items() if key != "filepath")


def _resolve_prompt_ref(prompt_graph: dict[str, Any], ref: Any) -> dict[str, Any] | None:
	if not isinstance(ref, (list, tuple)) or not ref:
		return None

	if not isinstance(prompt_graph, dict):
		return None

	node_id = str(ref[0])
	node = prompt_graph.get(node_id)
	if isinstance(node, dict):
		return node
	return None


def _extract_text_from_ref(prompt_graph: dict[str, Any], ref: Any) -> str:
	node = _resolve_prompt_ref(prompt_graph, ref)
	if not node:
		return ""
	if not isinstance(node, dict):
		return ""
	if str(node.get("class_type") or "") != "CLIPTextEncode":
		return ""
	inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else node.get("inputs", {}) if isinstance(node.get("inputs", {}), dict) else {}
	if not isinstance(inputs, dict):
		inputs = {}
	return _sanitize_text(inputs.get("text", ""), max_len=6000)


def _extract_prompt_text_from_ref(prompt_graph: dict[str, Any], ref: Any) -> str:
	node = _resolve_prompt_ref(prompt_graph, ref)
	if not node or not isinstance(node, dict):
		return ""
	inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
	if not isinstance(inputs, dict):
		return ""

	class_type = str(node.get("class_type") or "")
	if class_type == "CLIPTextEncode":
		return _sanitize_text(inputs.get("text", ""), max_len=6000)

	parts: list[str] = []
	for key in ("text", "positive", "prompt", "orinalMessage", "originalMessage"):
		value = inputs.get(key)
		if isinstance(value, str) and value.strip():
			parts.append(value.strip())

	trigger_words = inputs.get("toggle_trigger_words")
	if isinstance(trigger_words, dict):
		for item in trigger_words.get("__value__", []):
			if isinstance(item, dict) and item.get("active", True):
				text = str(item.get("text") or "").strip()
				if text:
					parts.append(text)

	for key in ("trigger_words", "trigger_words1", "trigger_words2"):
		value = inputs.get(key)
		text = _extract_prompt_text_from_ref(prompt_graph, value)
		if text:
			parts.append(text)

	seen: set[str] = set()
	unique_parts = []
	for part in parts:
		for segment in str(part).split(","):
			cleaned = segment.strip()
			if not cleaned:
				continue
			normalized = re.sub(r"\s+", " ", cleaned.lower())
			if normalized in seen:
				continue
			seen.add(normalized)
			unique_parts.append(cleaned)
	return _sanitize_text(", ".join(unique_parts), max_len=6000)


def _resolve_prompt_input_value(prompt_graph: dict[str, Any], value: Any, output_name: str | None = None) -> Any:
	if not isinstance(value, (list, tuple)) or not value:
		return value
	node = _resolve_prompt_ref(prompt_graph, value)
	if not node or not isinstance(node, dict):
		return value
	inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
	if not isinstance(inputs, dict):
		return value

	preferred_keys = [output_name] if output_name else []
	preferred_keys.extend(["seed", "sampler_name", "scheduler", "ckpt_name", "unet_name", "text"])
	for key in preferred_keys:
		if key and key in inputs and inputs[key] not in (None, ""):
			return inputs[key]
	return value


def _extract_model_name_from_ref(prompt_graph: dict[str, Any], ref: Any) -> str:
	node = _resolve_prompt_ref(prompt_graph, ref)
	if not node or not isinstance(node, dict):
		return ""

	class_type = str(node.get("class_type") or "")
	inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else node.get("inputs", {}) if isinstance(node.get("inputs", {}), dict) else {}
	if not isinstance(inputs, dict):
		inputs = {}

	if class_type in {"CheckpointLoaderSimple", "CheckpointLoader", "Checkpoint Loader (Simple)"}:
		return _sanitize_text(inputs.get("ckpt_name", ""), max_len=500)
	if class_type == "UNETLoader":
		return _sanitize_text(inputs.get("unet_name", ""), max_len=500)
	if "model" in inputs:
		return _extract_model_name_from_ref(prompt_graph, inputs.get("model"))
	return ""


def _extract_loras_from_prompt(prompt_graph: dict[str, Any]) -> list[str]:
	loras: list[str] = []
	for node in prompt_graph.values():
		if not isinstance(node, dict):
			continue
		inputs = node.get("inputs") if isinstance(node.get("inputs"), dict) else {}
		if not isinstance(inputs, dict):
			continue
		raw_loras = inputs.get("loras")
		if isinstance(raw_loras, dict):
			for item in raw_loras.get("__value__", []):
				if not isinstance(item, dict) or item.get("active") is False:
					continue
				name = str(item.get("name") or "").strip()
				strength = str(item.get("strength") or item.get("model_strength") or "").strip()
				if name and strength:
					loras.append(f"{name}:{strength}")
				elif name:
					loras.append(name)
		text = inputs.get("text")
		if isinstance(text, str):
			loras.extend(match.group(1).strip() for match in re.finditer(r"<lora:([^>]+)>", text, flags=re.IGNORECASE))
	unique_loras: list[str] = []
	seen: set[str] = set()
	for item in _coerce_loras(loras):
		normalized = item.lower()
		if normalized in seen:
			continue
		seen.add(normalized)
		unique_loras.append(item)
	return unique_loras


def _extract_generation_from_comfy_prompt(prompt_graph: Any) -> dict[str, Any]:
	if not isinstance(prompt_graph, dict):
		return {}

	sampler_node: dict[str, Any] | None = None
	for node in prompt_graph.values():
		if not isinstance(node, dict):
			continue
		class_type = str(node.get("class_type") or "")
		if class_type in {"KSampler", "KSamplerAdvanced"} or class_type.lower().endswith("ksampler"):
			sampler_node = node

	if sampler_node is None:
		return {}

	inputs = sampler_node.get("inputs") if isinstance(sampler_node.get("inputs"), dict) else sampler_node.get("inputs", {}) if isinstance(sampler_node.get("inputs", {}), dict) else {}
	if not isinstance(inputs, dict):
		inputs = {}
	generation: dict[str, Any] = {}

	field_map = {
		"seed": "seed",
		"steps": "steps",
		"cfg": "cfg",
		"sampler_name": "sampler_name",
		"scheduler": "scheduler",
		"denoise": "denoise",
	}
	for target_key, source_key in field_map.items():
		if isinstance(inputs, dict) and source_key in inputs and inputs[source_key] not in (None, ""):
			generation[target_key] = _resolve_prompt_input_value(prompt_graph, inputs[source_key], source_key)

	model_name = _extract_model_name_from_ref(prompt_graph, inputs.get("model") if isinstance(inputs, dict) else None)
	if model_name:
		generation["model_name"] = model_name

	positive_prompt = _extract_prompt_text_from_ref(prompt_graph, inputs.get("positive") if isinstance(inputs, dict) else None)
	if positive_prompt:
		generation["positive_prompt"] = positive_prompt

	negative_prompt = _extract_prompt_text_from_ref(prompt_graph, inputs.get("negative") if isinstance(inputs, dict) else None)
	if negative_prompt:
		generation["negative_prompt"] = negative_prompt

	loras = _extract_loras_from_prompt(prompt_graph)
	if loras:
		generation["loras"] = loras

	return generation


def _extract_generation_from_a1111_parameters(raw: Any) -> dict[str, Any]:
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

	# Heuristic split for prompt/negative sections in common parameter dumps.
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

	prompt_payload = _parse_json_text(info.get("prompt"))
	from_prompt = _extract_generation_from_comfy_prompt(prompt_payload)
	if from_prompt:
		return from_prompt

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


def _parse_png_metadata(path: str) -> dict[str, Any]:
	if Image is None:
		return {}

	try:
		with Image.open(path) as img:
			info = getattr(img, "info", {}) or {}
	except Exception:
		return {}

	if not isinstance(info, dict):
		return {}

	cleaned: dict[str, Any] = {}
	for key, value in info.items():
		normalized_key = str(key)
		if normalized_key == "bubba_metadata":
			coerced = _coerce_bubba_metadata(value)
			if _has_bubba_generation_metadata(coerced) or coerced.get("filepath"):
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


def _detect_metadata_badges(extension: str, path: str) -> list[dict[str, str]]:
	from backend.services.asset_viewer_metadata import detect_metadata_badges as _detect

	return _detect(extension, path, image_module=Image)


def _metadata_badge_keys_for_file(extension: str, path: str) -> set[str]:
	from backend.services.asset_viewer_metadata import metadata_badge_keys_for_file as _keys

	return _keys(extension, path, image_module=Image)


def _has_invalid_bubba_metadata(path: str) -> bool:
	from backend.services.asset_viewer_metadata import has_invalid_bubba_metadata as _has_invalid

	return _has_invalid(path, image_module=Image)


def repair_png_bubba_metadata(path: str, overwrite: bool = False) -> dict[str, Any]:
	if Image is None or PngInfo is None:
		raise RuntimeError("Pillow is required to repair PNG metadata.")

	abs_path = os.path.abspath(path)
	if Path(abs_path).suffix.lower() != ".png":
		raise ValueError("Bubba Metadata repair only supports PNG files.")

	with Image.open(abs_path) as img:
		info = dict(getattr(img, "info", {}) or {})
		existing = info.get("bubba_metadata")
		existing_payload = _parse_json_text(existing) if isinstance(existing, str) else existing
		if not overwrite and isinstance(existing_payload, dict) and _has_bubba_generation_metadata(_coerce_bubba_metadata(existing_payload)):
			return {
				"repaired": False,
				"reason": "Bubba Metadata already exists.",
				"metadata": _coerce_bubba_metadata(existing_payload),
			}

		generation = _extract_generation_from_png_info(info)
		if not generation:
			raise ValueError("No recoverable generation metadata found in prompt or parameters chunks.")

		metadata = _coerce_bubba_metadata({**generation, "filepath": abs_path})
		if not _has_bubba_generation_metadata(metadata):
			raise ValueError("Recovered metadata did not contain generation fields.")

		pnginfo = PngInfo()
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


def build_metadata_report(root: str, limit: int = 10000) -> MetadataReport:
	from backend.services.asset_viewer_metadata import build_metadata_report as _build_metadata_report

	return _build_metadata_report(root, MetadataReport, scan_assets, image_module=Image, limit=limit)


def metadata_health_report(root: str, limit: int = 10000, refresh: bool = False, cache_only: bool = False) -> tuple[MetadataReport | None, bool]:
	from backend.services.asset_viewer_metadata import metadata_health_report as _metadata_health_report

	return _metadata_health_report(
		root,
		MetadataReport,
		scan_assets,
		_is_path_within_root,
		image_module=Image,
		limit=limit,
		refresh=refresh,
		cache_only=cache_only,
	)


def build_folder_stats_report(root: str) -> FolderStatsReport:
	from backend.services.asset_viewer_metadata import build_folder_stats_report as _build_folder_stats_report

	return _build_folder_stats_report(root, FolderStatsReport, _is_path_within_root, image_module=Image)


def folder_stats_report(root: str, refresh: bool = False, cache_only: bool = False) -> tuple[FolderStatsReport | None, bool]:
	from backend.services.asset_viewer_metadata import folder_stats_report as _folder_stats_report

	return _folder_stats_report(
		root,
		FolderStatsReport,
		_is_path_within_root,
		image_module=Image,
		refresh=refresh,
		cache_only=cache_only,
	)


def move_file_to_trash(path: str, root: str) -> str:
	from backend.services.asset_viewer_trash import move_file_to_trash as _move_file_to_trash

	return _move_file_to_trash(path, root, _is_path_within_root)


def _flatten_to_search_text(value: Any) -> str:
	if value is None:
		return ""
	if isinstance(value, dict):
		parts: list[str] = []
		for key, item in value.items():
			parts.append(str(key))
			parts.append(_flatten_to_search_text(item))
		return " ".join(parts)
	if isinstance(value, list):
		return " ".join(_flatten_to_search_text(item) for item in value)
	return str(value)


def summarize_metadata(extension: str, path: str) -> dict[str, Any]:
	from backend.services.asset_viewer_metadata import summarize_metadata as _summarize_metadata

	return _summarize_metadata(extension, path, image_module=Image)


def discover_asset_roots() -> list[AssetRoot]:
	from backend.services.asset_viewer_roots import discover_asset_roots as _discover_asset_roots

	return [AssetRoot(key=key, label=label, path=path) for key, label, path in _discover_asset_roots(logger)]


def resolve_requested_root(requested_root: str | None, allowed_roots: list[AssetRoot]) -> str:
	from backend.services.asset_viewer_roots import resolve_requested_root as _resolve_requested_root

	serializable_roots = [(root.key, root.label, root.path) for root in allowed_roots]
	return _resolve_requested_root(requested_root, serializable_roots)


def resolve_requested_file(requested_path: str | None, allowed_roots: list[AssetRoot]) -> str:
	from backend.services.asset_viewer_roots import resolve_requested_file as _resolve_requested_file

	serializable_roots = [(root.key, root.label, root.path) for root in allowed_roots]
	return _resolve_requested_file(requested_path, serializable_roots)


def find_root_for_path(path: str, allowed_roots: list[AssetRoot]) -> AssetRoot | None:
	from backend.services.asset_viewer_roots import find_root_for_path as _find_root_for_path

	serializable_roots = [(root.key, root.label, root.path) for root in allowed_roots]
	found = _find_root_for_path(path, serializable_roots)
	if not found:
		return None
	return AssetRoot(key=found[0], label=found[1], path=found[2])


def sanitize_upload_filename(filename: str, fallback: str = "upload.png") -> str:
	from backend.services.asset_viewer_roots import sanitize_upload_filename as _sanitize_upload_filename

	return _sanitize_upload_filename(filename, fallback=fallback)


def make_unique_destination_path(root: str, filename: str) -> str:
	from backend.services.asset_viewer_roots import make_unique_destination_path as _make_unique_destination_path

	return _make_unique_destination_path(root, filename)


def build_asset_item(path: str, root: str, include_metadata: bool = False) -> dict[str, Any]:
	normalized_root = os.path.abspath(root)
	abs_path = os.path.abspath(path)
	if not _is_path_within_root(abs_path, normalized_root):
		raise PermissionError("Requested file is outside selected root.")

	extension = Path(abs_path).suffix.lower()
	rel_path = os.path.relpath(abs_path, normalized_root)
	stat = os.stat(abs_path)

	item: dict[str, Any] = {
		"name": os.path.basename(abs_path),
		"path": abs_path,
		"relative_path": rel_path,
		"extension": extension,
		"size_bytes": int(stat.st_size),
		"modified_ts": float(stat.st_mtime),
	}
	metadata_badges = _detect_metadata_badges(extension, abs_path)
	if metadata_badges:
		item["metadata_badges"] = metadata_badges

	if include_metadata and extension in {".safetensors", ".png"}:
		metadata = summarize_metadata(extension, abs_path)
		if metadata:
			item["metadata"] = metadata

	return item


def generate_thumbnail_bytes(path: str, max_size: int = 256) -> bytes | None:
	from backend.services.asset_viewer_thumbnails import generate_thumbnail_bytes as _generate_thumbnail_bytes

	return _generate_thumbnail_bytes(path, max_size=max_size, image_module=Image)


def _sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str | None:
	try:
		digest = hashlib.sha256()
		with open(path, "rb") as handle:
			for chunk in iter(lambda: handle.read(chunk_size), b""):
				digest.update(chunk)
		return digest.hexdigest()
	except OSError:
		return None


def _pixel_hash(path: str) -> str | None:
	if Image is None:
		return None
	try:
		with Image.open(path) as img:
			image = img.convert("RGBA")
			digest = hashlib.sha256()
			digest.update(str(image.size).encode("ascii"))
			digest.update(image.tobytes())
			return digest.hexdigest()
	except Exception:
		return None


def _dhash(path: str, hash_size: int = 8) -> int | None:
	if Image is None:
		return None
	try:
		with Image.open(path) as img:
			image = img.convert("L").resize((hash_size + 1, hash_size), Image.Resampling.LANCZOS)
			pixels = image.tobytes()
	except Exception:
		return None

	value = 0
	width = hash_size + 1
	for y in range(hash_size):
		row = y * width
		for x in range(hash_size):
			value = (value << 1) | (1 if pixels[row + x] > pixels[row + x + 1] else 0)
	return value


def _hamming_distance(left: int, right: int) -> int:
	return (left ^ right).bit_count()


def _append_duplicate_group(
	groups: list[dict[str, Any]],
	kind: str,
	key: str,
	paths: list[str],
	root: str,
	distance: int | None = None,
) -> None:
	assets: list[dict[str, Any]] = []
	for path in sorted(paths, key=lambda item: os.path.relpath(item, root).lower()):
		try:
			assets.append(build_asset_item(path, root, include_metadata=False))
		except Exception:
			continue

	if len(assets) < 2:
		return

	sizes = [int(asset.get("size_bytes") or 0) for asset in assets]
	group: dict[str, Any] = {
		"kind": kind,
		"key": key,
		"count": len(assets),
		"assets": assets,
		"total_bytes": sum(sizes),
		"wasted_bytes": sum(sizes) - max(sizes),
	}
	if distance is not None:
		group["distance"] = distance
	groups.append(group)


def scan_duplicate_assets(
	root: str,
	include_near: bool = False,
	near_threshold: int = 6,
	limit: int = 5000,
	progress_callback: Callable[[dict[str, Any]], None] | None = None,
) -> dict[str, Any]:
	from backend.services.asset_viewer_duplicates import scan_duplicate_assets as _scan_duplicate_assets

	return _scan_duplicate_assets(
		root,
		scan_assets,
		build_asset_item,
		NEAR_DUPLICATE_IMAGE_EXTENSIONS,
		image_module=Image,
		include_near=include_near,
		near_threshold=near_threshold,
		limit=limit,
		progress_callback=progress_callback,
	)


def scan_assets(
	root: str,
	query: str = "",
	extensions: list[str] | None = None,
	limit: int = 600,
	include_metadata: bool = True,
	offset: int = 0,
	search_in_metadata: bool = True,
	sort_by: str = "modified",
	sort_dir: str = "desc",
	min_size_bytes: int | None = None,
	max_size_bytes: int | None = None,
	modified_after_ts: float | None = None,
	metadata_mode: str = METADATA_MODE_ALL,
	metadata_badge_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
	from backend.services.asset_viewer_scanning import scan_assets as _scan_assets

	return _scan_assets(
		root=root,
		summarize_metadata_fn=summarize_metadata,
		detect_metadata_badges_fn=_detect_metadata_badges,
		has_bubba_generation_metadata_fn=_has_bubba_generation_metadata,
		is_path_within_root_fn=_is_path_within_root,
		report_cache_dirname=REPORT_CACHE_DIRNAME,
		metadata_mode_all=METADATA_MODE_ALL,
		valid_metadata_modes=VALID_METADATA_MODES,
		badge_key_no_tracked_metadata=BADGE_KEY_NO_TRACKED_METADATA,
		valid_metadata_badge_keys=VALID_METADATA_BADGE_KEYS,
		query=query,
		extensions=extensions,
		limit=limit,
		include_metadata=include_metadata,
		offset=offset,
		search_in_metadata=search_in_metadata,
		sort_by=sort_by,
		sort_dir=sort_dir,
		min_size_bytes=min_size_bytes,
		max_size_bytes=max_size_bytes,
		modified_after_ts=modified_after_ts,
		metadata_mode=metadata_mode,
		metadata_badge_filter=metadata_badge_filter,
	)
