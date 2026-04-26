# Asset Viewer Standalone

A minimal, standalone copy of the Bubba Asset Viewer: a small Python backend plus a static frontend for browsing and managing asset files.

Quick overview

- Backend: a lightweight Python application that exposes the asset API and any upload/delete endpoints. See [backend/server.py](backend/server.py) and [backend/asset_viewer.py](backend/asset_viewer.py).
- Frontend: a static UI (HTML/CSS/JS) to browse assets. Open [frontend/asset_viewer.html](frontend/asset_viewer.html) in a browser.

Repository layout

- [backend/](backend/) — backend code and server entrypoint ([backend/server.py](backend/server.py), [backend/asset_viewer.py](backend/asset_viewer.py)).
- [frontend/](frontend/) — static UI and sample dataset ([frontend/asset_viewer.html](frontend/asset_viewer.html), [frontend/asset_viewer.css](frontend/asset_viewer.css), [frontend/danbooru_e621_merged.csv](frontend/danbooru_e621_merged.csv)).
- [tests/](tests/) — test suite and utilities ([tests/test_asset_viewer.py](tests/test_asset_viewer.py), [tests/check_e621.py](tests/check_e621.py), [tests/upload_delete_test.py](tests/upload_delete_test.py)).
- requirements.txt — Python dependencies.
- start.bat — convenience script for Windows (if present) to help start the environment.
- LICENSE, pyproject.toml — project metadata and license.

Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\\.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
python backend/server.py
```

Setup (Windows cmd)

```cmd
python -m venv .venv
.\\.venv\\Scripts\\activate
pip install -r requirements.txt
python backend/server.py
```

Notes

- Open [frontend/asset_viewer.html](frontend/asset_viewer.html) in your browser to use the UI. If the backend is running and the frontend is configured to call it, the UI will connect to the backend API (see [backend/server.py](backend/server.py) for host/port configuration).
- The repository includes a small CSV sample dataset at [frontend/danbooru_e621_merged.csv](frontend/danbooru_e621_merged.csv) used by the frontend for demonstrations.

Running tests

```bash
python -m pytest -q
```

If tests fail, run the failing test file directly to see full output.

Contributing

- If you change backend endpoints, update the frontend URLs as needed.
- Add or update tests in the [tests/](tests/) folder and run them with pytest.

License

See the project [LICENSE](LICENSE) file for license details.
