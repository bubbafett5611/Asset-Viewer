from __future__ import annotations

from dataclasses import dataclass
import json
import os
from pathlib import Path
import sqlite3
import time
from typing import Any, Callable

from runtime_paths import asset_index_cache_file
from services.asset_query import build_facets, generation_fields, parse_query, row_matches
from services.asset_viewer_scanning import _flatten_to_search_text
from services.nsfw_detect import classify, resolve_options


INDEX_SCHEMA_VERSION = "1"
EXCLUDED_DIRS = {".asset_viewer_trash", ".asset_viewer_reports"}
SUPPORTS_METADATA_EXTENSIONS = {".png", ".safetensors"}
HASH_COLUMNS = {
    "content_hash": "TEXT",
    "pixel_hash": "TEXT",
    "dhash": "TEXT",
}


@dataclass(frozen=True)
class AssetIndexRuntime:
    summarize_metadata: Callable[[str, str], dict[str, Any]]
    detect_metadata_badges: Callable[[str, str], list[dict[str, str]]]
    has_bubba_generation_metadata: Callable[[Any], bool]
    is_path_within_root: Callable[[str, str], bool]
    metadata_mode_all: str
    valid_metadata_modes: set[str]
    badge_key_no_tracked_metadata: str
    valid_metadata_badge_keys: set[str]


def _connect(root: str) -> sqlite3.Connection:
    db_path = asset_index_cache_file(root)
    db_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(str(db_path))
    connection.row_factory = sqlite3.Row
    return connection


def _ensure_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS assets (
            path TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            name TEXT NOT NULL,
            relative_path TEXT NOT NULL,
            extension TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            modified_ts REAL NOT NULL,
            metadata_badges_json TEXT NOT NULL,
            metadata_json TEXT NOT NULL,
            search_text TEXT NOT NULL,
            content_hash TEXT,
            pixel_hash TEXT,
            dhash TEXT,
            indexed_at REAL NOT NULL
        )
        """
    )
    existing_columns = {
        row["name"]
        for row in connection.execute("PRAGMA table_info(assets)")
    }
    for column_name, column_type in HASH_COLUMNS.items():
        if column_name not in existing_columns:
            connection.execute(f"ALTER TABLE assets ADD COLUMN {column_name} {column_type}")
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS meta (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS favorites (
            path TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            added_at REAL NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS ratings (
            path TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            rating TEXT NOT NULL,
            rated_at REAL NOT NULL
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS nsfw_scans (
            path TEXT PRIMARY KEY,
            root TEXT NOT NULL,
            size_bytes INTEGER NOT NULL,
            modified_ts REAL NOT NULL,
            evidence_json TEXT NOT NULL,
            analyzed_at REAL NOT NULL
        )
        """
    )
    _ensure_collection_schema(connection)
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_root_name ON assets(root, name, relative_path)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_root_modified ON assets(root, modified_ts)")
    connection.execute("CREATE INDEX IF NOT EXISTS idx_assets_root_size ON assets(root, size_bytes)")
    connection.execute(
        "INSERT OR REPLACE INTO meta(key, value) VALUES ('schema_version', ?)",
        (INDEX_SCHEMA_VERSION,),
    )
    connection.commit()


