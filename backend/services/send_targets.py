"""Send media to the Discord webhooks and Immich server configured in Bubba Nodes.

Configuration is read from ComfyUI's user folder (setting `integrations.comfyui_user_dir`):
    bubba_nodes/discord/webhook_profiles.json   {"profile name": "https://discord.com/api/webhooks/..."}
    bubba_nodes/immich/settings.json            {"url": "https://host/api", "api_key": "..."}
Webhook URLs and API keys never leave the backend; the UI only sees profile names and the Immich host.
"""

from __future__ import annotations

import hashlib
import json
import os
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

DISCORD_MAX_FILES_PER_MESSAGE = 10
DISCORD_MAX_FILE_BYTES = 10 * 1024 * 1024
DISCORD_MAX_MESSAGE_LENGTH = 2000
DISCORD_MAX_FIELD_LENGTH = 1024
MAX_SEND_FILES = 100
CONTENT_TYPES = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp", ".gif": "image/gif", ".mp4": "video/mp4"}


class SendError(RuntimeError):
    """A user-facing send failure. `status` is 400 for setup problems and 502 when the service fails."""

    def __init__(self, message: str, status: int = 400):
        super().__init__(message)
        self.status = status


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # never forward credentials to another URL
        return None


def _open(request: urllib.request.Request, timeout: float):
    return urllib.request.build_opener(_NoRedirect).open(request, timeout=timeout)


def bubba_config_dir(comfyui_user_dir: str) -> Path:
    base = str(comfyui_user_dir or "").strip()
    if not base:
        raise SendError("Set the ComfyUI user folder in Settings > Integrations to use Send to….")
    return Path(base).expanduser() / "bubba_nodes"


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def discord_profiles(config_dir: Path) -> dict[str, str]:
    payload = _read_json(config_dir / "discord" / "webhook_profiles.json")
    if not isinstance(payload, dict):
        return {}
    return {str(name): str(url) for name, url in payload.items() if isinstance(name, str) and isinstance(url, str) and url}


def immich_config(config_dir: Path) -> dict[str, str]:
    payload = _read_json(config_dir / "immich" / "settings.json")
    if not isinstance(payload, dict) or not payload.get("url") or not payload.get("api_key"):
        return {}
    return {"url": str(payload["url"]).rstrip("/"), "api_key": str(payload["api_key"])}


def list_targets(comfyui_user_dir: str) -> dict[str, Any]:
    """Destinations the UI may offer. Secrets are never included."""
    try:
        config_dir = bubba_config_dir(comfyui_user_dir)
    except SendError as error:
        return {"configured": False, "error": str(error), "targets": []}
    targets = [
        {"id": f"discord:{name}", "kind": "discord", "label": f"Discord · {name}", "profile": name}
        for name in sorted(discord_profiles(config_dir), key=str.casefold)
    ]
    immich = immich_config(config_dir)
    if immich:
        host = urllib.parse.urlsplit(immich["url"]).hostname or immich["url"]
        targets.append({"id": "immich", "kind": "immich", "label": f"Immich · {host}"})
    error = "" if targets else f"No Discord profiles or Immich settings found under {config_dir}."
    return {"configured": bool(targets), "error": error, "targets": targets}


def _validate_discord_url(url: str) -> str:
    parsed = urllib.parse.urlparse(str(url or "").strip())
    host = (parsed.hostname or "").lower()
    parts = [part for part in parsed.path.split("/") if part]
    if parsed.scheme != "https" or not (host == "discord.com" or host.endswith(".discord.com")):
        raise SendError("The Discord webhook profile is not an https://discord.com webhook URL.")
    if len(parts) < 4 or parts[-3] != "webhooks":
        raise SendError("The Discord webhook profile does not look like a webhook URL.")
    query = urllib.parse.parse_qsl(parsed.query, keep_blank_values=True)
    if not any(key == "wait" for key, _ in query):
        query.append(("wait", "true"))
    return urllib.parse.urlunparse(parsed._replace(query=urllib.parse.urlencode(query)))


def _truncate(value: Any, limit: int) -> str:
    text = str(value or "").strip()
    return text if len(text) <= limit else text[: max(0, limit - 1)].rstrip() + "…"


def discord_embed(bubba: dict[str, Any] | None) -> dict[str, Any] | None:
    if not bubba:
        return None
    parts = [
        f"{label}: {bubba[key]}"
        for label, key in (("Model", "model_name"), ("Seed", "seed"), ("Steps", "steps"), ("CFG", "cfg"), ("Sampler", "sampler_name"), ("Scheduler", "scheduler"))
        if bubba.get(key)
    ]
    fields = []
    if parts:
        fields.append({"name": "Generation", "value": _truncate("\n".join(parts), DISCORD_MAX_FIELD_LENGTH)})
    if bubba.get("loras"):
        names = [str(name).replace("\\", "/").rsplit("/", 1)[-1] for name in bubba["loras"]]
        fields.append({"name": "LoRAs", "value": _truncate(", ".join(names), DISCORD_MAX_FIELD_LENGTH)})
    if bubba.get("positive_prompt"):
        fields.append({"name": "Positive prompt", "value": _truncate(bubba["positive_prompt"], DISCORD_MAX_FIELD_LENGTH)})
    return {"title": "Bubba Media Viewer", "fields": fields} if fields else None


