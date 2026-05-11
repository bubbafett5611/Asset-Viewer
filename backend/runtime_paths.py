from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from hashlib import sha256


APP_NAME = "Bubba Media Viewer"
APP_DIR_NAME = "bubba-media-viewer"

DATA_DIR_ENV = "BUBBA_ASSET_VIEWER_DATA_DIR"
FRONTEND_DIR_ENV = "BUBBA_ASSET_VIEWER_FRONTEND_DIR"
SETTINGS_FILE_ENV = "BUBBA_ASSET_VIEWER_SETTINGS_FILE"


def is_packaged() -> bool:
    return bool(getattr(sys, "frozen", False))


def project_root() -> Path:
    return Path(__file__).resolve().parents[1]


def resource_root() -> Path:
    bundled_root = getattr(sys, "_MEIPASS", None)
    if bundled_root:
        return Path(bundled_root)
    if is_packaged():
        return Path(sys.executable).resolve().parent
    return project_root()


def user_data_dir() -> Path:
    configured_dir = os.environ.get(DATA_DIR_ENV)
    if configured_dir:
        return Path(configured_dir).expanduser()

    appdata_dir = os.environ.get("APPDATA")
    if appdata_dir:
        return Path(appdata_dir) / APP_NAME

    return Path.home() / ".config" / APP_DIR_NAME


def frontend_root() -> Path:
    configured_dir = os.environ.get(FRONTEND_DIR_ENV)
    if configured_dir:
        return Path(configured_dir).expanduser()
    return resource_root() / "frontend"


def uses_user_data_for_cache() -> bool:
    return is_packaged() or bool(os.environ.get(DATA_DIR_ENV))


def cache_dir() -> Path:
    return user_data_dir() / "cache"


def report_cache_dir(root: str) -> Path:
    normalized_root = str(Path(root).expanduser().resolve()).casefold()
    root_key = sha256(normalized_root.encode("utf-8")).hexdigest()[:16]
    return cache_dir() / "reports" / root_key


def report_cache_file(root: str, filename: str) -> Path:
    if Path(filename).name != filename:
        raise ValueError("Report cache filename must not contain path separators.")
    return report_cache_dir(root) / filename


def bundled_settings_file() -> Path:
    root = resource_root()
    candidates = [
        root / "settings.json",
        root / "settings.example.json",
        root / "settings.json" / "settings.example.json",
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return candidates[0]


def settings_file() -> Path:
    configured_file = os.environ.get(SETTINGS_FILE_ENV)
    if configured_file:
        return Path(configured_file).expanduser()
    if is_packaged():
        return user_data_dir() / "settings.json"
    return project_root() / "settings.json"


def ensure_settings_file(settings_path: Path | None = None) -> Path:
    resolved_settings_path = settings_path or settings_file()
    if resolved_settings_path.exists():
        return resolved_settings_path

    if not is_packaged():
        return resolved_settings_path

    default_settings_path = bundled_settings_file()
    resolved_settings_path.parent.mkdir(parents=True, exist_ok=True)
    if default_settings_path.exists():
        shutil.copyfile(default_settings_path, resolved_settings_path)
    else:
        resolved_settings_path.write_text("{}\n", encoding="utf-8")
    return resolved_settings_path