def _json_dumps(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    except Exception:
        return "{}"


def _json_loads(raw: str, fallback: Any) -> Any:
    try:
        return json.loads(raw)
    except Exception:
        return fallback


def _metadata_flags(metadata_summary: dict[str, Any], has_bubba_generation_metadata_fn) -> tuple[bool, bool, bool]:
    metadata_obj = metadata_summary.get("metadata") if isinstance(metadata_summary.get("metadata"), dict) else {}
    generation_obj = metadata_obj.get("generation") if isinstance(metadata_obj, dict) else {}
    bubba_obj = metadata_obj.get("bubba_metadata") if isinstance(metadata_obj, dict) else None
    has_bubba_metadata = bool(bubba_obj)
    has_generation = bool(isinstance(generation_obj, dict) and generation_obj) or has_bubba_generation_metadata_fn(
        bubba_obj
    )
    workflow_val = metadata_obj.get("workflow") if isinstance(metadata_obj, dict) else None
    has_workflow = bool(workflow_val and str(workflow_val).strip())
    return has_generation, has_bubba_metadata, has_workflow


def _metadata_mode_matches(
    requested_metadata_mode: str,
    runtime: AssetIndexRuntime,
    extension: str,
    metadata_summary: dict[str, Any],
) -> bool:
    if requested_metadata_mode == runtime.metadata_mode_all:
        return True
    if extension not in SUPPORTS_METADATA_EXTENSIONS:
        has_generation = False
        has_bubba_metadata = False
        has_workflow = False
    else:
        has_generation, has_bubba_metadata, has_workflow = _metadata_flags(
            metadata_summary,
            runtime.has_bubba_generation_metadata,
        )

    if requested_metadata_mode == "has_generation":
        return has_generation
    if requested_metadata_mode == "missing_generation":
        return not has_generation
    if requested_metadata_mode == "has_bubba_metadata":
        return has_bubba_metadata
    if requested_metadata_mode == "missing_bubba_metadata":
        return not has_bubba_metadata
    if requested_metadata_mode == "has_workflow":
        return has_workflow
    if requested_metadata_mode == "missing_workflow":
        return not has_workflow
    return True


def _normalize_request(
    extensions: list[str] | None,
    limit: int,
    offset: int,
    sort_by: str,
    sort_dir: str,
    runtime: AssetIndexRuntime,
    metadata_mode: str,
    metadata_badge_filter: list[str] | None,
    min_size_bytes: int | None,
    max_size_bytes: int | None,
    modified_after_ts: float | None,
    folder: str = "",
) -> dict[str, Any]:
    requested_exts = [ext.lower() for ext in (extensions or []) if ext.strip()]
    requested_exts = [ext if ext.startswith(".") else f".{ext}" for ext in requested_exts]

    requested_sort_by = str(sort_by or "name").strip().lower()
    if requested_sort_by not in {"name", "extension", "modified", "size", "metadata"}:
        requested_sort_by = "name"

    requested_sort_dir = str(sort_dir or "asc").strip().lower()
    if requested_sort_dir not in {"asc", "desc"}:
        requested_sort_dir = "asc"

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
    requested_folder = str(folder or "").strip().replace("\\", os.sep).replace("/", os.sep)
    requested_folder = "" if requested_folder in {"", "."} else os.path.normpath(requested_folder)
    if requested_folder.startswith("..") or os.path.isabs(requested_folder):
        requested_folder = ""

    return {
        "requested_exts": requested_exts,
        "limit": max(1, min(int(limit), 3000)),
        "offset": max(0, int(offset)),
        "requested_sort_by": requested_sort_by,
        "requested_sort_dir": requested_sort_dir,
        "requested_metadata_mode": requested_metadata_mode,
        "requested_badges": requested_badges,
        "min_size": min_size,
        "max_size": max_size,
        "modified_after": modified_after,
        "requested_folder": requested_folder,
    }


def _sort_key(requested_sort_by: str, item: dict[str, Any]) -> tuple[Any, ...]:
    name_key = str(item.get("name") or "").lower()
    path_key = str(item.get("relative_path") or "").lower()
    if requested_sort_by == "extension":
        return (str(item.get("extension") or "").lower(), name_key, path_key)
    if requested_sort_by == "modified":
        return (float(item.get("modified_ts") or 0.0), name_key, path_key)
    if requested_sort_by == "size":
        return (int(item.get("size_bytes") or 0), name_key, path_key)
    if requested_sort_by == "metadata":
        return (1 if item.get("metadata") else 0, name_key, path_key)
    return (name_key, path_key)


def _item_from_row(row: sqlite3.Row, include_metadata: bool) -> dict[str, Any]:
    metadata_badges = _json_loads(row["metadata_badges_json"], [])
    metadata_summary = _json_loads(row["metadata_json"], {})
    item: dict[str, Any] = {
        "name": row["name"],
        "path": row["path"],
        "relative_path": row["relative_path"],
        "extension": row["extension"],
        "size_bytes": int(row["size_bytes"]),
        "modified_ts": float(row["modified_ts"]),
    }
    if metadata_badges:
        item["metadata_badges"] = metadata_badges
    if include_metadata and metadata_summary:
        item["metadata"] = metadata_summary
    return item


def _build_index_row(root: str, abs_path: str, runtime: AssetIndexRuntime) -> dict[str, Any] | None:
    try:
        stat = os.stat(abs_path)
    except OSError:
        return None

    extension = Path(abs_path).suffix.lower()
    rel_path = os.path.relpath(abs_path, root)
    metadata_summary = runtime.summarize_metadata(extension, abs_path) if extension in SUPPORTS_METADATA_EXTENSIONS else {}
    metadata_badges = runtime.detect_metadata_badges(extension, abs_path)
    search_text = f"{Path(abs_path).name} {rel_path} {_flatten_to_search_text(metadata_summary)}".lower()
    return {
        "path": abs_path,
        "root": root,
        "name": Path(abs_path).name,
        "relative_path": rel_path,
        "extension": extension,
        "size_bytes": int(stat.st_size),
        "modified_ts": float(stat.st_mtime),
        "metadata_badges_json": _json_dumps(metadata_badges),
        "metadata_json": _json_dumps(metadata_summary),
        "search_text": search_text,
        "content_hash": None,
        "pixel_hash": None,
        "dhash": None,
        "indexed_at": time.time(),
    }


def refresh_asset_index(root: str, runtime: AssetIndexRuntime) -> dict[str, int]:
    normalized_root = os.path.abspath(root)
    indexed = 0
    removed = 0
    seen_paths: set[str] = set()
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        existing = {
            row["path"]: (int(row["size_bytes"]), float(row["modified_ts"]))
            for row in connection.execute("SELECT path, size_bytes, modified_ts FROM assets WHERE root = ?", (normalized_root,))
        }
        for current_dir, dirnames, filenames in os.walk(normalized_root):
            dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
            dirnames.sort(key=str.lower)
            filenames.sort(key=str.lower)
            for filename in filenames:
                abs_path = os.path.abspath(os.path.join(current_dir, filename))
                if not runtime.is_path_within_root(abs_path, normalized_root):
                    continue
                seen_paths.add(abs_path)
                try:
                    stat = os.stat(abs_path)
                except OSError:
                    continue
                cached_signature = existing.get(abs_path)
                if cached_signature == (int(stat.st_size), float(stat.st_mtime)):
                    continue
                row = _build_index_row(normalized_root, abs_path, runtime)
                if row is None:
                    continue
                connection.execute(
                    """
                    INSERT OR REPLACE INTO assets (
                        path, root, name, relative_path, extension, size_bytes, modified_ts,
                        metadata_badges_json, metadata_json, search_text, content_hash, pixel_hash, dhash, indexed_at
                    ) VALUES (
                        :path, :root, :name, :relative_path, :extension, :size_bytes, :modified_ts,
                        :metadata_badges_json, :metadata_json, :search_text, :content_hash, :pixel_hash, :dhash, :indexed_at
                    )
                    """,
                    row,
                )
                indexed += 1

        stale_paths = set(existing).difference(seen_paths)
        for stale_path in stale_paths:
            connection.execute("DELETE FROM assets WHERE path = ?", (stale_path,))
            removed += 1
        connection.execute("INSERT OR REPLACE INTO meta(key, value) VALUES ('last_refresh_at', ?)", (str(time.time()),))
        connection.commit()
    return {"indexed": indexed, "removed": removed}


def index_has_assets(root: str) -> bool:
    normalized_root = os.path.abspath(root)
    db_path = asset_index_cache_file(normalized_root)
    if not db_path.exists():
        return False
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            row = connection.execute("SELECT 1 FROM assets WHERE root = ? LIMIT 1", (normalized_root,)).fetchone()
            return row is not None
    except sqlite3.Error:
        return False


def list_indexed_assets(
    root: str,
    runtime: AssetIndexRuntime,
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
    folder: str = "",
    stats: dict[str, Any] | None = None,
    favorites_only: bool = False,
    collection_id: int | None = None,
    similar_to: str = "",
    nsfw_options: dict[str, Any] | None = None,
) -> list[dict[str, Any]] | None:
    normalized_root = os.path.abspath(root)
    db_path = asset_index_cache_file(normalized_root)
    if not db_path.exists():
        return None
    parsed_query = parse_query(query) if search_in_metadata else None
    if parsed_query is not None and parsed_query.favorites_only:
        favorites_only = True
    rating_filter = parsed_query.rating_filter if parsed_query is not None else set()
    rating_exclude = parsed_query.rating_exclude if parsed_query is not None else set()
    nsfw_filter = parsed_query.nsfw_filter if parsed_query is not None else set()
    nsfw_exclude = parsed_query.nsfw_exclude if parsed_query is not None else set()
    nsfw_settings = nsfw_options or resolve_options()

    request_state = _normalize_request(
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
        folder,
    )
    q = query.strip().lower()
    rows: list[sqlite3.Row]
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            row = connection.execute("SELECT 1 FROM assets WHERE root = ? LIMIT 1", (normalized_root,)).fetchone()
            if row is None:
                return None
            rows = list(connection.execute("SELECT * FROM assets WHERE root = ?", (normalized_root,)))
            favorite_paths = {
                str(fav["path"])
                for fav in connection.execute("SELECT path FROM favorites WHERE root = ?", (normalized_root,))
            }
            ratings = {
                str(item["path"]): str(item["rating"])
                for item in connection.execute("SELECT path, rating FROM ratings WHERE root = ?", (normalized_root,))
            }
            nsfw_scans = {
                str(item["path"]): item
                for item in connection.execute(
                    "SELECT path, size_bytes, modified_ts, evidence_json FROM nsfw_scans WHERE root = ?", (normalized_root,)
                )
            }
            collection_paths: set[str] | None = None
            if collection_id is not None:
                collection_paths = {
                    str(item["path"])
                    for item in connection.execute(
                        "SELECT path FROM collection_items WHERE collection_id = ?", (int(collection_id),)
                    )
                }
    except sqlite3.Error:
        return None

    similarity: dict[str, int] | None = None
    if similar_to:
        similarity = _similarity_distances(normalized_root, similar_to, rows, runtime)

    items: list[dict[str, Any]] = []
    for row in rows:
        is_favorite = str(row["path"]) in favorite_paths
        if favorites_only and not is_favorite:
            continue
        if collection_paths is not None and str(row["path"]) not in collection_paths:
            continue
        rating = ratings.get(str(row["path"]))
        rating_key = rating or "unrated"
        if rating_filter and rating_key not in rating_filter:
            continue
        if rating_key in rating_exclude:
            continue
        if similarity is not None and str(row["path"]) not in similarity:
            continue
        extension = str(row["extension"] or "").lower()
        requested_folder = request_state["requested_folder"]
        if requested_folder:
            rel_parent = os.path.dirname(str(row["relative_path"] or ""))
            if rel_parent != requested_folder and not rel_parent.startswith(requested_folder + os.sep):
                continue
        if request_state["requested_exts"] and extension not in request_state["requested_exts"]:
            continue

        if parsed_query is not None and not parsed_query.is_empty:
            generation = (
                generation_fields(_json_loads(row["metadata_json"], {})) if parsed_query.needs_generation else None
            )
            if not row_matches(parsed_query, dict(row), str(row["search_text"] or ""), generation):
                continue
        elif q and parsed_query is None:
            base_blob = f"{row['name']} {row['relative_path']}".lower()
            if q not in base_blob:
                continue

        size_bytes = int(row["size_bytes"])
        modified_ts = float(row["modified_ts"])
        if request_state["min_size"] is not None and size_bytes < request_state["min_size"]:
            continue
        if request_state["max_size"] is not None and size_bytes > request_state["max_size"]:
            continue
        if request_state["modified_after"] is not None and modified_ts < request_state["modified_after"]:
            continue

        metadata_summary = _json_loads(row["metadata_json"], {})
        if not _metadata_mode_matches(request_state["requested_metadata_mode"], runtime, extension, metadata_summary):
            continue
        nsfw = nsfw_for_row(dict(row), metadata_summary, nsfw_scans.get(str(row["path"])), nsfw_settings)
        nsfw_key = nsfw["rating"] if nsfw else "unscanned"
        if nsfw_filter and nsfw_key not in nsfw_filter:
            continue
        if nsfw_key in nsfw_exclude:
            continue

        metadata_badges = _json_loads(row["metadata_badges_json"], [])
        badge_keys = {badge.get("key") for badge in metadata_badges if isinstance(badge, dict)}
        requested_badges = request_state["requested_badges"]
        if requested_badges:
            if runtime.badge_key_no_tracked_metadata in requested_badges:
                if badge_keys:
                    continue
            elif not requested_badges.issubset(badge_keys):
                continue

        item = _item_from_row(row, include_metadata=include_metadata)
        if is_favorite:
            item["favorite"] = True
        if rating:
            item["rating"] = rating
        if nsfw:
            item["nsfw"] = nsfw
        if similarity is not None:
            # 64-bit dHash: 0 bits apart = identical; express as a 0-100 similarity score.
            item["similarity"] = round(100 * (1 - similarity[str(row["path"])] / 64))
        items.append(item)

    if similarity is not None:
        target_abs = os.path.abspath(similar_to)
        # The source image leads, then closest first, newest first among ties.
        items.sort(key=lambda item: (item["path"] != target_abs, similarity[item["path"]], -item["modified_ts"]))
    else:
        items.sort(
            key=lambda item: _sort_key(request_state["requested_sort_by"], item),
            reverse=request_state["requested_sort_dir"] == "desc",
        )
    if stats is not None:
        stats["total"] = len(items)
    return items[request_state["offset"] : request_state["offset"] + request_state["limit"]]


def upsert_asset_in_index(root: str, path: str, runtime: AssetIndexRuntime) -> None:
    normalized_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    if not runtime.is_path_within_root(abs_path, normalized_root):
        return
    row = _build_index_row(normalized_root, abs_path, runtime)
    if row is None:
        return
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        connection.execute(
            """
            INSERT OR REPLACE INTO assets (
                path, root, name, relative_path, extension, size_bytes, modified_ts,
                metadata_badges_json, metadata_json, search_text, content_hash, pixel_hash, dhash, indexed_at
            ) VALUES (
                :path, :root, :name, :relative_path, :extension, :size_bytes, :modified_ts,
                :metadata_badges_json, :metadata_json, :search_text, :content_hash, :pixel_hash, :dhash, :indexed_at
            )
            """,
            row,
        )
        connection.commit()


def delete_assets_from_index(root: str, paths: list[str]) -> None:
    normalized_root = os.path.abspath(root)
    if not paths:
        return
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        connection.executemany("DELETE FROM assets WHERE path = ?", [(os.path.abspath(path),) for path in paths])
        connection.commit()


def get_duplicate_hashes(root: str, path: str) -> dict[str, Any] | None:
    normalized_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    db_path = asset_index_cache_file(normalized_root)
    if not db_path.exists():
        return None
    try:
        stat = os.stat(abs_path)
    except OSError:
        return None
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            row = connection.execute(
                """
                SELECT size_bytes, modified_ts, content_hash, pixel_hash, dhash
                FROM assets
                WHERE root = ? AND path = ?
                """,
                (normalized_root, abs_path),
            ).fetchone()
    except sqlite3.Error:
        return None
    if row is None:
        return None
    if (int(row["size_bytes"]), float(row["modified_ts"])) != (int(stat.st_size), float(stat.st_mtime)):
        return None
    raw_dhash = row["dhash"]
    try:
        dhash = int(raw_dhash) if raw_dhash not in (None, "") else None
    except (TypeError, ValueError):
        dhash = None
    return {
        "content_hash": row["content_hash"],
        "pixel_hash": row["pixel_hash"],
        "dhash": dhash,
    }


def update_duplicate_hashes(root: str, path: str, hashes: dict[str, Any]) -> None:
    normalized_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    allowed_updates = {key: value for key, value in hashes.items() if key in HASH_COLUMNS and value is not None}
    if "dhash" in allowed_updates:
        allowed_updates["dhash"] = str(allowed_updates["dhash"])
    if not allowed_updates:
        return
    assignments = ", ".join(f"{key} = ?" for key in allowed_updates)
    values = list(allowed_updates.values())
    values.extend([normalized_root, abs_path])
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        connection.execute(
            f"UPDATE assets SET {assignments} WHERE root = ? AND path = ?",
            values,
        )
        connection.commit()


def set_asset_favorite(root: str, path: str, favorite: bool) -> None:
    normalized_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        if favorite:
            connection.execute(
                "INSERT OR REPLACE INTO favorites(path, root, added_at) VALUES (?, ?, ?)",
                (abs_path, normalized_root, time.time()),
            )
        else:
            connection.execute("DELETE FROM favorites WHERE path = ?", (abs_path,))
        connection.commit()


def is_asset_favorite(root: str, path: str) -> bool:
    normalized_root = os.path.abspath(root)
    if not asset_index_cache_file(normalized_root).exists():
        return False
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            row = connection.execute("SELECT 1 FROM favorites WHERE path = ?", (os.path.abspath(path),)).fetchone()
            return row is not None
    except sqlite3.Error:
        return False


RATING_VALUES = {"keep", "reject"}
NSFW_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def nsfw_evidence(metadata_summary: dict[str, Any], scan_row: Any, size_bytes: int, modified_ts: float) -> tuple[list[dict[str, Any]], str] | None:
    """(regions, source) for an image: save-time Bubba metadata first, then a still-fresh viewer scan."""
    embedded = (metadata_summary or {}).get("metadata")
    bubba = embedded.get("bubba_metadata") if isinstance(embedded, dict) else None
    if isinstance(bubba, dict) and bubba.get("content_rating"):
        return list(bubba.get("nsfw_regions") or []), "metadata"
    if scan_row is not None and (int(scan_row["size_bytes"]), float(scan_row["modified_ts"])) == (int(size_bytes), float(modified_ts)):
        return _json_loads(scan_row["evidence_json"], []), "scan"
    return None


def nsfw_for_row(row: dict[str, Any], metadata_summary: dict[str, Any], scan_row: Any, options: dict[str, Any]) -> dict[str, Any] | None:
    """Rating + blur regions for an image row under the current sensitivity; None when not analysed yet."""
    if str(row.get("extension") or "").lower() not in NSFW_IMAGE_EXTENSIONS:
        return None
    evidence = nsfw_evidence(metadata_summary, scan_row, int(row["size_bytes"]), float(row["modified_ts"]))
    if evidence is None:
        return None
    regions, source = evidence
    result = classify(regions, **options)
    return {"rating": result["rating"], "score": result["score"], "regions": result["regions"], "source": source}


def nsfw_for_path(root: str, path: str, metadata_summary: dict[str, Any], options: dict[str, Any] | None = None) -> dict[str, Any] | None:
    normalized_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    try:
        stat = os.stat(abs_path)
    except OSError:
        return None
    scan_row = None
    if asset_index_cache_file(normalized_root).exists():
        try:
            with _connect(normalized_root) as connection:
                _ensure_schema(connection)
                scan_row = connection.execute(
                    "SELECT size_bytes, modified_ts, evidence_json FROM nsfw_scans WHERE path = ?", (abs_path,)
                ).fetchone()
        except sqlite3.Error:
            scan_row = None
    row = {"extension": Path(abs_path).suffix.lower(), "size_bytes": stat.st_size, "modified_ts": stat.st_mtime}
    return nsfw_for_row(row, metadata_summary, scan_row, options or resolve_options())


def pending_nsfw_scans(root: str) -> list[dict[str, Any]]:
    """Images with neither save-time evidence nor a fresh viewer scan, newest first."""
    normalized_root = os.path.abspath(root)
    if not asset_index_cache_file(normalized_root).exists():
        return []
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            "SELECT path, extension, size_bytes, modified_ts, metadata_json FROM assets WHERE root = ?", (normalized_root,)
        ).fetchall()
        scans = {
            str(item["path"]): item
            for item in connection.execute(
                "SELECT path, size_bytes, modified_ts, evidence_json FROM nsfw_scans WHERE root = ?", (normalized_root,)
            )
        }
    pending = []
    for row in rows:
        if str(row["extension"] or "").lower() not in NSFW_IMAGE_EXTENSIONS:
            continue
        evidence = nsfw_evidence(
            _json_loads(row["metadata_json"], {}), scans.get(str(row["path"])), row["size_bytes"], row["modified_ts"]
        )
        if evidence is None:
            pending.append({"path": str(row["path"]), "size_bytes": int(row["size_bytes"]), "modified_ts": float(row["modified_ts"])})
    pending.sort(key=lambda item: item["modified_ts"], reverse=True)
    return pending


