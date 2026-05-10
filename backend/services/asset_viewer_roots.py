from __future__ import annotations

import logging
import os
import re
from pathlib import Path

ALLOWED_UPLOAD_IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"}


def safe_real_path(path: str) -> str:
    return os.path.normcase(os.path.realpath(path))


def is_path_within_root(path: str, root: str) -> bool:
    path_real = safe_real_path(path)
    root_real = safe_real_path(root)
    try:
        return os.path.commonpath([path_real, root_real]) == root_real
    except ValueError:
        return False


def discover_asset_roots(logger: logging.Logger) -> list[tuple[str, str, str]]:
    roots: list[tuple[str, str, str]] = []
    seen: set[str] = set()

    try:
        import folder_paths
    except Exception as error:
        logger.info("Could not import folder_paths: %s", error)
        folder_paths = None

    if folder_paths is not None:
        for key, label, getter_name in [
            ("input", "Comfy Input", "get_input_directory"),
            ("output", "Comfy Output", "get_output_directory"),
        ]:
            try:
                getter = getattr(folder_paths, getter_name)
                folder = getter()
                logger.debug("%s returned: %s", getter_name, folder)
            except Exception as error:
                logger.warning("Error calling %s: %s", getter_name, error)
                folder = None
            if not folder:
                continue
            real = safe_real_path(folder)
            if real in seen or not os.path.isdir(folder):
                logger.debug("Skipping folder (already seen or not a dir): %s", folder)
                continue
            seen.add(real)
            roots.append((key, label, os.path.abspath(folder)))

    if not roots:
        fallback = os.getcwd()
        logger.info("No asset roots found, using fallback: %s", fallback)
        roots.append(("cwd", "Current Directory", os.path.abspath(fallback)))

    logger.info("Discovered %d asset roots.", len(roots))
    return roots


def resolve_requested_root(requested_root: str | None, allowed_roots: list[tuple[str, str, str]]) -> str:
    if not allowed_roots:
        raise ValueError("No asset roots available.")

    if not requested_root:
        return allowed_roots[0][2]

    requested = requested_root.strip()
    if not requested:
        return allowed_roots[0][2]

    root_by_path = {os.path.abspath(path): (key, label, path) for key, label, path in allowed_roots}
    requested_abs = os.path.abspath(requested)
    if requested_abs in root_by_path:
        return requested_abs

    for key, _, path in allowed_roots:
        if requested == key:
            return path

    raise ValueError("Requested root is not allowed.")


def resolve_requested_file(requested_path: str | None, allowed_roots: list[tuple[str, str, str]]) -> str:
    if not allowed_roots:
        raise ValueError("No asset roots available.")

    raw = str(requested_path or "").strip()
    if not raw:
        raise ValueError("Missing file path.")

    normalized = os.path.abspath(raw)
    if not os.path.isfile(normalized):
        raise FileNotFoundError("File does not exist.")

    for _, _, root_path in allowed_roots:
        if is_path_within_root(normalized, root_path):
            return normalized

    raise PermissionError("Requested file is outside allowed roots.")


def find_root_for_path(path: str, allowed_roots: list[tuple[str, str, str]]) -> tuple[str, str, str] | None:
    normalized = os.path.abspath(path)
    for root in allowed_roots:
        if is_path_within_root(normalized, root[2]):
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
