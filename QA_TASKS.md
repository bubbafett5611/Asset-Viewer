# QA Tasks

Captured from the May 9, 2026 project QA pass against the local Flask/Vue app.

- [x] Fix `/api/assets/list` invalid query handling.
  Return `400` or safe defaults for bad `limit`, `offset`, `min_size_bytes`, `max_size_bytes`, and `modified_after_ts`.
- [x] Add real pytest coverage.
  Cover roots, asset list filtering/sorting, details, thumbnails, upload/delete validation, traversal rejection, and malformed query params.
- [x] Fix `.pytest_cache` permissions/shape.
  Pytest warns it cannot write cache files, and `git status` cannot read `.pytest_cache`.
- [x] Exclude non-previewable files from broken thumbnail rendering.
  Non-image and empty files now show a clean preview fallback instead of a broken image.
- [x] Improve thumbnail error state.
  Broken thumbnail images should render a clean placeholder instead of a blank image icon.
- [x] Improve desktop layout polish.
  Toolbar controls and card metadata are cramped; dates/sizes visually run together in places.
- [x] Improve Tag Browser contrast.
  Tag row text is very low contrast against pale cards, especially aliases and counts.
- [x] Normalize tag search.
  Searching `red hair` should match `red_hair`; likely normalize spaces, underscores, and maybe hyphens.
- [x] Reduce `/api/tags` payload size.
  It currently returns about `23 MB` / `321,995` tags at once. Add server-side search, pagination, category filters, or lazy loading.
- [x] Replace CDN Vue dependency or document it clearly.
  The standalone app imports Vue from `unpkg.com`; offline or blocked-network usage can break.
- [x] Wire visible labels to inputs/selects.
  Some controls rely on `aria-label` rather than real `label for` associations.
- [x] Add browser smoke tests.
  Automate basic flows: load app, select asset, search/filter, empty state, open Tag Browser, select tag, and favorite tag.
- [x] Add duplicate image detection.
  Provide a Duplicates tab with exact file matches, same-pixel matches, and optional near-duplicate scanning.

## Future QA / Product Tasks

- [x] Add metadata filter chips. [HIGH]
  Quick toggles for Bubba metadata, Workflow, Params, No metadata, and related combinations.
- [x] Add duplicate cleanup helpers. [HIGH]
  Per duplicate group actions such as Select all but newest, Select all but largest, and Select all in group.
- [x] Add image compare view. [HIGHEST]
  Side-by-side or lightbox comparison for duplicate and near-duplicate groups.
- [x] Persist viewer settings. [MEDIUM]
  Remember density, blur, sort order, last folder, duplicate threshold, Near Duplicates toggle, and active tab.
- [x] Add metadata health report. [HIGH]
  Summarize how many assets have Bubba metadata, Workflow, Params, missing metadata, and invalid metadata.
- [x] Add bulk export/copy tools. [MEDIUM]
  Copy selected paths and export duplicate groups or metadata coverage as CSV/JSON.
- [x] Improve keyboard selection. [MEDIUM]
  Add duplicate-group keyboard navigation, Space to select, and Delete to remove selected items.
- [x] Add folder stats panel. [LOW]
  Show total files, total size, image count, model count, metadata coverage, and reclaimable duplicate size.
- [x] Add open containing folder action. [LOW]
  Open the selected asset's parent folder from the viewer.
- [x] Add delete safety mode. [HIGH]
  Move deleted files to a local trash or quarantine folder instead of permanent deletion.
