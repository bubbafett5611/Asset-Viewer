from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from io import BytesIO
import hashlib
import json
import os
import re
import shutil
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
	if extension.lower() != ".png" or Image is None:
		return []

	try:
		with Image.open(path) as img:
			info = getattr(img, "info", {}) or {}
	except Exception:
		return []

	if not isinstance(info, dict):
		return []

	keys = {str(key).lower() for key in info.keys()}
	badges: list[dict[str, str]] = []
	if "bubba_metadata" in keys:
		badges.append({"key": "bubba_metadata", "label": "Bubba"})
	if "workflow" in keys:
		badges.append({"key": "workflow", "label": "Workflow"})
	if "parameters" in keys:
		badges.append({"key": "parameters", "label": "Params"})
	return badges


def _metadata_badge_keys_for_file(extension: str, path: str) -> set[str]:
	return {badge["key"] for badge in _detect_metadata_badges(extension, path)}


def _has_invalid_bubba_metadata(path: str) -> bool:
	if Image is None:
		return False
	try:
		with Image.open(path) as img:
			info = getattr(img, "info", {}) or {}
	except Exception:
		return False
	if "bubba_metadata" not in info:
		return False
	return _parse_json_text(info.get("bubba_metadata")) is None


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
	normalized_root = os.path.abspath(root)
	assets = scan_assets(root=normalized_root, limit=limit, include_metadata=False, sort_by="name", sort_dir="asc")
	stats = MetadataReport(total_assets=len(assets))
	for asset in assets:
		extension = str(asset.get("extension") or "").lower()
		path = str(asset.get("path") or "")
		if extension == ".png":
			stats.png_assets += 1
		keys = {badge.get("key") for badge in asset.get("metadata_badges", []) if isinstance(badge, dict)}
		if "bubba_metadata" in keys:
			stats.bubba_metadata += 1
		if "workflow" in keys:
			stats.workflow += 1
		if "parameters" in keys:
			stats.parameters += 1
		if extension == ".png" and not keys:
			stats.no_tracked_metadata += 1
		if extension == ".png" and path and _has_invalid_bubba_metadata(path):
			stats.invalid_bubba_metadata += 1
	return stats


def metadata_health_report(root: str, limit: int = 10000, refresh: bool = False, cache_only: bool = False) -> tuple[MetadataReport | None, bool]:
	if not refresh:
		cached = _load_report_cache(root, METADATA_REPORT_FILE, MetadataReport)
		if isinstance(cached, MetadataReport):
			return cached, True
		if cache_only:
			return None, False
	report = build_metadata_report(root, limit=limit)
	_save_report_cache(root, METADATA_REPORT_FILE, report)
	return report, False


def build_folder_stats_report(root: str) -> FolderStatsReport:
	normalized_root = os.path.abspath(root)
	stats = FolderStatsReport()
	if not os.path.isdir(normalized_root):
		return stats

	for current_dir, dirnames, filenames in os.walk(normalized_root):
		dirnames[:] = [name for name in dirnames if name not in {".asset_viewer_trash", REPORT_CACHE_DIRNAME}]
		for filename in filenames:
			abs_path = os.path.join(current_dir, filename)
			if not _is_path_within_root(abs_path, normalized_root):
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
				keys = _metadata_badge_keys_for_file(extension, abs_path)
				if "bubba_metadata" in keys:
					stats.bubba_metadata += 1
				if "workflow" in keys:
					stats.workflow += 1
				if "parameters" in keys:
					stats.parameters += 1
				if not keys:
					stats.no_tracked_metadata += 1
				if _has_invalid_bubba_metadata(abs_path):
					stats.invalid_bubba_metadata += 1
	return stats


def folder_stats_report(root: str, refresh: bool = False, cache_only: bool = False) -> tuple[FolderStatsReport | None, bool]:
	if not refresh:
		cached = _load_report_cache(root, FOLDER_STATS_REPORT_FILE, FolderStatsReport)
		if isinstance(cached, FolderStatsReport):
			return cached, True
		if cache_only:
			return None, False
	report = build_folder_stats_report(root)
	_save_report_cache(root, FOLDER_STATS_REPORT_FILE, report)
	return report, False


