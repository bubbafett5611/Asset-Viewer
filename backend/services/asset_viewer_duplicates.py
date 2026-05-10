from __future__ import annotations

import hashlib
from typing import Any, Callable

from .duplicate_scan_tasks import DuplicateScanCancelled


def _sha256_file(path: str, chunk_size: int = 1024 * 1024) -> str | None:
    try:
        digest = hashlib.sha256()
        with open(path, "rb") as handle:
            for chunk in iter(lambda: handle.read(chunk_size), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def _pixel_hash(path: str, image_module=None) -> str | None:
    if image_module is None:
        return None
    try:
        with image_module.open(path) as image_handle:
            image = image_handle.convert("RGBA")
            digest = hashlib.sha256()
            digest.update(str(image.size).encode("ascii"))
            digest.update(image.tobytes())
            return digest.hexdigest()
    except Exception:
        return None


def _dhash(path: str, image_module=None, hash_size: int = 8) -> int | None:
    if image_module is None:
        return None
    try:
        with image_module.open(path) as image_handle:
            image = image_handle.convert("L").resize((hash_size + 1, hash_size), image_module.Resampling.LANCZOS)
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
    build_asset_item_fn,
    distance: int | None = None,
) -> None:
    assets: list[dict[str, Any]] = []
    for path in sorted(paths, key=lambda item: __import__("os").path.relpath(item, root).lower()):
        try:
            assets.append(build_asset_item_fn(path, root, include_metadata=False))
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


def _report_progress(progress_callback, stage: str, completed: int, total: int, percent: int, message: str) -> None:
    if progress_callback is None:
        return
    progress_callback(
        {
            'stage': stage,
            'completed': completed,
            'total': total,
            'percent': max(0, min(int(percent), 100)),
            'message': message,
        }
    )


def _ensure_not_cancelled(cancel_check: Callable[[], bool] | None) -> None:
    if cancel_check is not None and cancel_check():
        raise DuplicateScanCancelled('Duplicate scan cancelled')


def _hash_duplicate_assets(assets: list[dict[str, Any]], near_duplicate_extensions: set[str], image_module, include_near: bool, progress_callback, cancel_check):
    content_hashes: dict[str, list[str]] = {}
    pixel_hashes: dict[str, list[str]] = {}
    content_hash_by_path: dict[str, str] = {}
    pixel_hash_by_path: dict[str, str] = {}
    dhash_by_path: dict[str, int] = {}

    for index, asset in enumerate(assets, start=1):
        _ensure_not_cancelled(cancel_check)
        path = str(asset.get('path') or '')
        extension = str(asset.get('extension') or '').lower()
        if not path:
            continue

        content_hash = _sha256_file(path)
        if content_hash:
            content_hash_by_path[path] = content_hash
            content_hashes.setdefault(content_hash, []).append(path)

        if extension in near_duplicate_extensions:
            pixel_hash = _pixel_hash(path, image_module=image_module)
            if pixel_hash:
                pixel_hash_by_path[path] = pixel_hash
                pixel_hashes.setdefault(pixel_hash, []).append(path)
            if include_near:
                dhash_value = _dhash(path, image_module=image_module)
                if dhash_value is not None:
                    dhash_by_path[path] = dhash_value

        if index == len(assets) or index == 1 or index % 10 == 0:
            percent = 5 + round((index / max(len(assets), 1)) * 65)
            _report_progress(progress_callback, 'hashing', index, len(assets), percent, f'Checked {index} of {len(assets)} file(s)...')

    return content_hashes, pixel_hashes, content_hash_by_path, pixel_hash_by_path, dhash_by_path


def _append_hash_groups(groups, content_hashes, pixel_hashes, content_hash_by_path, normalized_root, build_asset_item_fn, progress_callback, cancel_check):
    _report_progress(progress_callback, 'grouping', 0, 0, 72, 'Grouping exact and same-pixel matches...')
    for key, paths in content_hashes.items():
        _ensure_not_cancelled(cancel_check)
        if len(paths) > 1:
            _append_duplicate_group(groups, 'exact', key, paths, normalized_root, build_asset_item_fn)

    for key, paths in pixel_hashes.items():
        _ensure_not_cancelled(cancel_check)
        if len(paths) > 1 and len({content_hash_by_path.get(path, '') for path in paths}) > 1:
            _append_duplicate_group(groups, 'pixel', key, paths, normalized_root, build_asset_item_fn)


