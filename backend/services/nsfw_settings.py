"""Current NSFW classification options from the viewer settings."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from services.nsfw_detect import PRESETS, default_model_dir, resolve_options

CUSTOM_EXPLICIT_ONLY_BELOW = 40  # custom sensitivity under this counts only the tagger's explicit rating


def options_for(preset: str, sensitivity: int, see_through: bool) -> dict[str, Any]:
    if preset in PRESETS:
        return resolve_options(preset)
    options = resolve_options("strict", sensitivity=sensitivity, see_through=see_through)
    options["tagger"] = "explicit" if sensitivity < CUSTOM_EXPLICIT_ONLY_BELOW else "nudity"
    return options


def current_nsfw_options() -> dict[str, Any]:
    from settings_model import Settings

    viewer = Settings().viewer
    return options_for(str(viewer.nsfw_preset), int(viewer.nsfw_sensitivity), bool(viewer.nsfw_see_through))


def current_model_dir() -> Path:
    from settings_model import Settings

    configured = str(Settings().viewer.nsfw_model_dir or "").strip()
    return Path(configured).expanduser() if configured else default_model_dir()