def move_file_to_trash(path: str, root: str) -> str:
	normalized_root = os.path.abspath(root)
	abs_path = os.path.abspath(path)
	if not _is_path_within_root(abs_path, normalized_root):
		raise PermissionError("Requested file is outside selected root.")
	trash_root = os.path.join(normalized_root, ".asset_viewer_trash", time.strftime("%Y%m%d-%H%M%S"))
	rel_path = os.path.relpath(abs_path, normalized_root)
	destination = os.path.join(trash_root, rel_path)
	os.makedirs(os.path.dirname(destination), exist_ok=True)
	base, ext = os.path.splitext(destination)
	counter = 1
	while os.path.exists(destination):
		destination = f"{base}_{counter}{ext}"
		counter += 1
	shutil.move(abs_path, destination)
	return destination


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
	ext = extension.lower()
	if ext == ".safetensors":
		metadata = _parse_safetensors_header(path)
		summary = {
			"format": "safetensors",
			"keys": sorted([str(k) for k in metadata.keys()]),
		}
		if metadata:
			summary["metadata"] = {str(k): _sanitize_text(v, max_len=800) for k, v in metadata.items()}
		return summary

	if ext == ".png":
		metadata = _parse_png_metadata(path)
		summary = {
			"format": "png",
			"keys": sorted([str(k) for k in metadata.keys()]),
		}
		if metadata:
			summary["metadata"] = metadata
		return summary

	return {}


def discover_asset_roots() -> list[AssetRoot]:
	roots: list[AssetRoot] = []
	seen: set[str] = set()

	try:
		import folder_paths  # type: ignore
	except Exception as e:
		print(f"[asset_viewer] Could not import folder_paths: {e}")
		folder_paths = None

	if folder_paths is not None:
		for key, label, getter_name in [
			("input", "Comfy Input", "get_input_directory"),
			("output", "Comfy Output", "get_output_directory"),
		]:
			try:
				getter = getattr(folder_paths, getter_name)
				folder = getter()
				print(f"[asset_viewer] {getter_name} returned: {folder}")
			except Exception as e:
				print(f"[asset_viewer] Error calling {getter_name}: {e}")
				folder = None
			if not folder:
				continue
			real = _safe_real_path(folder)
			if real in seen or not os.path.isdir(folder):
				print(f"[asset_viewer] Skipping folder (already seen or not a dir): {folder}")
				continue
			seen.add(real)
			roots.append(AssetRoot(key=key, label=label, path=os.path.abspath(folder)))

	if not roots:
		fallback = os.getcwd()
		print(f"[asset_viewer] No asset roots found, using fallback: {fallback}")
		roots.append(AssetRoot(key="cwd", label="Current Directory", path=os.path.abspath(fallback)))

	print(f"[asset_viewer] Discovered asset roots: {roots}")
	return roots


def resolve_requested_root(requested_root: str | None, allowed_roots: list[AssetRoot]) -> str:
	if not allowed_roots:
		raise ValueError("No asset roots available.")

	if not requested_root:
		return allowed_roots[0].path

	requested = requested_root.strip()
	if not requested:
		return allowed_roots[0].path

	root_by_path = {os.path.abspath(root.path): root for root in allowed_roots}
	requested_abs = os.path.abspath(requested)
	if requested_abs in root_by_path:
		return requested_abs

	for root in allowed_roots:
		if requested == root.key:
			return root.path

	raise ValueError("Requested root is not allowed.")


def resolve_requested_file(requested_path: str | None, allowed_roots: list[AssetRoot]) -> str:
	if not allowed_roots:
		raise ValueError("No asset roots available.")

	raw = str(requested_path or "").strip()
	if not raw:
		raise ValueError("Missing file path.")

	normalized = os.path.abspath(raw)
	if not os.path.isfile(normalized):
		raise FileNotFoundError("File does not exist.")

	for root in allowed_roots:
		if _is_path_within_root(normalized, root.path):
			return normalized

	raise PermissionError("Requested file is outside allowed roots.")


def find_root_for_path(path: str, allowed_roots: list[AssetRoot]) -> AssetRoot | None:
	normalized = os.path.abspath(path)
	for root in allowed_roots:
		if _is_path_within_root(normalized, root.path):
			return root
	return None


def sanitize_upload_filename(filename: str, fallback: str = "upload.png") -> str:
	raw_name = os.path.basename(str(filename or "").strip())
	raw_name = raw_name.replace("\x00", "")
	raw_name = raw_name.replace("/", "_").replace("\\", "_")
	raw_name = re.sub(r"[^A-Za-z0-9._ -]+", "_", raw_name)

	if not raw_name or raw_name in {".", ".."}:
		raw_name = fallback

	stem = Path(raw_name).stem or "upload"
	ext = Path(raw_name).suffix.lower()
	if ext not in ALLOWED_UPLOAD_IMAGE_EXTENSIONS:
		ext = ".png"

	safe = f"{stem}{ext}"
	if len(safe) <= 180:
		return safe

	trimmed_stem = stem[: max(1, 180 - len(ext))]
	return f"{trimmed_stem}{ext}"


