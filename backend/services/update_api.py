from __future__ import annotations

import os
from typing import Any

from flask import jsonify
import requests

from runtime_paths import project_root


GITHUB_REPO_ENV = "BUBBA_ASSET_VIEWER_RELEASE_REPO"
GITHUB_REPO_DEFAULT = "bubbafett5611/Asset-Viewer"
GITHUB_API_TIMEOUT_SECONDS = 6


def _read_project_version() -> str:
    pyproject_path = project_root() / "pyproject.toml"
    if not pyproject_path.exists():
        return os.environ.get("BUBBA_ASSET_VIEWER_VERSION", "0.0.0")

    try:
        import tomllib

        with open(pyproject_path, "rb") as handle:
            data = tomllib.load(handle)
        project = data.get("project")
        if isinstance(project, dict):
            version = project.get("version")
            if isinstance(version, str) and version.strip():
                return version.strip()
    except Exception:
        pass

    return os.environ.get("BUBBA_ASSET_VIEWER_VERSION", "0.0.0")


def _releases_latest_url(repo: str) -> str:
    return f"https://api.github.com/repos/{repo}/releases/latest"


def _release_page_url(repo: str) -> str:
    return f"https://github.com/{repo}/releases"


def _fetch_latest_release(repo: str) -> dict[str, Any] | None:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "Bubba-Media-Viewer-UpdateCheck",
    }
    try:
        response = requests.get(_releases_latest_url(repo), headers=headers, timeout=GITHUB_API_TIMEOUT_SECONDS)
    except requests.RequestException:
        return None
    if response.status_code >= 400:
        return None
    try:
        payload = response.json()
    except ValueError:
        return None
    if not isinstance(payload, dict):
        return None
    return payload


def api_update_latest_handler():
    repo = os.environ.get(GITHUB_REPO_ENV, GITHUB_REPO_DEFAULT)
    current_version = _read_project_version()

    latest_payload = _fetch_latest_release(repo)
    if not latest_payload:
        return jsonify(
            {
                "repo": repo,
                "current_version": current_version,
                "latest_version": None,
                "latest_tag": None,
                "latest_name": None,
                "latest_url": None,
                "published_at": None,
            }
        )

    tag_name = latest_payload.get("tag_name")
    latest_version = str(tag_name or "").strip()
    if latest_version.lower().startswith("v"):
        latest_version = latest_version[1:]

    return jsonify(
        {
            "repo": repo,
            "current_version": current_version,
            "latest_version": latest_version or None,
            "latest_tag": tag_name,
            "latest_name": latest_payload.get("name"),
            "latest_url": latest_payload.get("html_url"),
            "published_at": latest_payload.get("published_at"),
        }
    )


def api_app_info_handler():
    repo = os.environ.get(GITHUB_REPO_ENV, GITHUB_REPO_DEFAULT)
    return jsonify(
        {
            "repo": repo,
            "current_version": _read_project_version(),
            "release_page_url": _release_page_url(repo),
        }
    )
