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


class GeneralSettings(BaseModel):
	asset_roots: list[str] = Field(default_factory=list, description="Folders scanned by the media viewer.")


class ViewerSettings(BaseModel):
	density: Density = Field(default=Density.comfortable, description="Default media card density.")
	preview: bool = Field(default=False, title="Blur All", description="Blur all media thumbnails.")


class UpdateSettings(BaseModel):
	auto_check_enabled: bool = Field(
		default=True,
		title="Automatic Update Checks",
		description="Automatically check for updates when the app starts.",
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