def _multipart(fields: list[tuple[str, str]], files: list[tuple[str, Path]]) -> tuple[bytes, str]:
    boundary = f"----BubbaViewer{uuid.uuid4().hex}"
    chunks: list[bytes] = []
    for name, value in fields:
        content_type = "Content-Type: application/json\r\n" if name == "payload_json" else ""
        chunks.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n{content_type}\r\n'.encode())
        chunks.extend([value.encode("utf-8"), b"\r\n"])
    for name, path in files:
        content_type = CONTENT_TYPES.get(path.suffix.lower(), "application/octet-stream")
        safe_name = path.name.replace('"', "_")
        chunks.append(
            f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; filename="{safe_name}"\r\nContent-Type: {content_type}\r\n\r\n'.encode()
        )
        chunks.extend([path.read_bytes(), b"\r\n"])
    chunks.append(f"--{boundary}--\r\n".encode())
    return b"".join(chunks), boundary


def _post(url: str, body: bytes, boundary: str, headers: dict[str, str], timeout: float, service: str) -> bytes:
    request = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "User-Agent": "Bubba-Media-Viewer", **headers},
    )
    try:
        with _open(request, timeout) as response:
            if response.status < 200 or response.status >= 300:
                raise SendError(f"{service} returned HTTP {response.status}.", 502)
            return response.read()
    except urllib.error.HTTPError as error:
        raise SendError(f"{service} returned HTTP {error.code}.", 502) from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise SendError(f"Could not reach {service}.", 502) from None


def send_to_discord(
    config_dir: Path,
    profile: str,
    paths: list[str],
    message: str = "",
    metadata_for: Callable[[str], dict[str, Any] | None] = lambda _path: None,
) -> dict[str, Any]:
    webhook = discord_profiles(config_dir).get(str(profile or ""))
    if not webhook:
        raise SendError(f'Discord profile "{profile}" is not configured in Bubba Nodes.')
    url = _validate_discord_url(webhook)
    files = [Path(path) for path in paths]
    too_big = [path.name for path in files if path.stat().st_size > DISCORD_MAX_FILE_BYTES]
    if too_big:
        raise SendError(f"Discord webhooks accept files up to 10 MB; too large: {', '.join(too_big[:3])}.")
    batches = [files[index : index + DISCORD_MAX_FILES_PER_MESSAGE] for index in range(0, len(files), DISCORD_MAX_FILES_PER_MESSAGE)]
    for number, batch in enumerate(batches):
        payload: dict[str, Any] = {}
        if number == 0 and message.strip():
            payload["content"] = _truncate(message, DISCORD_MAX_MESSAGE_LENGTH)
        if len(files) == 1:
            embed = discord_embed(metadata_for(str(batch[0])))
            if embed:
                payload["embeds"] = [embed]
        body, boundary = _multipart(
            [("payload_json", json.dumps(payload, ensure_ascii=False))],
            [(f"files[{index}]", path) for index, path in enumerate(batch)],
        )
        _post(url, body, boundary, {}, 60, "Discord")
    return {"sent": len(files), "messages": len(batches), "destination": f"Discord · {profile}"}


def send_to_immich(config_dir: Path, paths: list[str]) -> dict[str, Any]:
    config = immich_config(config_dir)
    if not config:
        raise SendError("Immich is not configured in Bubba Nodes (server URL and API key).")
    parsed = urllib.parse.urlsplit(config["url"])
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise SendError("The Immich server URL in Bubba Nodes is invalid.")
    asset_ids = []
    for path in (Path(item) for item in paths):
        data = path.read_bytes()
        stamp = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
        fields = [
            ("deviceAssetId", f"{path.name}-{hashlib.sha256(data).hexdigest()[:20]}"),
            ("deviceId", "bubba-media-viewer"),
            ("fileCreatedAt", stamp),
            ("fileModifiedAt", stamp),
        ]
        body, boundary = _multipart(fields, [("assetData", path)])
        raw = _post(config["url"] + "/assets", body, boundary, {"x-api-key": config["api_key"], "Accept": "application/json"}, 120, "Immich")
        try:
            result = json.loads(raw.decode("utf-8") or "{}")
        except ValueError:
            result = {}
        if not isinstance(result, dict) or not result.get("id"):
            raise SendError("Immich returned an invalid upload response.", 502)
        asset_ids.append(str(result["id"]))
    host = parsed.hostname or config["url"]
    return {"sent": len(asset_ids), "asset_ids": asset_ids, "destination": f"Immich · {host}"}


def validate_send_paths(paths: list[str]) -> list[str]:
    if not paths:
        raise SendError("Select media to send.")
    if len(paths) > MAX_SEND_FILES:
        raise SendError(f"Send at most {MAX_SEND_FILES} files at a time.")
    missing = [os.path.basename(path) for path in paths if not os.path.isfile(path)]
    if missing:
        raise SendError(f"File not found: {missing[0]}")
    return paths
