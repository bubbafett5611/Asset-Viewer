from __future__ import annotations

from io import BytesIO


def generate_thumbnail_bytes(path: str, max_size: int = 256, image_module=None) -> bytes | None:
    image_module = image_module
    if image_module is None:
        return None

    try:
        size = max(32, min(int(max_size), 1024))
    except Exception:
        size = 256

    try:
        with image_module.open(path) as image_handle:
            image = image_handle.convert("RGBA")
            image.thumbnail((size, size), image_module.Resampling.LANCZOS)
            buffer = BytesIO()
            image.save(buffer, format="PNG", optimize=True)
            return buffer.getvalue()
    except Exception:
        return None