def _append_near_groups(groups, dhash_by_path, pixel_hash_by_path, near_threshold: int, normalized_root: str, build_asset_item_fn, progress_callback, cancel_check):
    if len(dhash_by_path) <= 1:
        _report_progress(progress_callback, 'grouping', 0, 0, 95, 'Finishing duplicate groups...')
        return

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
        _ensure_not_cancelled(cancel_check)
        for right in paths[left_index + 1 :]:
            _ensure_not_cancelled(cancel_check)
            if pixel_hash_by_path.get(left) and pixel_hash_by_path.get(left) == pixel_hash_by_path.get(right):
                compared_pairs += 1
                continue
            distance = _hamming_distance(dhash_by_path[left], dhash_by_path[right])
            if distance <= near_threshold:
                union(left, right, distance)
            compared_pairs += 1
            if compared_pairs == 1 or compared_pairs == total_pairs or compared_pairs % 1000 == 0:
                percent = 72 + round((compared_pairs / total_pairs) * 23)
                _report_progress(
                    progress_callback,
                    'comparing',
                    compared_pairs,
                    total_pairs,
                    percent,
                    f'Compared {compared_pairs} of {total_pairs} image pair(s)...',
                )

    near_groups: dict[str, list[str]] = {}
    for path in paths:
        near_groups.setdefault(find(path), []).append(path)

    for root_key, paths_in_group in near_groups.items():
        if len(paths_in_group) < 2:
            continue
        if len({pixel_hash_by_path.get(path, '') for path in paths_in_group}) <= 1:
            continue
        _append_duplicate_group(
            groups,
            'near',
            f'dhash:{root_key}',
            paths_in_group,
            normalized_root,
            build_asset_item_fn,
            distance=group_distance.get(find(root_key), 0),
        )


def _build_duplicate_summary(groups: list[dict[str, Any]], assets: list[dict[str, Any]], include_near: bool) -> dict[str, Any]:
    return {
        'groups': len(groups),
        'assets': sum(int(group.get('count') or 0) for group in groups),
        'exact_groups': sum(1 for group in groups if group.get('kind') == 'exact'),
        'pixel_groups': sum(1 for group in groups if group.get('kind') == 'pixel'),
        'near_groups': sum(1 for group in groups if group.get('kind') == 'near'),
        'scanned_assets': len(assets),
        'near_enabled': bool(include_near),
    }


def scan_duplicate_assets(
    root: str,
    scan_assets_fn,
    build_asset_item_fn,
    near_duplicate_extensions: set[str],
    image_module=None,
    include_near: bool = False,
    near_threshold: int = 6,
    limit: int = 5000,
    progress_callback: Callable[[dict[str, Any]], None] | None = None,
    cancel_check: Callable[[], bool] | None = None,
) -> dict[str, Any]:
    import os

    normalized_root = os.path.abspath(root)
    limit = max(1, min(int(limit), 10000))
    near_threshold = max(0, min(int(near_threshold), 16))

    _report_progress(progress_callback, 'collecting', 0, 0, 2, 'Collecting files...')
    _ensure_not_cancelled(cancel_check)
    assets = scan_assets_fn(
        root=normalized_root,
        limit=limit,
        include_metadata=False,
        sort_by="name",
        sort_dir="asc",
    )
    _ensure_not_cancelled(cancel_check)
    _report_progress(progress_callback, 'hashing', 0, len(assets), 5, f'Scanning {len(assets)} file(s)...')

    content_hashes, pixel_hashes, content_hash_by_path, pixel_hash_by_path, dhash_by_path = _hash_duplicate_assets(
        assets,
        near_duplicate_extensions,
        image_module,
        include_near,
        progress_callback,
        cancel_check,
    )

    groups: list[dict[str, Any]] = []
    _append_hash_groups(
        groups,
        content_hashes,
        pixel_hashes,
        content_hash_by_path,
        normalized_root,
        build_asset_item_fn,
        progress_callback,
        cancel_check,
    )
    if include_near:
        _append_near_groups(
            groups,
            dhash_by_path,
            pixel_hash_by_path,
            near_threshold,
            normalized_root,
            build_asset_item_fn,
            progress_callback,
            cancel_check,
        )
    else:
        _report_progress(progress_callback, 'grouping', 0, 0, 95, 'Finishing duplicate groups...')

    groups.sort(key=lambda group: (str(group.get("kind") or ""), -int(group.get("count") or 0), str(group.get("key") or "")))
    summary = _build_duplicate_summary(groups, assets, include_near)
    _report_progress(progress_callback, 'complete', len(groups), len(groups), 100, f'Found {len(groups)} duplicate group(s).')
    return {"groups": groups, "summary": summary}
