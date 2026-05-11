from __future__ import annotations

import logging
import threading
from pathlib import Path

from asset_viewer import AssetRoot

from settings_model import DEFAULT_SETTINGS_FILE, Settings

SETTINGS_FILE = DEFAULT_SETTINGS_FILE

logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
logger = logging.getLogger('bubba.server')


def _asset_roots_from_settings(settings: Settings) -> list[AssetRoot]:
    return [AssetRoot(key=Path(path).name, label=Path(path).name, path=path) for path in settings.general.asset_roots]


def load_asset_roots() -> list[AssetRoot]:
    return _asset_roots_from_settings(Settings())


ASSET_ROOTS = load_asset_roots()
_asset_roots_lock = threading.Lock()


def _get_asset_roots_snapshot() -> list[AssetRoot]:
    with _asset_roots_lock:
        return list(ASSET_ROOTS)


def _set_asset_roots(new_roots: list[AssetRoot]) -> None:
    global ASSET_ROOTS
    with _asset_roots_lock:
        ASSET_ROOTS = list(new_roots)
