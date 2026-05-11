# Bubba Media Viewer

Bubba Media Viewer is a fast local web app for browsing, inspecting, comparing, and cleaning up image-heavy folders. It is built for generated-image libraries, Stability Matrix output folders, asset collections, prompt experiments, reference dumps, and any directory where normal file explorers start to feel clumsy.

The app runs on your machine and works directly with folders you choose. Point it at one or more asset roots in `settings.json`, start the local server, and open the viewer in your browser. From there you get a purpose-built media workflow: dense thumbnail browsing, metadata inspection, tag lookup, duplicate cleanup, image comparison, exports, and keyboard-first navigation.

## Who It Is For

Bubba Media Viewer is for people who have outgrown ordinary file explorers for image work. If your folders are full of generation batches, upscales, edits, references, test renders, duplicate candidates, and prompt experiments, the viewer gives you a focused place to sort through them.

It fits especially well for:

- AI image generation workflows with large output folders.
- Stability Matrix users who want a cleaner way to review generated images.
- Artists and asset collectors managing reference libraries.
- Prompt builders who want tag lookup next to their media.
- Dataset and model-prep workflows where metadata quality matters.
- Anyone who wants local file management without uploading private images to a hosted tool.

## Why Use It?

Big image folders get messy quickly. A generation session can leave you with hundreds or thousands of similar outputs, vague filenames, repeated prompts, partial metadata, and near-identical images scattered across subfolders. Bubba Media Viewer gives that mess a proper workspace.

Instead of opening files one by one, you can scan a whole folder visually, filter it down, inspect metadata, copy useful paths or tags, compare candidates, find duplicates, and safely clean up files without leaving the browser.

It is especially useful when you want to:

- Review large batches of generated images.
- Find the best result among many similar outputs.
- Clean duplicate or near-duplicate images from a folder.
- Inspect prompt and generation metadata quickly.
- Copy images or paths into other tools.
- Browse tag vocabularies while building prompts.
- Keep local asset folders organized without uploading anything to a hosted service.

## What Makes It Different

Most image tools are either general file managers, single-image editors, or cloud galleries. Bubba Media Viewer is narrower on purpose: it is built around the repeated chores that happen after image generation or collection work.

- It treats folders as working libraries, not just directories.
- It keeps media browsing, metadata, tags, duplicates, and cleanup in one interface.
- It favors dense, practical controls over decorative gallery layouts.
- It supports keyboard-heavy review sessions where speed matters.
- It keeps destructive actions explicit, with safe delete as the default.
- It is local-first, so your files stay on your machine.

## What You Can Do

### Browse Local Media Like A Workspace

Open your configured image roots in a browser interface built for scanning. The Media tab supports dense thumbnail grids, adjustable card density, blur toggles, search, extension filtering, metadata filtering, sorting, paging, multi-select, full-size opening, and quick access to containing folders.

This is the main advantage over a normal folder view: you can keep context visible while moving quickly. Select an image, inspect its details, copy it, open the folder, compare it, or delete it without breaking your review flow.

### Inspect Metadata Without Digging Through Files

The details panel surfaces file information, paths, metadata badges, and parsed generation metadata where available. You can copy useful values directly instead of hunting through PNG chunks, sidecar data, or scattered notes.

For generated images, this makes it much easier to answer practical questions: which prompt created this, which files are missing metadata, which outputs came from similar settings, and which images need repair or cleanup.

### Copy Images And Paths Quickly

Copy the selected full-size image to the clipboard, copy one or many file paths, copy media names, and copy selected tag names. This is handy when moving between the viewer, prompt tools, editors, Discord, issue trackers, or file-management scripts.

The goal is to reduce context switching. When you find the image or tag you need, you should be able to move it into the next tool immediately.

### Clean Up Safely

Normal delete actions move files into `.asset_viewer_trash` inside the asset root, giving you a safer cleanup workflow than immediate permanent deletion. Permanent delete is still available when you explicitly ask for it.

### Find And Remove Duplicates

The Duplicates tab can scan the selected root for exact duplicates and optional near duplicates. It streams progress, supports cancellation, groups results, helps select duplicates while preserving one item, and can export reports for later review.

This turns cleanup into a reviewable process instead of a guessing game. You can scan, inspect grouped results, compare uncertain matches, keep the best copy, and export what was found before taking action.

