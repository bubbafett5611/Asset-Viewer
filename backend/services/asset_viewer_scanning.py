from __future__ import annotations

import os
from pathlib import Path
from typing import Any


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


def scan_assets(
    root: str,
    summarize_metadata_fn,
    detect_metadata_badges_fn,
    has_bubba_generation_metadata_fn,
    is_path_within_root_fn,
    report_cache_dirname: str,
    metadata_mode_all: str,
    valid_metadata_modes: set[str],
    badge_key_no_tracked_metadata: str,
    valid_metadata_badge_keys: set[str],
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

    requested_metadata_mode = str(metadata_mode or metadata_mode_all).strip().lower()
    if requested_metadata_mode not in valid_metadata_modes:
        requested_metadata_mode = metadata_mode_all

    requested_badges = {str(item).strip().lower() for item in (metadata_badge_filter or []) if str(item).strip()}
    requested_badges = requested_badges.intersection(valid_metadata_badge_keys)

    min_size = int(min_size_bytes) if isinstance(min_size_bytes, int) else None
    if min_size is not None and min_size < 0:
        min_size = 0

    max_size = int(max_size_bytes) if isinstance(max_size_bytes, int) else None
    if max_size is not None and max_size < 0:
        max_size = None

    modified_after = float(modified_after_ts) if isinstance(modified_after_ts, (int, float)) else None

    stream_fast_path = requested_sort_by == "name" and requested_sort_dir == "asc"

    files: list[dict[str, Any]] = []
    matched = 0

    for current_dir, dirnames, filenames in os.walk(normalized_root):
        dirnames[:] = [name for name in dirnames if name not in {".asset_viewer_trash", report_cache_dirname}]
        dirnames.sort(key=str.lower)
        filenames.sort(key=str.lower)
        for filename in filenames:
            extension = Path(filename).suffix.lower()
            if requested_exts and extension not in requested_exts:
                continue

            abs_path = os.path.join(current_dir, filename)
            if not is_path_within_root_fn(abs_path, normalized_root):
                continue

            rel_path = os.path.relpath(abs_path, normalized_root)
            metadata_summary: dict[str, Any] = {}
            supports_metadata = extension in {".safetensors", ".png"}
            base_search_blob = f"{filename} {rel_path}".lower()

            needs_metadata_for_query = bool(q and search_in_metadata and supports_metadata and q not in base_search_blob)
            needs_metadata_for_payload = bool(include_metadata and supports_metadata)
            if needs_metadata_for_query or needs_metadata_for_payload:
                metadata_summary = summarize_metadata_fn(extension, abs_path)

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

            if requested_metadata_mode != metadata_mode_all:
                if supports_metadata:
                    if not metadata_summary:
                        metadata_summary = summarize_metadata_fn(extension, abs_path)
                    metadata_obj = metadata_summary.get("metadata") if isinstance(metadata_summary.get("metadata"), dict) else {}
                    generation_obj = metadata_obj.get("generation") if isinstance(metadata_obj, dict) else {}
                    bubba_obj = metadata_obj.get("bubba_metadata") if isinstance(metadata_obj, dict) else None
                    has_bubba_metadata = bool(bubba_obj)
                    has_generation = bool(isinstance(generation_obj, dict) and generation_obj) or has_bubba_generation_metadata_fn(bubba_obj)
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

            metadata_badges = detect_metadata_badges_fn(extension, abs_path)
            if requested_badges:
                badge_keys = {badge["key"] for badge in metadata_badges}
                if badge_key_no_tracked_metadata in requested_badges:
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