def save_nsfw_scans(root: str, results: list[dict[str, Any]]) -> None:
    """Persist viewer scan evidence; each result needs path, size_bytes, modified_ts and regions."""
    if not results:
        return
    normalized_root = os.path.abspath(root)
    now = time.time()
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        connection.executemany(
            "INSERT OR REPLACE INTO nsfw_scans(path, root, size_bytes, modified_ts, evidence_json, analyzed_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            [
                (
                    os.path.abspath(item["path"]),
                    normalized_root,
                    int(item["size_bytes"]),
                    float(item["modified_ts"]),
                    _json_dumps(item["regions"]),
                    now,
                )
                for item in results
            ],
        )
        connection.commit()


def set_asset_ratings(root: str, paths: list[str], rating: str | None) -> None:
    """Mark files keep/reject for cull mode; None clears the rating."""
    if rating is not None and rating not in RATING_VALUES:
        raise ValueError("Rating must be keep, reject or empty.")
    normalized_root = os.path.abspath(root)
    abs_paths = [os.path.abspath(path) for path in paths]
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        if rating:
            now = time.time()
            connection.executemany(
                "INSERT OR REPLACE INTO ratings(path, root, rating, rated_at) VALUES (?, ?, ?, ?)",
                [(path, normalized_root, rating, now) for path in abs_paths],
            )
        else:
            connection.executemany("DELETE FROM ratings WHERE path = ?", [(path,) for path in abs_paths])
        connection.commit()