### Compare Images Side By Side

Select two images and open the compare view to inspect differences with a draggable divider. This is useful for subtle generation variations, upscales, edits, and duplicate candidates.

### Browse Prompt Tags

The Tag Browser helps you search tag names and aliases, favorite tags, keep recent tags nearby, inspect example results, copy tag names, and open external searches. It is designed to stay useful while prompt-building or standardizing labels.

Because tag search lives in the same app as your media, you can move between visual review and prompt vocabulary without bouncing between unrelated tools.

### Check Folder And Metadata Health

The Stats tab summarizes root-level folder information and metadata health. Reports can be refreshed and exported, which makes it easier to spot missing or inconsistent metadata in a collection.

This is useful before cleanup, archival, sharing, or model-prep work. Instead of relying on memory, you can get a quick read on what is in a library and where the rough spots are.

### Work Keyboard-First

The app has shortcuts for tab switching, search focus, media navigation, multi-selection, image copying, duplicate scanning, tag copying, compare controls, exports, and delete actions. Press `?` inside the app to show the shortcut reference.

## Feature Overview

| Area | Highlights |
| --- | --- |
| Media browsing | Multi-root browsing, search, sorting, filters, density controls, virtualized large-list handling |
| Details | Preview, paths, metadata badges, generation metadata, copy actions, folder opening |
| File management | Upload, safe delete, permanent delete, trash folder cleanup workflow |
| Duplicate cleanup | Exact/near duplicate scan, progress events, cancellation, grouped selection, compare, export |
| Tag workflow | Tag search, aliases, categories, favorites, recents, examples, external search links |
| Reports | Folder stats, metadata health, JSON/CSV exports |
| Keyboard workflow | Fast tab switching, arrow navigation, copy/export/delete shortcuts, in-app shortcut reference |
| Local-first design | Runs locally, reads configured folders, uses a vendored Vue build, no hosted service required |

## Install

### Requirements

- Python 3.10 or newer.
- Windows is the primary target environment.
- Node.js/npm is only needed if you want to run frontend linting/formatting as a developer.

### Quick Install On Windows

Run:

```cmd
install.bat
```

If you prefer to install manually, use one of the setup flows below.

### Manual Install With PowerShell

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### Manual Install With cmd

```cmd
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
```

## Configure Your Media Folders

Open `settings.json` and set `general.asset_roots` to the folders you want Bubba Media Viewer to browse.

Example:

```json
{
  "general": {
    "asset_roots": [
      "C:\\StabilityMatrix\\Data\\Images\\Text2Img"
    ]
  },
  "viewer": {
    "density": "large",
    "preview": false
  }
}
```

Only files inside configured asset roots are available to the app. If no roots are configured, the Media tab will not have a folder to browse.

You can configure multiple roots. The viewer will show them in the root picker so you can switch between libraries without changing code or restarting your workflow.

### Where Settings Are Stored

When running from a source checkout, the app reads and writes the repo-local `settings.json` file.

Standalone packaged builds are designed to keep user-editable state out of the install folder. In packaged mode, settings are stored at:

```text
%APPDATA%\Bubba Media Viewer\settings.json
```

Generated report caches are also stored under:

```text
%APPDATA%\Bubba Media Viewer\cache\
```

On first launch, the packaged app copies the bundled default `settings.json` into AppData if no user settings file exists yet. This means the app can be updated or replaced later without wiping your configured media folders or relying on writes to the install directory.

### Viewer Preferences

The `viewer` section controls presentation defaults:

- `density`: default media card density. Supported values are `compact`, `comfortable`, and `large`.
- `preview`: whether thumbnail blur starts enabled.

You can also edit supported settings from the Settings tab in the app.

## Start The App

### Recommended Windows Launcher

Run:

```cmd
start.bat
```

### Manual Start

```powershell
python backend/server.py
```

Then open:

```text
http://localhost:5001/
```

## Using The Viewer

### Media

The Media tab is the main workspace. Pick a root folder, search or filter the current library, then move through the grid with the mouse or keyboard. The right-side details panel updates as you select images, so you can inspect files without opening them one at a time.

From here you can:

- Pick the active root folder.
- Search by name/path.
- Filter by extension and metadata state.
- Sort by name, modified date, size, or metadata.
- Change card density.
- Select one or many media items.
- Copy the selected image or selected file path(s).
- Open the image full-size or open its containing folder.
- Upload images into the current root.
- Delete selected media.
- Compare two selected images.
- Repair tracked PNG metadata when available.

