# Media Viewer Standalone

A minimal, standalone copy of the Bubba Media Viewer: a small Python backend plus a static frontend for browsing and managing media files.

Quick overview

- Backend: a lightweight Python application that exposes the media API and upload/delete endpoints. See [backend/server.py](backend/server.py) and [backend/asset_viewer.py](backend/asset_viewer.py).
- Frontend: a static Vue UI served from [frontend/asset_viewer_vue.html](frontend/asset_viewer_vue.html).

Repository layout

- [backend/](backend/) - backend code and server entrypoint ([backend/server.py](backend/server.py), [backend/asset_viewer.py](backend/asset_viewer.py)).
- [frontend/](frontend/) - static UI and sample dataset ([frontend/asset_viewer_vue.html](frontend/asset_viewer_vue.html), [frontend/asset_viewer.css](frontend/asset_viewer.css), [frontend/danbooru_e621_merged.csv](frontend/danbooru_e621_merged.csv)).
- [tests/](tests/) - test suite and utilities ([tests/test_asset_viewer.py](tests/test_asset_viewer.py), [tests/check_e621.py](tests/check_e621.py), [tests/upload_delete_test.py](tests/upload_delete_test.py)).
- requirements.txt - Python dependencies.
- start.bat - convenience script for Windows, if present, to help start the environment.
- LICENSE, pyproject.toml - project metadata and license.

Setup (Windows PowerShell)

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python backend/server.py
```

Setup (Windows cmd)

```cmd
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python backend/server.py
```

Notes

- Open `http://localhost:5001/` to use the Vue UI.
- The repository includes a small CSV sample dataset at [frontend/danbooru_e621_merged.csv](frontend/danbooru_e621_merged.csv) used by the frontend for demonstrations.
- The Vue UI currently imports Vue 3 from `https://unpkg.com`, so first-load usage needs network access unless Vue is vendored locally later.

Running tests

```bash
python -m pytest -q
```

Quality checks (Phase 1)

Install Python quality tools if you have not already:

```bash
pip install -r requirements.txt
```

Run backend lint + type checks + tests:

```bash
python -m ruff check backend tests
python -m mypy
python -m pytest --basetemp .pytest_tmp -q
```

Short command set for daily use:

```bash
python -m ruff check backend tests && python -m mypy && python -m pytest --basetemp .pytest_tmp -q
```

Frontend formatter/linter setup:

```bash
npm install
npm run lint:frontend
npm run format:frontend
```

The optional browser smoke test in [tests/test_browser_smoke.py](tests/test_browser_smoke.py) runs when Playwright is installed; otherwise pytest skips it cleanly. If tests fail, run the failing test file directly to see full output.

Contributing

- If you change backend endpoints, update the frontend URLs as needed.
- Add or update tests in the [tests/](tests/) folder and run them with pytest.

License

See the project [LICENSE](LICENSE) file for license details.
