#!/usr/bin/env python3
"""
Simple test script that creates an in-memory PNG, uploads it to the running
asset viewer backend, then deletes the uploaded file.
"""
import sys
import time
from io import BytesIO

import requests
from PIL import Image

BASE = "http://127.0.0.1:5001"
ROOT_KEY = "Text2Img"


def make_image_bytes():
    img = Image.new("RGBA", (64, 64), (255, 0, 0, 255))
    buf = BytesIO()
    img.save(buf, "PNG")
    buf.seek(0)
    return buf


def upload():
    url = f"{BASE}/bubba/assets/upload?root={ROOT_KEY}"
    buf = make_image_bytes()
    files = [("files", ("test_upload.png", buf, "image/png"))]
    r = requests.post(url, files=files, timeout=30)
    print("upload status", r.status_code)
    print(r.text)
    if not r.ok:
        raise SystemExit(1)
    data = r.json()
    uploaded = data.get("uploaded", [])
    if not uploaded:
        print("No uploaded files returned")
        return None
    return uploaded[0].get("path")


def delete(path):
    url = f"{BASE}/bubba/assets/delete"
    r = requests.post(url, json={"path": path}, timeout=30)
    print("delete status", r.status_code)
    print(r.text)
    return r.ok


def main():
    p = upload()
    if not p:
        print("Upload failed")
        sys.exit(1)
    print("Uploaded:", p)
    time.sleep(1)
    ok = delete(p)
    print("Deleted OK?", ok)


if __name__ == "__main__":
    main()
