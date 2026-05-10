from __future__ import annotations

import mimetypes
import os
import subprocess
import sys
from io import BytesIO
from pathlib import Path

from asset_viewer import (
    ALLOWED_UPLOAD_IMAGE_EXTENSIONS,
    Image,
    build_asset_item,
    find_root_for_path,
    folder_stats_report,
    generate_thumbnail_bytes,
    make_unique_destination_path,
    metadata_health_report,
    move_file_to_trash,
    repair_png_bubba_metadata,
    resolve_requested_file,
    resolve_requested_root,
    sanitize_upload_filename,
    scan_assets,
    scan_duplicate_assets,
)
from flask import Response, abort, jsonify, request, send_file, stream_with_context

from services.app_context import _get_asset_roots_snapshot, logger
from services.duplicate_scan_tasks import (
    create_duplicate_scan_task,
    get_duplicate_scan_task,
    request_duplicate_scan_cancel,
    stream_duplicate_scan_events,
)


def bubba_assets_upload_handler():
    asset_roots = _get_asset_roots_snapshot()
    root_key = request.args.get('root')
    try:
        dest_root = resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    files = request.files.getlist('files') if hasattr(request, 'files') else []
    uploaded = []
    skipped = []

    for f in files:
        fname = getattr(f, 'filename', None) or 'upload.png'
        filename = sanitize_upload_filename(fname)
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_UPLOAD_IMAGE_EXTENSIONS:
            skipped.append({'filename': fname, 'error': f'Invalid extension: {ext}'})
            logger.warning('Upload skipped invalid extension: %s', fname)
            continue

        try:
            content = f.read()
            if Image is not None:
                try:
                    bio = BytesIO(content)
                    img = Image.open(bio)
                    img.verify()
                except Exception:
                    skipped.append({'filename': fname, 'error': 'Invalid image file'})
                    logger.warning('Upload skipped invalid image: %s', fname)
                    continue

            dest_path = make_unique_destination_path(dest_root, filename)
            with open(dest_path, 'wb') as fh:
                fh.write(content)

            logger.info('Uploaded file: %s -> %s', filename, dest_path)
            uploaded.append(build_asset_item(dest_path, dest_root))
        except Exception as ex:
            logger.exception('Upload failed for %s', fname)
            skipped.append({'filename': fname, 'error': str(ex)})

    return jsonify({'uploaded': uploaded, 'skipped': skipped})


def bubba_assets_delete_handler():
    asset_roots = _get_asset_roots_snapshot()
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
            abs_path = resolve_requested_file(p, asset_roots)
            root = find_root_for_path(abs_path, asset_roots)
            if not root:
                raise PermissionError('File not in allowed roots')
            if os.path.exists(abs_path):
                if safe_delete:
                    destination = move_file_to_trash(abs_path, root.path)
                    moved.append({'path': p, 'destination': destination})
                else:
                    os.remove(abs_path)
                deleted.append(p)
                logger.info('Deleted file: %s', abs_path)
            else:
                errors.append({'path': p, 'error': 'File not found'})
        except Exception as e:
            logger.exception('Delete failed for %s', p)
            errors.append({'path': p, 'error': str(e)})

    return jsonify({'deleted': deleted, 'moved': moved, 'safe_delete': safe_delete, 'errors': errors})


def api_roots_handler():
    asset_roots = _get_asset_roots_snapshot()
    return jsonify({'roots': [root.__dict__ for root in asset_roots]})


def api_assets_list_handler():
    asset_roots = _get_asset_roots_snapshot()
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
        root_path = resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    assets = scan_assets(
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
    asset_roots = _get_asset_roots_snapshot()
    root_key = request.args.get('root')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    cache_only = request.args.get('cache_only', 'false').lower() == 'true'
    try:
        limit = int(request.args.get('limit', 10000))
    except ValueError:
        abort(400, 'Invalid metadata health parameter')
    try:
        root_path = resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))
    report, cached = metadata_health_report(root_path, limit=limit, refresh=refresh, cache_only=cache_only)
    return jsonify({'root': root_key, 'stats': report.model_dump(mode='json') if report else None, 'cached': cached})


def api_assets_stats_handler():
    asset_roots = _get_asset_roots_snapshot()
    root_key = request.args.get('root')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    cache_only = request.args.get('cache_only', 'false').lower() == 'true'
    try:
        root_path = resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))
    report, cached = folder_stats_report(root_path, refresh=refresh, cache_only=cache_only)
    return jsonify({'root': root_key, 'stats': report.model_dump(mode='json') if report else None, 'cached': cached})


