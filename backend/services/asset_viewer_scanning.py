from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
from typing import Any, Callable


@dataclass(frozen=True)
class ScanRuntime:
    summarize_metadata: Callable[[str, str], dict[str, Any]]
    detect_metadata_badges: Callable[[str, str], list[dict[str, str]]]
    has_bubba_generation_metadata: Callable[[Any], bool]
    is_path_within_root: Callable[[str, str], bool]
    report_cache_dirname: str
    metadata_mode_all: str
    valid_metadata_modes: set[str]
    badge_key_no_tracked_metadata: str
    valid_metadata_badge_keys: set[str]


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


def _normalize_scan_request(
    root: str,
    extensions: list[str] | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_dir: str,
    runtime: ScanRuntime,
    metadata_mode: str,
    metadata_badge_filter: list[str] | None,
    min_size_bytes: int | None,
    max_size_bytes: int | None,
    modified_after_ts: float | None,
) -> dict[str, Any]:
    requested_exts = [ext.lower() for ext in (extensions or []) if ext.strip()]
    requested_exts = [ext if ext.startswith('.') else f'.{ext}' for ext in requested_exts]

    requested_sort_by = str(sort_by or 'name').strip().lower()
    if requested_sort_by not in {'name', 'modified', 'size', 'metadata'}:
        requested_sort_by = 'name'

    requested_sort_dir = str(sort_dir or 'asc').strip().lower()
    if requested_sort_dir not in {'asc', 'desc'}:
        requested_sort_dir = 'asc'

    requested_metadata_mode = str(metadata_mode or runtime.metadata_mode_all).strip().lower()
    if requested_metadata_mode not in runtime.valid_metadata_modes:
        requested_metadata_mode = runtime.metadata_mode_all

    requested_badges = {str(item).strip().lower() for item in (metadata_badge_filter or []) if str(item).strip()}
    requested_badges = requested_badges.intersection(runtime.valid_metadata_badge_keys)

    min_size = int(min_size_bytes) if isinstance(min_size_bytes, int) else None
    if min_size is not None and min_size < 0:
        min_size = 0

    max_size = int(max_size_bytes) if isinstance(max_size_bytes, int) else None
    if max_size is not None and max_size < 0:
        max_size = None

    modified_after = float(modified_after_ts) if isinstance(modified_after_ts, (int, float)) else None

    return {
        'normalized_root': os.path.abspath(root),
        'requested_exts': requested_exts,
        'limit': max(1, min(int(limit), 3000)),
        'offset': max(0, int(offset)),
        'requested_sort_by': requested_sort_by,
        'requested_sort_dir': requested_sort_dir,
        'requested_metadata_mode': requested_metadata_mode,
        'requested_badges': requested_badges,
        'min_size': min_size,
        'max_size': max_size,
        'modified_after': modified_after,
    }


def _metadata_flags(metadata_summary: dict[str, Any], has_bubba_generation_metadata_fn) -> tuple[bool, bool, bool]:
    metadata_obj = metadata_summary.get('metadata') if isinstance(metadata_summary.get('metadata'), dict) else {}
    generation_obj = metadata_obj.get('generation') if isinstance(metadata_obj, dict) else {}
    bubba_obj = metadata_obj.get('bubba_metadata') if isinstance(metadata_obj, dict) else None
    has_bubba_metadata = bool(bubba_obj)
    has_generation = bool(isinstance(generation_obj, dict) and generation_obj) or has_bubba_generation_metadata_fn(bubba_obj)
    workflow_val = metadata_obj.get('workflow') if isinstance(metadata_obj, dict) else None
    has_workflow = bool(workflow_val and str(workflow_val).strip())
    return has_generation, has_bubba_metadata, has_workflow


