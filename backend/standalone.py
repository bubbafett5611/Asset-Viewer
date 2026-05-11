from __future__ import annotations

import os
import threading
import time
import webbrowser

from server import app
from services.app_context import logger


HOST = "127.0.0.1"
DEFAULT_PORT = 5001


def _configured_port() -> int:
    raw_port = os.environ.get("BUBBA_ASSET_VIEWER_PORT")
    if not raw_port:
        return DEFAULT_PORT
    try:
        return int(raw_port)
    except ValueError:
        logger.warning("Invalid BUBBA_ASSET_VIEWER_PORT value %r; using %s.", raw_port, DEFAULT_PORT)
        return DEFAULT_PORT


def _open_browser(url: str) -> None:
    if os.environ.get("BUBBA_ASSET_VIEWER_NO_BROWSER"):
        return
    time.sleep(0.75)
    webbrowser.open(url)


def main() -> None:
    port = _configured_port()
    url = f"http://{HOST}:{port}/"
    threading.Thread(target=_open_browser, args=(url,), daemon=True).start()
    logger.info("Bubba Media Viewer started on %s", url)
    app.run(host=HOST, port=port, debug=False, use_reloader=False)


if __name__ == "__main__":
    main()
