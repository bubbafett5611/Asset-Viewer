from __future__ import annotations

import importlib
import json
import mimetypes
import os
import queue
import subprocess
import sys
import threading
from io import BytesIO
from pathlib import Path
from typing import Any

from flask import Response, abort, jsonify, request, send_file, stream_with_context


def _ctx():
    # Resolve server module lazily to avoid import cycles and preserve monkeypatch behavior in tests.
    return importlib.import_module("server")


def bubba_assets_upload_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    root_key = request.args.get('root')
    try:
        dest_root = ctx.resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    files = request.files.getlist('files') if hasattr(request, 'files') else []
    uploaded = []
    skipped = []

    for f in files:
        fname = getattr(f, 'filename', None) or 'upload.png'
        filename = ctx.sanitize_upload_filename(fname)
        ext = Path(filename).suffix.lower()
        if ext not in ctx.ALLOWED_UPLOAD_IMAGE_EXTENSIONS:
            skipped.append({'filename': fname, 'error': f'Invalid extension: {ext}'})
            ctx.logger.warning('Upload skipped invalid extension: %s', fname)
            continue

        try:
            content = f.read()
            if ctx.Image is not None:
                try:
                    bio = BytesIO(content)
                    img = ctx.Image.open(bio)
                    img.verify()
                except Exception:
                    skipped.append({'filename': fname, 'error': 'Invalid image file'})
                    ctx.logger.warning('Upload skipped invalid image: %s', fname)
                    continue

            dest_path = ctx.make_unique_destination_path(dest_root, filename)
            with open(dest_path, 'wb') as fh:
                fh.write(content)

            ctx.logger.info('Uploaded file: %s -> %s', filename, dest_path)
            uploaded.append(ctx.build_asset_item(dest_path, dest_root))
        except Exception as ex:
            ctx.logger.exception('Upload failed for %s', fname)
            skipped.append({'filename': fname, 'error': str(ex)})

    return jsonify({'uploaded': uploaded, 'skipped': skipped})


def bubba_assets_delete_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    payload = request.get_json(silent=True) or {}
    paths: list[str] = []
    payload_paths = payload.get('paths')
    payload_path = payload.get('path')
    if isinstance(payload_paths, list):
        paths = [item for item in payload_paths if isinstance(item, str)]
    elif isinstance(payload_path, str):
        paths = [payload_path]

    if not paths:
        abort(400, 'No paths provided')
    safe_delete = payload.get('safe_delete', True) is not False

    deleted = []
    moved = []
    errors = []
    for p in paths:
        try:
            abs_path = ctx.resolve_requested_file(p, asset_roots)
            root = ctx.find_root_for_path(abs_path, asset_roots)
            if not root:
                raise PermissionError('File not in allowed roots')
            if os.path.exists(abs_path):
                if safe_delete:
                    destination = ctx.move_file_to_trash(abs_path, root.path)
                    moved.append({'path': p, 'destination': destination})
                else:
                    os.remove(abs_path)
                deleted.append(p)
                ctx.logger.info('Deleted file: %s', abs_path)
            else:
                errors.append({'path': p, 'error': 'File not found'})
        except Exception as e:
            ctx.logger.exception('Delete failed for %s', p)
            errors.append({'path': p, 'error': str(e)})

    return jsonify({'deleted': deleted, 'moved': moved, 'safe_delete': safe_delete, 'errors': errors})


def api_roots_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    return jsonify({'roots': [root.__dict__ for root in asset_roots]})


def api_assets_list_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    root_key = request.args.get('root')
    q = request.args.get('q', '')
    ext = request.args.get('ext', '')
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
    except ValueError:
        abort(400, 'Invalid pagination parameter')
    include_metadata = request.args.get('include_metadata', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'modified')
    sort_dir = request.args.get('sort_dir', 'desc')
    min_size_bytes = request.args.get('min_size_bytes')
    max_size_bytes = request.args.get('max_size_bytes')
    modified_after_ts = request.args.get('modified_after_ts')
    metadata_mode = request.args.get('metadata_mode', 'all')
    metadata_badges = [item.strip() for item in request.args.get('metadata_badges', '').split(',') if item.strip()]
    try:
        min_size_filter = int(min_size_bytes) if min_size_bytes else None
        max_size_filter = int(max_size_bytes) if max_size_bytes else None
        modified_after_filter = float(modified_after_ts) if modified_after_ts else None
    except ValueError:
        abort(400, 'Invalid numeric filter')

    try:
        root_path = ctx.resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    assets = ctx.scan_assets(
        root=root_path,
        query=q,
        extensions=[ext] if ext else None,
        limit=limit,
        include_metadata=include_metadata,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
        min_size_bytes=min_size_filter,
        max_size_bytes=max_size_filter,
        modified_after_ts=modified_after_filter,
        metadata_mode=metadata_mode,
        metadata_badge_filter=metadata_badges,
    )
    return jsonify({'assets': assets, 'root': root_key})