def get_asset_rating(root: str, path: str) -> str | None:
    normalized_root = os.path.abspath(root)
    if not asset_index_cache_file(normalized_root).exists():
        return None
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            row = connection.execute("SELECT rating FROM ratings WHERE path = ?", (os.path.abspath(path),)).fetchone()
            return str(row["rating"]) if row else None
    except sqlite3.Error:
        return None


def move_asset_favorite(root: str, old_path: str, new_path: str) -> None:
    """Keep favorites, cull ratings and collection membership attached to a file after it is moved or restored."""
    normalized_root = os.path.abspath(root)
    if not asset_index_cache_file(normalized_root).exists():
        return
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        connection.execute(
            "UPDATE OR REPLACE favorites SET path = ? WHERE path = ?",
            (os.path.abspath(new_path), os.path.abspath(old_path)),
        )
        connection.execute(
            "UPDATE OR REPLACE collection_items SET path = ? WHERE path = ?",
            (os.path.abspath(new_path), os.path.abspath(old_path)),
        )
        connection.execute(
            "UPDATE OR REPLACE ratings SET path = ? WHERE path = ?",
            (os.path.abspath(new_path), os.path.abspath(old_path)),
        )
        connection.execute(
            "UPDATE OR REPLACE nsfw_scans SET path = ? WHERE path = ?",
            (os.path.abspath(new_path), os.path.abspath(old_path)),
        )
        connection.commit()