def _metadata_mode_matches(
    requested_metadata_mode: str,
    metadata_mode_all: str,
    supports_metadata: bool,
    metadata_summary: dict[str, Any],
    has_bubba_generation_metadata_fn,
) -> bool:
    if requested_metadata_mode == metadata_mode_all:
        return True
    if not supports_metadata:
        has_generation = False
        has_bubba_metadata = False
        has_workflow = False
    else:
        has_generation, has_bubba_metadata, has_workflow = _metadata_flags(metadata_summary, has_bubba_generation_metadata_fn)

    if requested_metadata_mode == 'has_generation':
        return has_generation
    if requested_metadata_mode == 'missing_generation':
        return not has_generation
    if requested_metadata_mode == 'has_bubba_metadata':
        return has_bubba_metadata
    if requested_metadata_mode == 'missing_bubba_metadata':
        return not has_bubba_metadata
    if requested_metadata_mode == 'has_workflow':
        return has_workflow
    if requested_metadata_mode == 'missing_workflow':
        return not has_workflow
    return True


def _scan_sort_key(requested_sort_by: str, item: dict[str, Any]) -> tuple[Any, ...]:
    name_key = str(item.get('name') or '').lower()
    path_key = str(item.get('relative_path') or '').lower()
    if requested_sort_by == 'modified':
        return (float(item.get('modified_ts') or 0.0), name_key, path_key)
    if requested_sort_by == 'size':
        return (int(item.get('size_bytes') or 0), name_key, path_key)
    if requested_sort_by == 'metadata':
        return (1 if item.get('metadata') else 0, name_key, path_key)
    return (name_key, path_key)


def scan_assets(
    runtime: ScanRuntime,
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
    request_state = _normalize_scan_request(
        root,
        extensions,
        limit,
        offset,
        sort_by,
        sort_dir,
        runtime,
        metadata_mode,
        metadata_badge_filter,
        min_size_bytes,
        max_size_bytes,
        modified_after_ts,
    )
    normalized_root = request_state['normalized_root']

    if not os.path.isdir(normalized_root):
        return []

    q = query.strip().lower()
    limit = request_state['limit']
    offset = request_state['offset']
    requested_sort_by = request_state['requested_sort_by']
    requested_sort_dir = request_state['requested_sort_dir']
    requested_metadata_mode = request_state['requested_metadata_mode']
    requested_badges = request_state['requested_badges']
    min_size = request_state['min_size']
    max_size = request_state['max_size']
    modified_after = request_state['modified_after']
    requested_exts = request_state['requested_exts']

    stream_fast_path = requested_sort_by == "name" and requested_sort_dir == "asc"

    files: list[dict[str, Any]] = []
    matched = 0

    for current_dir, dirnames, filenames in os.walk(normalized_root):
        dirnames[:] = [name for name in dirnames if name not in {".asset_viewer_trash", runtime.report_cache_dirname}]
        dirnames.sort(key=str.lower)
        filenames.sort(key=str.lower)
        for filename in filenames:
            extension = Path(filename).suffix.lower()
            if requested_exts and extension not in requested_exts:
                continue

            abs_path = os.path.join(current_dir, filename)
            if not runtime.is_path_within_root(abs_path, normalized_root):
                continue

            rel_path = os.path.relpath(abs_path, normalized_root)
            metadata_summary: dict[str, Any] = {}
            supports_metadata = extension in {".safetensors", ".png"}
            base_search_blob = f"{filename} {rel_path}".lower()

            needs_metadata_for_query = bool(q and search_in_metadata and supports_metadata and q not in base_search_blob)
            needs_metadata_for_payload = bool(include_metadata and supports_metadata)
            if needs_metadata_for_query or needs_metadata_for_payload:
                metadata_summary = runtime.summarize_metadata(extension, abs_path)

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

            if requested_metadata_mode != runtime.metadata_mode_all:
                if supports_metadata and not metadata_summary:
                    metadata_summary = runtime.summarize_metadata(extension, abs_path)
                if not _metadata_mode_matches(
                    requested_metadata_mode,
                    runtime.metadata_mode_all,
                    supports_metadata,
                    metadata_summary,
                    runtime.has_bubba_generation_metadata,
                ):
                    continue

            metadata_badges = runtime.detect_metadata_badges(extension, abs_path)
            if requested_badges:
                badge_keys = {badge["key"] for badge in metadata_badges}
                if runtime.badge_key_no_tracked_metadata in requested_badges:
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

    files.sort(key=lambda item: _scan_sort_key(requested_sort_by, item), reverse=requested_sort_dir == "desc")
    return files[offset : offset + limit]