def api_assets_metadata_health_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    root_key = request.args.get('root')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    cache_only = request.args.get('cache_only', 'false').lower() == 'true'
    try:
        limit = int(request.args.get('limit', 10000))
    except ValueError:
        abort(400, 'Invalid metadata health parameter')
    try:
        root_path = ctx.resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))
    report, cached = ctx.metadata_health_report(root_path, limit=limit, refresh=refresh, cache_only=cache_only)
    return jsonify({'root': root_key, 'stats': report.model_dump(mode='json') if report else None, 'cached': cached})


def api_assets_stats_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    root_key = request.args.get('root')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    cache_only = request.args.get('cache_only', 'false').lower() == 'true'
    try:
        root_path = ctx.resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))
    report, cached = ctx.folder_stats_report(root_path, refresh=refresh, cache_only=cache_only)
    return jsonify({'root': root_key, 'stats': report.model_dump(mode='json') if report else None, 'cached': cached})


def api_assets_duplicates_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    root_key = request.args.get('root')
    include_near = request.args.get('include_near', 'false').lower() == 'true'
    try:
        near_threshold = int(request.args.get('near_threshold', 6))
        limit = int(request.args.get('limit', 5000))
    except ValueError:
        abort(400, 'Invalid duplicate scan parameter')

    try:
        root_path = ctx.resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    payload = ctx.scan_duplicate_assets(
        root=root_path,
        include_near=include_near,
        near_threshold=near_threshold,
        limit=limit,
    )
    return jsonify({'root': root_key, **payload})


def api_assets_duplicates_stream_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    root_key = request.args.get('root')
    include_near = request.args.get('include_near', 'false').lower() == 'true'
    try:
        near_threshold = int(request.args.get('near_threshold', 6))
        limit = int(request.args.get('limit', 5000))
    except ValueError:
        abort(400, 'Invalid duplicate scan parameter')

    try:
        root_path = ctx.resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    events: queue.Queue[dict[str, Any]] = queue.Queue()

    def progress_callback(progress: dict[str, Any]) -> None:
        events.put({'type': 'progress', 'progress': progress})

    def worker() -> None:
        try:
            payload = ctx.scan_duplicate_assets(
                root=root_path,
                include_near=include_near,
                near_threshold=near_threshold,
                limit=limit,
                progress_callback=progress_callback,
            )
            events.put({'type': 'result', 'root': root_key, **payload})
        except Exception as exc:
            ctx.logger.exception('Duplicate scan failed')
            events.put({'type': 'error', 'error': str(exc)})
        finally:
            events.put({'type': 'done'})

    threading.Thread(target=worker, daemon=True).start()

    @stream_with_context
    def generate():
        while True:
            event = events.get()
            yield json.dumps(event) + "\n"
            if event.get('type') == 'done':
                break

    return Response(generate(), mimetype='application/x-ndjson')  # type: ignore[call-arg]


def api_assets_file_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    path = request.args.get('path')
    try:
        abs_path = ctx.resolve_requested_file(path, asset_roots)
    except Exception as e:
        abort(400, str(e))
    mime, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime or 'application/octet-stream')


def api_assets_thumb_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    path = request.args.get('path')
    size = int(request.args.get('size', 256))
    try:
        abs_path = ctx.resolve_requested_file(path, asset_roots)
    except Exception as e:
        abort(400, str(e))
    thumb = ctx.generate_thumbnail_bytes(abs_path, max_size=size)
    if not thumb:
        abort(404, 'Could not generate thumbnail')
    return send_file(
        BytesIO(thumb),
        mimetype='image/png',
        as_attachment=False,
        download_name=Path(abs_path).name + '_thumb.png'
    )


def api_assets_details_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    path = request.args.get('path')
    try:
        abs_path = ctx.resolve_requested_file(path, asset_roots)
        root = ctx.find_root_for_path(abs_path, asset_roots)
        if not root:
            abort(400, 'File not in allowed roots')
        item = ctx.build_asset_item(abs_path, root.path, include_metadata=True)
    except Exception as e:
        abort(400, str(e))
    return jsonify({'asset': item})


def api_assets_repair_metadata_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    payload = request.get_json(silent=True) or {}
    path = payload.get('path')
    overwrite = payload.get('overwrite', False) is True
    try:
        abs_path = ctx.resolve_requested_file(path, asset_roots)
        root = ctx.find_root_for_path(abs_path, asset_roots)
        if not root:
            raise PermissionError('File not in allowed roots')
        result = ctx.repair_png_bubba_metadata(abs_path, overwrite=overwrite)
        item = ctx.build_asset_item(abs_path, root.path, include_metadata=True)
    except Exception as e:
        abort(400, str(e))
    return jsonify({'result': result, 'asset': item})


def api_assets_open_folder_handler():
    ctx = _ctx()
    asset_roots = ctx._get_asset_roots_snapshot()
    payload = request.get_json(silent=True) or {}
    path = payload.get('path')
    try:
        abs_path = ctx.resolve_requested_file(path, asset_roots)
    except Exception as e:
        abort(400, str(e))

    folder = os.path.dirname(abs_path)
    try:
        if os.name == 'nt':
            os.startfile(folder)
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
    except Exception as e:
        ctx.logger.exception('Open folder failed for %s', folder)
        abort(500, str(e))
    return jsonify({'opened': folder})