def make_unique_destination_path(root: str, filename: str) -> str:
	normalized_root = os.path.abspath(root)
	safe_name = sanitize_upload_filename(filename)
	base_stem = Path(safe_name).stem
	base_ext = Path(safe_name).suffix.lower()

	candidate = os.path.join(normalized_root, safe_name)
	counter = 1
	while os.path.exists(candidate):
		candidate = os.path.join(normalized_root, f"{base_stem}_{counter}{base_ext}")
		counter += 1

	return candidate


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
	if Image is None:
		return None

	try:
		size = max(32, min(int(max_size), 1024))
	except Exception:
		size = 256

	try:
		with Image.open(path) as img:
			image = img.convert("RGBA")
			image.thumbnail((size, size), Image.Resampling.LANCZOS)
			buffer = BytesIO()
			image.save(buffer, format="PNG", optimize=True)
			return buffer.getvalue()
	except Exception:
		return None


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
	normalized_root = os.path.abspath(root)
	limit = max(1, min(int(limit), 10000))
	near_threshold = max(0, min(int(near_threshold), 16))

	def report(stage: str, completed: int, total: int, percent: int, message: str) -> None:
		if progress_callback is None:
			return
		progress_callback({
			"stage": stage,
			"completed": completed,
			"total": total,
			"percent": max(0, min(int(percent), 100)),
			"message": message,
		})

	report("collecting", 0, 0, 2, "Collecting files...")
	assets = scan_assets(
		root=normalized_root,
		limit=limit,
		include_metadata=False,
		sort_by="name",
		sort_dir="asc",
	)
	report("hashing", 0, len(assets), 5, f"Scanning {len(assets)} file(s)...")

	content_hashes: dict[str, list[str]] = {}
	pixel_hashes: dict[str, list[str]] = {}
	content_hash_by_path: dict[str, str] = {}
	pixel_hash_by_path: dict[str, str] = {}
	dhash_by_path: dict[str, int] = {}

	for index, asset in enumerate(assets, start=1):
		path = str(asset.get("path") or "")
		extension = str(asset.get("extension") or "").lower()
		if not path:
			continue

		content_hash = _sha256_file(path)
		if content_hash:
			content_hash_by_path[path] = content_hash
			content_hashes.setdefault(content_hash, []).append(path)

		if extension in NEAR_DUPLICATE_IMAGE_EXTENSIONS:
			pixel_hash = _pixel_hash(path)
			if pixel_hash:
				pixel_hash_by_path[path] = pixel_hash
				pixel_hashes.setdefault(pixel_hash, []).append(path)
			if include_near:
				dhash_value = _dhash(path)
				if dhash_value is not None:
					dhash_by_path[path] = dhash_value

		if index == len(assets) or index == 1 or index % 10 == 0:
			percent = 5 + round((index / max(len(assets), 1)) * 65)
			report("hashing", index, len(assets), percent, f"Checked {index} of {len(assets)} file(s)...")

	groups: list[dict[str, Any]] = []
	report("grouping", 0, 0, 72, "Grouping exact and same-pixel matches...")
	for key, paths in content_hashes.items():
		if len(paths) > 1:
			_append_duplicate_group(groups, "exact", key, paths, normalized_root)

	for key, paths in pixel_hashes.items():
		if len(paths) > 1 and len({content_hash_by_path.get(path, "") for path in paths}) > 1:
			_append_duplicate_group(groups, "pixel", key, paths, normalized_root)

	if include_near and len(dhash_by_path) > 1:
		paths = list(dhash_by_path.keys())
		total_pairs = max(1, (len(paths) * (len(paths) - 1)) // 2)
		compared_pairs = 0
		parent = {path: path for path in paths}
		group_distance: dict[str, int] = {}

		def find(path: str) -> str:
			while parent[path] != path:
				parent[path] = parent[parent[path]]
				path = parent[path]
			return path

		def union(left: str, right: str, distance: int) -> None:
			left_root = find(left)
			right_root = find(right)
			if left_root == right_root:
				group_distance[left_root] = max(group_distance.get(left_root, distance), distance)
				return
			parent[right_root] = left_root
			group_distance[left_root] = max(group_distance.get(left_root, 0), group_distance.get(right_root, 0), distance)

		for left_index, left in enumerate(paths):
			for right in paths[left_index + 1 :]:
				if pixel_hash_by_path.get(left) and pixel_hash_by_path.get(left) == pixel_hash_by_path.get(right):
					compared_pairs += 1
					continue
				distance = _hamming_distance(dhash_by_path[left], dhash_by_path[right])
				if distance <= near_threshold:
					union(left, right, distance)
				compared_pairs += 1
				if compared_pairs == 1 or compared_pairs == total_pairs or compared_pairs % 1000 == 0:
					percent = 72 + round((compared_pairs / total_pairs) * 23)
					report("comparing", compared_pairs, total_pairs, percent, f"Compared {compared_pairs} of {total_pairs} image pair(s)...")

		near_groups: dict[str, list[str]] = {}
		for path in paths:
			near_groups.setdefault(find(path), []).append(path)

		for root_key, paths_in_group in near_groups.items():
			if len(paths_in_group) < 2:
				continue
			if len({pixel_hash_by_path.get(path, "") for path in paths_in_group}) <= 1:
				continue
			_append_duplicate_group(
				groups,
				"near",
				f"dhash:{root_key}",
				paths_in_group,
				normalized_root,
				distance=group_distance.get(find(root_key), 0),
			)
	else:
		report("grouping", 0, 0, 95, "Finishing duplicate groups...")

	groups.sort(key=lambda group: (str(group.get("kind") or ""), -int(group.get("count") or 0), str(group.get("key") or "")))
	summary = {
		"groups": len(groups),
		"assets": sum(int(group.get("count") or 0) for group in groups),
		"exact_groups": sum(1 for group in groups if group.get("kind") == "exact"),
		"pixel_groups": sum(1 for group in groups if group.get("kind") == "pixel"),
		"near_groups": sum(1 for group in groups if group.get("kind") == "near"),
		"scanned_assets": len(assets),
		"near_enabled": bool(include_near),
	}
	report("complete", len(groups), len(groups), 100, f"Found {len(groups)} duplicate group(s).")
	return {"groups": groups, "summary": summary}


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
	metadata_mode: str = "all",
	metadata_badge_filter: list[str] | None = None,
) -> list[dict[str, Any]]:
	normalized_root = os.path.abspath(root)
	requested_exts = [ext.lower() for ext in (extensions or []) if ext.strip()]
	requested_exts = [ext if ext.startswith(".") else f".{ext}" for ext in requested_exts]

	if not os.path.isdir(normalized_root):
		return []

	q = query.strip().lower()
	limit = max(1, min(int(limit), 3000))
	offset = max(0, int(offset))

	requested_sort_by = str(sort_by or "name").strip().lower()
	if requested_sort_by not in {"name", "modified", "size", "metadata"}:
		requested_sort_by = "name"

	requested_sort_dir = str(sort_dir or "asc").strip().lower()
	if requested_sort_dir not in {"asc", "desc"}:
		requested_sort_dir = "asc"

	requested_metadata_mode = str(metadata_mode or "all").strip().lower()
	_valid_metadata_modes = {
		"all",
		"has_generation",
		"missing_generation",
		"has_bubba_metadata",
		"missing_bubba_metadata",
		"has_workflow",
		"missing_workflow",
	}
	if requested_metadata_mode not in _valid_metadata_modes:
		requested_metadata_mode = "all"
	requested_badges = {str(item).strip().lower() for item in (metadata_badge_filter or []) if str(item).strip()}
	valid_badges = {"bubba_metadata", "workflow", "parameters", "no_tracked_metadata"}
	requested_badges = requested_badges.intersection(valid_badges)

	min_size = int(min_size_bytes) if isinstance(min_size_bytes, int) else None
	if min_size is not None and min_size < 0:
		min_size = 0

	max_size = int(max_size_bytes) if isinstance(max_size_bytes, int) else None
	if max_size is not None and max_size < 0:
		max_size = None

	modified_after = float(modified_after_ts) if isinstance(modified_after_ts, (int, float)) else None

	# Fast path keeps streaming behavior for default sort.
	stream_fast_path = requested_sort_by == "name" and requested_sort_dir == "asc"

	files: list[dict[str, Any]] = []
	matched = 0

	for current_dir, dirnames, filenames in os.walk(normalized_root):
		dirnames[:] = [name for name in dirnames if name not in {".asset_viewer_trash", REPORT_CACHE_DIRNAME}]
		dirnames.sort(key=str.lower)
		filenames.sort(key=str.lower)
		for filename in filenames:
			extension = Path(filename).suffix.lower()
			if requested_exts and extension not in requested_exts:
				continue

			abs_path = os.path.join(current_dir, filename)
			if not _is_path_within_root(abs_path, normalized_root):
				continue

			rel_path = os.path.relpath(abs_path, normalized_root)
			metadata_summary: dict[str, Any] = {}
			supports_metadata = extension in {".safetensors", ".png"}
			base_search_blob = f"{filename} {rel_path}".lower()

			needs_metadata_for_query = bool(q and search_in_metadata and supports_metadata and q not in base_search_blob)
			needs_metadata_for_payload = bool(include_metadata and supports_metadata)
			if needs_metadata_for_query or needs_metadata_for_payload:
				metadata_summary = summarize_metadata(extension, abs_path)

			if q:
				if q not in base_search_blob:
					if not metadata_summary:
						continue
					metadata_blob = _flatten_to_search_text(metadata_summary).lower()
					if q not in metadata_blob:
						continue

			try:
				stat = os.stat(abs_path)
			except OSError:
				continue

			size_bytes = int(stat.st_size)
			modified_ts = float(stat.st_mtime)

			if min_size is not None and size_bytes < min_size:
				continue
			if max_size is not None and size_bytes > max_size:
				continue
			if modified_after is not None and modified_ts < modified_after:
				continue

			if requested_metadata_mode != "all":
				if supports_metadata:
					if not metadata_summary:
						metadata_summary = summarize_metadata(extension, abs_path)
					metadata_obj = metadata_summary.get("metadata") if isinstance(metadata_summary.get("metadata"), dict) else {}

					# generation (ComfyUI prompt chunk)
					generation_obj = metadata_obj.get("generation") if isinstance(metadata_obj, dict) else {}

					# bubba metadata chunk
					bubba_obj = metadata_obj.get("bubba_metadata") if isinstance(metadata_obj, dict) else None
					has_bubba_metadata = bool(bubba_obj)
					has_generation = bool(isinstance(generation_obj, dict) and generation_obj) or _has_bubba_generation_metadata(bubba_obj)

					# workflow chunk (stored as non-empty string)
					workflow_val = metadata_obj.get("workflow") if isinstance(metadata_obj, dict) else None
					has_workflow = bool(workflow_val and str(workflow_val).strip())
				else:
					has_generation = False
					has_bubba_metadata = False
					has_workflow = False

				if requested_metadata_mode == "has_generation" and not has_generation:
					continue
				if requested_metadata_mode == "missing_generation" and has_generation:
					continue
				if requested_metadata_mode == "has_bubba_metadata" and not has_bubba_metadata:
					continue
				if requested_metadata_mode == "missing_bubba_metadata" and has_bubba_metadata:
					continue
				if requested_metadata_mode == "has_workflow" and not has_workflow:
					continue
				if requested_metadata_mode == "missing_workflow" and has_workflow:
					continue

			metadata_badges = _detect_metadata_badges(extension, abs_path)
			if requested_badges:
				badge_keys = {badge["key"] for badge in metadata_badges}
				if "no_tracked_metadata" in requested_badges:
					if badge_keys:
						continue
				elif not requested_badges.issubset(badge_keys):
					continue

			item: dict[str, Any] = {
				"name": filename,
				"path": abs_path,
				"relative_path": rel_path,
				"extension": extension,
				"size_bytes": size_bytes,
				"modified_ts": modified_ts,
			}
			if metadata_badges:
				item["metadata_badges"] = metadata_badges

			if include_metadata and metadata_summary:
				item["metadata"] = metadata_summary

			if stream_fast_path:
				if matched < offset:
					matched += 1
					continue

				matched += 1
				files.append(item)
				if len(files) >= limit:
					return files
				continue

			files.append(item)

	if stream_fast_path:
		return files

	def _sort_key(item: dict[str, Any]) -> tuple[Any, ...]:
		name_key = str(item.get("name") or "").lower()
		path_key = str(item.get("relative_path") or "").lower()
		if requested_sort_by == "modified":
			return (float(item.get("modified_ts") or 0.0), name_key, path_key)
		if requested_sort_by == "size":
			return (int(item.get("size_bytes") or 0), name_key, path_key)
		if requested_sort_by == "metadata":
			has_metadata = 1 if item.get("metadata") else 0
			return (has_metadata, name_key, path_key)
		return (name_key, path_key)

	files.sort(key=_sort_key, reverse=requested_sort_dir == "desc")
	return files[offset : offset + limit]
