# Production QA Review

Date: 2026-05-10

## 1. High-Level Architecture Review

No critical production blockers were found, but several major maintainability risks stand out.

### Major

- `backend/server.py` is doing too much: external tag fetching, Flask app setup, static file serving, API routes, caching, settings, upload/delete behavior, duplicate streaming, and OS integration all live in one module. Real-world impact: every backend change risks accidental coupling, and onboarding developers will struggle to find the correct boundary.
- `backend/server.py` runs `ensure_tag_list()` at import time. This can perform network/file work before the Flask app is even created. That makes tests, imports, deployments, and CLI tooling less predictable.
- There is no application factory, blueprint separation, or service layer. Routes directly call scanning, filesystem, HTTP, settings, and subprocess behavior.

### Cleaner Alternative

- Split the backend into focused modules such as `app.py`, `routes/assets.py`, `routes/tags.py`, `routes/settings.py`, `services/assets.py`, `services/tags.py`, and `services/duplicates.py`.
- Move startup data preparation behind an explicit command or lazy runtime check.

## 2. Python Review

### Major

- `backend/asset_viewer.py::scan_assets()` is large and multi-purpose: walking files, filtering, sorting, metadata extraction, pagination, badge filtering, and response shaping. This is hard to safely extend.
- `backend/asset_viewer.py::scan_duplicate_assets()` mixes scan orchestration, hashing, grouping, near-duplicate comparison, and progress reporting. Near-duplicate mode is pairwise comparison, so scale risk grows quickly.
- `backend/server.py` uses module-level mutable `ASSET_ROOTS`. In production or threaded servers, settings changes can race with active requests.

### Minor

- `backend/asset_viewer.py::discover_asset_roots()` uses `print()` for operational logging. Use module loggers with levels.
- `backend/server.py` imports are split into two blocks, with executable startup work in between. This violates normal Python structure and makes dependencies harder to audit.
- Many broad `except Exception` blocks hide root causes. Some are reasonable at API boundaries, but internal parsing/scanning should catch narrower exceptions.

## 3. Vue Review

### Major

- `frontend/vue/useAssetViewer.js` is effectively the whole frontend application: assets, tags, duplicates, stats, settings, upload, delete, keyboard shortcuts, drag/drop, resize, export, and API orchestration. This is the largest frontend maintainability issue.
- `frontend/asset_viewer_vue.js` contains a very large inline template. It should be split into view components: `AssetsView`, `TagsView`, `DuplicatesView`, `StatsView`, `SettingsView`, plus modal components.
- `frontend/vue/useAssetViewer.js` relies on several watchers for orchestration. The watchers are understandable now, but as state grows this becomes fragile and difficult to reason about.

### Cleaner Alternative

- Create composables by domain: `useAssets`, `useTags`, `useDuplicates`, `useSettings`, `useSelection`, and `useKeyboardShortcuts`.
- Let view components own their UI-specific state instead of returning a very large public binding surface from one composable.

## 4. CSS Review

### Major

- CSS is split into files, which helps, but component ownership is blurry. For example, button styles appear in both `frontend/styles/base.css` and `frontend/styles/layout.css`. This will become a specificity and consistency problem.
- Design tokens exist in `base.css`, but many raw `rgba(...)`, hard-coded radii, font sizes, gradients, and shadows still appear throughout feature files.
- Generic classes like `.panel`, `.controls`, `.button`, `.field`, and `.meta-row` are globally shared. Real-world impact: future feature CSS can accidentally affect unrelated screens.

### Minor

- `base.css` uses `!important` for `[hidden]`; acceptable, but keep it as the only exception.
- Commented-out CSS remains in production styles, for example in `layout.css`.

### Cleaner Alternative

- Define a small design system layer: buttons, fields, panels, badges.
- Use feature-prefixed classes for feature-specific styling, such as `assets-*`, `duplicates-*`, and `settings-*`.

## 5. Readability And Maintainability Review

### Major

- The backend and frontend both have large mixed-responsibility modules. The code is readable line-by-line, but not readable at system scale.
- Several names are clear locally, but boundaries are not. `asset_viewer.py` contains metadata parsing, asset scanning, duplicate detection, thumbnails, trash handling, root discovery, and report caching.
- Error handling often returns simplified messages, which is good for users but weak for developers unless paired with structured logging.

## 6. Technical Debt Risks

- Import-time side effects in `server.py`.
- No configured linting, formatting, type checking, or frontend build tooling in `pyproject.toml`.
- Vue is loaded from CDN in `frontend/asset_viewer_vue.js`, which is fragile for production/offline use.
- Duplicate scanning and metadata extraction are synchronous and request-bound.
- Global mutable backend state will become problematic under multiple workers.

## 7. Recommended Refactors

1. Introduce a Flask app factory and blueprints.
2. Split `asset_viewer.py` into focused services: roots, scanning, metadata, thumbnails, duplicates, trash.
3. Split `useAssetViewer.js` by domain composable.
4. Split `asset_viewer_vue.js` into view components.
5. Add `ruff`, `mypy` or pyright-lite typing checks, and a frontend formatter/linter.
6. Replace CDN Vue with vendored or package-managed Vue.
7. Move long-running scans toward background jobs or cancellable task endpoints.

## 8. Quick Wins

- Move `ensure_tag_list()` out of module import.
- Replace `print()` in backend with `logging.getLogger(__name__)`.
- Add `ruff` config to `pyproject.toml`.
- Remove committed `__pycache__` directories from the repo if tracked.
- Consolidate `.btn` and `.button` into one button system.
- Add constants for repeated metadata mode strings and badge keys.
- Add tests around settings updates while asset requests are active.

## 9. Overall Project Health Score

**6.5 / 10**

Functionality is in decent shape: tests passed with `.venv` using `27 passed, 1 skipped`.

The main concern is not correctness today; it is long-term change cost. The project is at the point where the next few features will either become much easier after decomposition or significantly harder if the current large modules keep absorbing responsibilities.