def list_asset_folders(root: str) -> list[dict[str, Any]]:
    normalized_root = os.path.abspath(root)
    root_folder: dict[str, Any] = {"path": "", "label": "root", "depth": 0, "file_count": 0}
    folders = [root_folder]
    if not os.path.isdir(normalized_root):
        return folders

    by_path: dict[str, dict[str, Any]] = {"": root_folder}
    for current_dir, dirnames, filenames in os.walk(normalized_root):
        dirnames[:] = [name for name in dirnames if name not in EXCLUDED_DIRS]
        dirnames.sort(key=str.lower)
        if os.path.abspath(current_dir) == normalized_root:
            root_folder["file_count"] += len(filenames)
            continue
        rel_path = os.path.relpath(current_dir, normalized_root)
        folder = {
            "path": rel_path,
            "label": os.path.basename(current_dir),
            "depth": len(Path(rel_path).parts),
            "file_count": len(filenames),
        }
        by_path[rel_path] = folder
        folders.append(folder)

    # Roll each folder's direct file count up into its ancestors so counts are recursive,
    # matching what the media grid shows when a folder is selected. Deepest folders first.
    for folder in sorted(folders[1:], key=lambda item: item["depth"], reverse=True):
        parent = by_path.get(os.path.dirname(folder["path"]), root_folder)
        parent["file_count"] += folder["file_count"]
    return folders