Deletion defaults to safe delete, which moves files to `.asset_viewer_trash` inside the asset root. Permanent delete is available through the permanent-delete shortcut or Shift-click delete actions.

### Tag Browser

The Tag Browser is a companion panel for prompt and label work. Search for a tag or alias, inspect the selected tag on the right, copy it, favorite it, or jump to an external search.

You can:

- Search tags and aliases.
- Filter by category.
- View all, favorite, or recent tags.
- Copy a selected tag.
- Favorite or unfavorite tags.
- Inspect aliases and example posts.
- Open external searches for a tag.

### Duplicates

The Duplicates tab is built for cleanup sessions. Run a scan on the current root, review grouped results, compare similar images, select everything except the keeper, then delete or export the findings.

You can:

- Run a duplicate scan for the selected root.
- Include near-duplicate detection.
- Watch scan progress.
- Cancel an active scan.
- Select all but one item from duplicate groups.
- Compare duplicate candidates.
- Delete selected duplicate media.
- Export duplicate reports as JSON or CSV.

### Stats

Use the Stats tab to understand the shape and health of a library. It can load folder statistics and metadata health reports for the selected root or all configured roots. Reports can be refreshed and exported.

### Settings

Use the Settings tab to edit supported viewer settings without opening `settings.json` manually. Changes are saved back to disk.

## Typical Workflows

### Review A New Generation Batch

1. Open the Media tab.
2. Select the output root.
3. Sort by modified date.
4. Use arrow keys to move through the newest images.
5. Copy strong candidates to the clipboard or open them full-size.
6. Delete rejects with safe delete.

### Clean Up Duplicates

1. Open the Duplicates tab.
2. Choose whether to include near duplicates.
3. Run the scan with `Ctrl+Shift+D` or the scan button.
4. Compare uncertain candidates.
5. Select duplicate items you do not want to keep.
6. Delete or export the report.

### Build Or Refine Prompt Tags

1. Open the Tag Browser.
2. Search by tag name or alias.
3. Move through results with `Up` and `Down`.
4. Copy the selected tag with `Ctrl+C`.
5. Favorite useful tags for later.

### Audit Metadata

1. Open the Stats tab.
2. Load metadata health for the current root.
3. Export the report if you want to keep a snapshot.
4. Return to Media to inspect or repair individual files.

## Keyboard Shortcuts

Shortcuts apply when focus is not inside an input, textarea, select, or editable field. Press `?` in the app to open the in-app shortcut reference.

On macOS, browser-level `Cmd` is treated like `Ctrl` for command shortcuts where supported.

### Navigation And General

| Shortcut | Function |
| --- | --- |
| `M` | Open Media tab |
| `T` | Open Tag Browser tab |
| `D` | Open Duplicates tab |
| `S` | Open Stats tab |
| `?` | Open keyboard shortcut reference |
| `Esc` | Close shortcut/delete/compare modal, or clear selection |
| `R` | Refresh Media, Tags, Stats, or Settings |
| `Ctrl+F` | Focus search in Media or Tags |
| `Ctrl+A` | Select all visible media or duplicate media |
| `Ctrl+E` | Export media selection or duplicate groups |
| `Ctrl+L` | Copy selected media or tag name |

### Media

| Shortcut | Function |
| --- | --- |
| `Arrows` | Move media selection |
| `Shift+Arrows` | Extend media selection while moving |
| `Space` | Toggle selected media into multi-selection |
| `Enter` | Open selected media full-size |
| `Ctrl+C` | Copy selected image to clipboard |
| `Ctrl+Shift+C` | Copy selected file path(s) |
| `Ctrl+O` | Open selected media full-size |
| `Ctrl+Shift+O` | Open containing folder |
| `B` | Toggle thumbnail blur |
| `Delete` | Delete selected media |
| `Shift+Delete` | Permanently delete selected media |

### Duplicates

