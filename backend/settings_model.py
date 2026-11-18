from __future__ import annotations

import sys
from enum import Enum
from pathlib import Path
from typing import Any

# StrEnum was added in Python 3.11; provide fallback for Python 3.10
if sys.version_info >= (3, 11):
	from enum import StrEnum
else:
	class StrEnum(str, Enum):
		"""Enum where members are also strings; fallback for Python < 3.11."""
		def __str__(self):
			return str(self.value)

from pydantic import BaseModel, Field
from pydantic_settings import (
	BaseSettings,
	JsonConfigSettingsSource,
	PydanticBaseSettingsSource,
	SettingsConfigDict,
)

from runtime_paths import ensure_settings_file, settings_file


DEFAULT_SETTINGS_FILE = ensure_settings_file(settings_file())


class Density(StrEnum):
	compact = "compact"
	comfortable = "comfortable"
	large = "large"


class NsfwPreset(StrEnum):
	cautious = "cautious"
	balanced = "balanced"
	strict = "strict"
	custom = "custom"


class NsfwBlurStyle(StrEnum):
	regions = "regions"
	image = "image"


class GeneralSettings(BaseModel):
	asset_roots: list[str] = Field(default_factory=list, description="Folders scanned by the media viewer.")


class ViewerSettings(BaseModel):
	density: Density = Field(default=Density.comfortable, description="Default media card density.")
	preview: bool = Field(default=False, title="Blur All", description="Blur all media thumbnails.")
	nsfw_blur: bool = Field(
		default=True, title="Blur NSFW only", description="Blur images rated NSFW (when Blur All is off)."
	)
	nsfw_blur_style: NsfwBlurStyle = Field(
		default=NsfwBlurStyle.regions,
		title="NSFW blur style",
		description="Blur only the detected regions, or the whole image.",
	)
	nsfw_preset: NsfwPreset = Field(
		default=NsfwPreset.strict,
		title="NSFW preset",
		description="Cautious blurs the most; Strict only nudity. Custom keeps your slider and switch.",
	)
	nsfw_sensitivity: int = Field(
		default=33, ge=0, le=100, title="NSFW sensitivity", description="0 = least sensitive, 100 = most."
	)
	nsfw_see_through: bool = Field(
		default=False, title="See-through counts as NSFW", description="Treat see-through clothing as NSFW."
	)
	nsfw_model_dir: str = Field(
		default="",
		title="NSFW model folder",
		description="Folder with 640m.onnx (+ wd-vit-tagger-v3.onnx). Empty = %APPDATA%\\Bubba Media Viewer\\models\\nsfw.",
	)


class UpdateSettings(BaseModel):
	auto_check_enabled: bool = Field(
		default=True,
		title="Automatic Update Checks",
		description="Automatically check for updates when the app starts.",
	)


class IntegrationSettings(BaseModel):
	comfyui_url: str = Field(
		default="http://127.0.0.1:8188",
		title="ComfyUI URL",
		description="Where Re-queue in ComfyUI sends workflows (the address ComfyUI is listening on).",
	)
	comfyui_user_dir: str = Field(
		default="",
		title="ComfyUI user folder",
		description=(
			"ComfyUI's user folder (contains bubba_nodes/). Send to… reuses the Discord webhook profiles and "
			"Immich settings saved there by Bubba Nodes, e.g. C:\\StabilityMatrix\\Data\\Packages\\ComfyUI\\user."
		),
	)


class Settings(BaseSettings):
	model_config = SettingsConfigDict(
		env_prefix="BUBBA_ASSET_VIEWER_",
		extra="ignore",
		json_file=DEFAULT_SETTINGS_FILE,
		json_file_encoding="utf-8",
	)

	general: GeneralSettings = Field(default_factory=GeneralSettings, title="General")
	viewer: ViewerSettings = Field(default_factory=ViewerSettings, title="Viewer")
	updates: UpdateSettings = Field(default_factory=UpdateSettings, title="Updates")
	integrations: IntegrationSettings = Field(default_factory=IntegrationSettings, title="Integrations")

	@classmethod
	def settings_customise_sources(
		cls,
		settings_cls: type[BaseSettings],
		init_settings: PydanticBaseSettingsSource,
		env_settings: PydanticBaseSettingsSource,
		dotenv_settings: PydanticBaseSettingsSource,
		file_secret_settings: PydanticBaseSettingsSource,
	) -> tuple[PydanticBaseSettingsSource, ...]:
		json_settings = JsonConfigSettingsSource(settings_cls)
		return (init_settings, env_settings, dotenv_settings, json_settings, file_secret_settings)


def save_settings(settings_path: Path, settings: Settings) -> None:
	settings_path.parent.mkdir(parents=True, exist_ok=True)
	settings_path.write_text(settings.model_dump_json(indent=2) + "\n", encoding="utf-8")


def validate_settings_payload(payload: dict[str, Any]) -> Settings:
	return Settings.model_validate(payload)