SIMILAR_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff"}
SIMILAR_MAX_DISTANCE = 20  # of 64 dHash bits; ~69% similarity and up
SIMILAR_MAX_NEW_HASHES = 2500  # bound first-run work; later runs reuse cached hashes


def _similarity_distances(root: str, target_path: str, rows: list[sqlite3.Row], runtime: AssetIndexRuntime) -> dict[str, int]:
    """Hamming distance from the target image's dHash to every visually close image in the root."""
    from PIL import Image

    from services.asset_viewer_duplicates import _dhash

    target_abs = os.path.abspath(target_path)
    hashes: dict[str, int] = {}
    pending: list[str] = []
    for row in rows:
        path = str(row["path"])
        if str(row["extension"] or "").lower() not in SIMILAR_IMAGE_EXTENSIONS:
            continue
        if row["dhash"]:
            try:
                hashes[path] = int(row["dhash"])
                continue
            except ValueError:
                pass
        pending.append(path)

    if target_abs in pending:
        pending.remove(target_abs)
        pending.insert(0, target_abs)
    computed: dict[str, int] = {}
    for path in pending[:SIMILAR_MAX_NEW_HASHES]:
        value = _dhash(path, image_module=Image)
        if value is not None:
            hashes[path] = value
            computed[path] = value
    if computed:
        try:
            with _connect(root) as connection:
                connection.executemany(
                    "UPDATE assets SET dhash = ? WHERE root = ? AND path = ?",
                    [(str(value), root, path) for path, value in computed.items()],
                )
                connection.commit()
        except sqlite3.Error:
            pass

    target_hash = hashes.get(target_abs)
    if target_hash is None:
        return {}
    distances = {}
    for path, value in hashes.items():
        distance = (value ^ target_hash).bit_count()
        if distance <= SIMILAR_MAX_DISTANCE:
            distances[path] = distance
    return distances