| Shortcut | Function |
| --- | --- |
| `Arrows` | Move duplicate media selection |
| `Shift+Arrows` | Extend duplicate selection while moving |
| `Space` | Toggle selected duplicate media |
| `Ctrl+C` | Copy selected duplicate path(s) |
| `Ctrl+Shift+C` | Copy selected duplicate path(s) |
| `Ctrl+A` | Select all duplicate media |
| `Ctrl+E` | Export duplicate groups |
| `Ctrl+Shift+D` | Run duplicate scan for current root |
| `Delete` | Delete selected duplicate media |
| `Shift+Delete` | Permanently delete selected duplicate media |

### Tags

| Shortcut | Function |
| --- | --- |
| `Up / Down` | Move through tag list |
| `Enter` | Select focused tag row |
| `Space` | Select focused tag row |
| `Ctrl+C` | Copy selected tag |
| `Ctrl+Shift+F` | Favorite or unfavorite selected tag |
| `Ctrl+L` | Copy selected tag name |
| `/` | Focus tag search |

### Compare Modal

| Shortcut | Function |
| --- | --- |
| `Left / Right` | Move compare divider |
| `Shift+Left / Right` | Move compare divider faster |
| `Home` | Move divider fully left |
| `End` | Move divider fully right |
| `Esc` | Close compare modal |

## Safety Notes

- The viewer can upload, move, and delete files inside configured asset roots.
- Safe delete moves media to `.asset_viewer_trash`.
- Permanent delete bypasses the viewer trash.
- Keep `settings.json` pointed only at folders you intentionally want the app to manage.
- This app is intended for local trusted use, not public hosting.

## Troubleshooting

### The Media tab is empty

Check `settings.json` and make sure `general.asset_roots` contains at least one existing folder.

### Thumbnails do not appear

Make sure the files are supported image types and are inside a configured asset root. The app currently handles common image extensions such as PNG, JPG/JPEG, WEBP, BMP, GIF, TIF, and TIFF.

### Open containing folder does nothing

Folder opening depends on the local operating system. Windows is the primary supported environment.

### Clipboard image copy fails

Image clipboard support depends on the browser. Path and tag copying should still work even if image copying is unavailable.

## For Developers

### Project Structure

```text
backend/
  server.py                  Flask app factory and server entrypoint
  settings_model.py          Pydantic settings schema and validation
  blueprints/                HTTP route registration by feature area
  services/                  Backend services for assets, tags, settings, duplicates, metadata, thumbnails, and trash

frontend/
  asset_viewer_vue.html      Static app shell
  asset_viewer_vue.js        Vue app mount and top-level layout
  styles/                    CSS modules
  vendor/                    Vendored Vue ESM build
  vue/components/            Vue component modules
  vue/composables/           State and workflow composables

tests/                       Backend and smoke tests
```

### Development Setup

Install Python dependencies:

```powershell
pip install -r requirements.txt
```

Install frontend tooling:

```powershell
npm install
```

Run the backend:

```powershell
python backend/server.py
```

### QA Commands

```powershell
python -m ruff check .
python -m mypy
python -m pytest -q
npm run lint:frontend
npm run format:frontend:check
```

Format frontend files:

```powershell
npm run format:frontend
```

### Windows Build

Install build tooling and create a portable Windows build:

```powershell
.\scripts\build_windows.ps1
```

For a faster local packaging pass after checks already passed:

```powershell
.\scripts\build_windows.ps1 -SkipChecks
```

The build outputs:

```text
dist\BubbaMediaViewer\
dist\BubbaMediaViewer-windows-x64.zip
```

GitHub Actions builds the same portable zip when changes land on `main`, when you run the workflow manually, or when you push a version tag.

To publish a GitHub Release:

```powershell
git tag v0.1.0
git push origin v0.1.0
```

Version tags matching `v*` run the Windows build, create a GitHub Release, generate release notes, and attach `BubbaMediaViewer-windows-x64.zip` to the release.

### Maintenance Notes

- Keep Flask routes thin; route modules should validate HTTP input and delegate behavior to `backend/services/`.
- Keep Vue components focused on rendering and user events; shared state/workflows belong in composables.
- Keep runtime path decisions in `backend/runtime_paths.py`; packaged builds should write mutable state to AppData, not the install directory.
- Update both the in-app shortcut modal and this README when adding or changing shortcuts.
- Update `backend/settings_model.py` when adding persisted settings.
- Avoid committing local caches, generated thumbnails, `.asset_viewer_trash`, virtualenvs, or `node_modules`.

## License

See [LICENSE](LICENSE).