def api_assets_duplicates_handler():
    asset_roots = _get_asset_roots_snapshot()
    root_key = request.args.get('root')
    include_near = request.args.get('include_near', 'false').lower() == 'true'
    try:
        near_threshold = int(request.args.get('near_threshold', 6))
        limit = int(request.args.get('limit', 5000))
    except ValueError:
        abort(400, 'Invalid duplicate scan parameter')

    try:
        root_path = resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    payload = scan_duplicate_assets(
        root=root_path,
        include_near=include_near,
        near_threshold=near_threshold,
        limit=limit,
    )
    return jsonify({'root': root_key, **payload})


def api_assets_duplicate_task_status_handler(task_id: str):
    task = get_duplicate_scan_task(task_id)
    if not task:
        abort(404, 'Duplicate task not found')
    return jsonify(task.snapshot())


def api_assets_duplicate_task_cancel_handler(task_id: str):
    task = request_duplicate_scan_cancel(task_id)
    if not task:
        abort(404, 'Duplicate task not found')
    return jsonify(task.snapshot())


def api_assets_duplicates_stream_handler():
    asset_roots = _get_asset_roots_snapshot()
    root_key = request.args.get('root')
    include_near = request.args.get('include_near', 'false').lower() == 'true'
    try:
        near_threshold = int(request.args.get('near_threshold', 6))
        limit = int(request.args.get('limit', 5000))
    except ValueError:
        abort(400, 'Invalid duplicate scan parameter')

    try:
        root_path = resolve_requested_root(root_key, asset_roots)
    except Exception as e:
        abort(400, str(e))

    task = create_duplicate_scan_task(
        root=root_path,
        include_near=include_near,
        near_threshold=near_threshold,
        limit=limit,
    )
    event_stream = stream_with_context(
        stream_duplicate_scan_events(task, scan_duplicate_assets, logger, root_key=root_key)
    )
    return Response(event_stream, mimetype='application/x-ndjson')


def api_assets_file_handler():
    asset_roots = _get_asset_roots_snapshot()
    path = request.args.get('path')
    try:
        abs_path = resolve_requested_file(path, asset_roots)
    except Exception as e:
        abort(400, str(e))
    mime, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime or 'application/octet-stream')


def api_assets_thumb_handler():
    asset_roots = _get_asset_roots_snapshot()
    path = request.args.get('path')
    size = int(request.args.get('size', 256))
    try:
        abs_path = resolve_requested_file(path, asset_roots)
    except Exception as e:
        abort(400, str(e))
    thumb = generate_thumbnail_bytes(abs_path, max_size=size)
    if not thumb:
        abort(404, 'Could not generate thumbnail')
    return send_file(
        BytesIO(thumb),
        mimetype='image/png',
        as_attachment=False,
        download_name=Path(abs_path).name + '_thumb.png'
    )


def api_assets_details_handler():
    asset_roots = _get_asset_roots_snapshot()
    path = request.args.get('path')
    try:
        abs_path = resolve_requested_file(path, asset_roots)
        root = find_root_for_path(abs_path, asset_roots)
        if not root:
            abort(400, 'File not in allowed roots')
        item = build_asset_item(abs_path, root.path, include_metadata=True)
    except Exception as e:
        abort(400, str(e))
    return jsonify({'asset': item})


def api_assets_repair_metadata_handler():
    asset_roots = _get_asset_roots_snapshot()
    payload = request.get_json(silent=True) or {}
    path = payload.get('path')
    overwrite = payload.get('overwrite', False) is True
    try:
        abs_path = resolve_requested_file(path, asset_roots)
        root = find_root_for_path(abs_path, asset_roots)
        if not root:
            raise PermissionError('File not in allowed roots')
        result = repair_png_bubba_metadata(abs_path, overwrite=overwrite)
        item = build_asset_item(abs_path, root.path, include_metadata=True)
    except Exception as e:
        abort(400, str(e))
    return jsonify({'result': result, 'asset': item})


def api_assets_open_folder_handler():
    asset_roots = _get_asset_roots_snapshot()
    payload = request.get_json(silent=True) or {}
    path = payload.get('path')
    try:
        abs_path = resolve_requested_file(path, asset_roots)
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
        logger.exception('Open folder failed for %s', folder)
        abort(500, str(e))
    return jsonify({'opened': folder})