def _ensure_collection_schema(connection: sqlite3.Connection) -> None:
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS collections (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            root TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at REAL NOT NULL,
            UNIQUE(root, name)
        )
        """
    )
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS collection_items (
            collection_id INTEGER NOT NULL,
            path TEXT NOT NULL,
            added_at REAL NOT NULL,
            PRIMARY KEY (collection_id, path)
        )
        """
    )


def _clean_collection_name(name: str) -> str:
    clean = " ".join(str(name or "").split())[:80]
    if not clean:
        raise ValueError("Collection name is required.")
    return clean


def list_collections(root: str) -> list[dict[str, Any]]:
    normalized_root = os.path.abspath(root)
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        rows = connection.execute(
            """
            SELECT c.id, c.name, COUNT(a.path) AS item_count
            FROM collections c
            LEFT JOIN collection_items i ON i.collection_id = c.id
            LEFT JOIN assets a ON a.path = i.path AND a.root = c.root
            WHERE c.root = ?
            GROUP BY c.id
            ORDER BY LOWER(c.name)
            """,
            (normalized_root,),
        ).fetchall()
    return [{"id": int(row["id"]), "name": row["name"], "count": int(row["item_count"])} for row in rows]


def create_collection(root: str, name: str) -> dict[str, Any]:
    normalized_root = os.path.abspath(root)
    clean = _clean_collection_name(name)
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        existing = connection.execute(
            "SELECT id FROM collections WHERE root = ? AND name = ?", (normalized_root, clean)
        ).fetchone()
        if existing:
            return {"id": int(existing["id"]), "name": clean, "created": False}
        cursor = connection.execute(
            "INSERT INTO collections(root, name, created_at) VALUES (?, ?, ?)", (normalized_root, clean, time.time())
        )
        connection.commit()
        return {"id": int(cursor.lastrowid), "name": clean, "created": True}


