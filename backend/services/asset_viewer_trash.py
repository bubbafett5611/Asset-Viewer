from __future__ import annotations

import os
import shutil
import time


def move_file_to_trash(path: str, root: str, is_path_within_root_fn) -> str:
    normalized_root = os.path.abspath(root)
    abs_path = os.path.abspath(path)
    if not is_path_within_root_fn(abs_path, normalized_root):
        raise PermissionError("Requested file is outside selected root.")
    trash_root = os.path.join(normalized_root, ".asset_viewer_trash", time.strftime("%Y%m%d-%H%M%S"))
    rel_path = os.path.relpath(abs_path, normalized_root)
    destination = os.path.join(trash_root, rel_path)
    os.makedirs(os.path.dirname(destination), exist_ok=True)
    base, ext = os.path.splitext(destination)
    counter = 1
    while os.path.exists(destination):
        destination = f"{base}_{counter}{ext}"
        counter += 1
    shutil.move(abs_path, destination)
    return destination