def _require_collection(connection: sqlite3.Connection, root: str, collection_id: int) -> None:
    row = connection.execute("SELECT 1 FROM collections WHERE id = ? AND root = ?", (int(collection_id), root)).fetchone()
    if row is None:
        raise LookupError("Collection not found.")


def update_collection_items(root: str, collection_id: int, paths: list[str], add: bool) -> int:
    normalized_root = os.path.abspath(root)
    abs_paths = [os.path.abspath(path) for path in paths]
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        _require_collection(connection, normalized_root, collection_id)
        if add:
            connection.executemany(
                "INSERT OR IGNORE INTO collection_items(collection_id, path, added_at) VALUES (?, ?, ?)",
                [(int(collection_id), path, time.time()) for path in abs_paths],
            )
        else:
            connection.executemany(
                "DELETE FROM collection_items WHERE collection_id = ? AND path = ?",
                [(int(collection_id), path) for path in abs_paths],
            )
        connection.commit()
    return len(abs_paths)


def rename_collection(root: str, collection_id: int, name: str) -> None:
    normalized_root = os.path.abspath(root)
    clean = _clean_collection_name(name)
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        _require_collection(connection, normalized_root, collection_id)
        connection.execute("UPDATE collections SET name = ? WHERE id = ?", (clean, int(collection_id)))
        connection.commit()


def delete_collection(root: str, collection_id: int) -> None:
    normalized_root = os.path.abspath(root)
    with _connect(normalized_root) as connection:
        _ensure_schema(connection)
        _require_collection(connection, normalized_root, collection_id)
        connection.execute("DELETE FROM collection_items WHERE collection_id = ?", (int(collection_id),))
        connection.execute("DELETE FROM collections WHERE id = ?", (int(collection_id),))
        connection.commit()


def indexed_rows_with_metadata(root: str, like: str = "") -> list[dict[str, Any]]:
    """Indexed rows with parsed metadata summaries; `like` pre-filters on search text (lower-case substring)."""
    normalized_root = os.path.abspath(root)
    if not asset_index_cache_file(normalized_root).exists():
        return []
    sql = "SELECT path, name, relative_path, modified_ts, metadata_json FROM assets WHERE root = ?"
    params: list[Any] = [normalized_root]
    if like:
        sql += " AND instr(search_text, ?) > 0"
        params.append(like.lower())
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            rows = connection.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []
    return [
        {
            "path": row["path"],
            "name": row["name"],
            "relative_path": row["relative_path"],
            "modified_ts": float(row["modified_ts"]),
            "metadata": _json_loads(row["metadata_json"], {}),
        }
        for row in rows
    ]


def asset_facets(root: str, folder: str = "") -> dict[str, Any] | None:
    normalized_root = os.path.abspath(root)
    if not asset_index_cache_file(normalized_root).exists():
        return None
    requested_folder = os.path.normpath(folder) if folder else ""
    try:
        with _connect(normalized_root) as connection:
            _ensure_schema(connection)
            rows = connection.execute(
                "SELECT relative_path, modified_ts, metadata_json FROM assets WHERE root = ?", (normalized_root,)
            ).fetchall()
    except sqlite3.Error:
        return None
    prepared = []
    for row in rows:
        if requested_folder:
            rel_parent = os.path.dirname(str(row["relative_path"] or ""))
            if rel_parent != requested_folder and not rel_parent.startswith(requested_folder + os.sep):
                continue
        prepared.append(
            {
                "modified_ts": row["modified_ts"],
                "generation": generation_fields(_json_loads(row["metadata_json"], {})),
            }
        )
    return build_facets(prepared)
