"""HTTP handlers for copy formats, cull ratings, XY sweeps, Send to… and NSFW analysis."""

from __future__ import annotations

import os

from asset_viewer import Image, find_root_for_path, resolve_requested_file, resolve_requested_root
from flask import abort, jsonify, request

from services.app_context import _get_asset_roots_snapshot, logger
from services.asset_index import indexed_rows_with_metadata, nsfw_for_path, pending_nsfw_scans, set_asset_ratings
from services.copy_formats import copy_formats_from_png_info
from services.send_targets import (
    SendError,
    bubba_config_dir,
    list_targets,
    send_to_discord,
    send_to_immich,
    validate_send_paths,
)
from services.sweep_groups import build_sweep_group, sweep_key
from services import nsfw_scan_tasks
from services.nsfw_detect import PRESETS, models_available
from services.nsfw_settings import current_model_dir, current_nsfw_options


def _resolve_file_in_roots(path) -> tuple[str, str]:
    """(absolute path, root path) for a requested file, or a 400."""
    asset_roots = _get_asset_roots_snapshot()
    try:
        abs_path = resolve_requested_file(path, asset_roots)
        root = find_root_for_path(abs_path, asset_roots)
        if not root:
            raise PermissionError('File not in allowed roots')
    except Exception as error:
        abort(400, str(error))
    return abs_path, os.path.abspath(root.path)


def _resolve_root(root_key) -> str:
    try:
        return resolve_requested_root(root_key, _get_asset_roots_snapshot())
    except Exception as error:
        abort(400, str(error))


def api_copy_formats_handler():
    abs_path, _ = _resolve_file_in_roots(request.args.get('path'))
    info: dict = {}
    if abs_path.lower().endswith('.png') and Image is not None:
        try:
            with Image.open(abs_path) as image:
                info = dict(getattr(image, 'info', {}) or {})
        except Exception:
            logger.exception('Could not read PNG text chunks: %s', abs_path)
    return jsonify({'path': abs_path, **copy_formats_from_png_info(info)})


def api_assets_rating_handler():
    """Cull mode: mark paths keep / reject, or clear them (rating null)."""
    payload = request.get_json(silent=True) or {}
    requested_paths = payload.get('paths')
    if isinstance(payload.get('path'), str):
        requested_paths = [payload['path']]
    if not isinstance(requested_paths, list) or not requested_paths:
        abort(400, 'No paths provided')
    rating = payload.get('rating') or None
    if rating not in (None, 'keep', 'reject'):
        abort(400, 'Rating must be keep, reject or null.')
    by_root: dict[str, list[str]] = {}
    updated, errors = [], []
    for requested_path in requested_paths:
        if not isinstance(requested_path, str):
            continue
        try:
            asset_roots = _get_asset_roots_snapshot()
            abs_path = resolve_requested_file(requested_path, asset_roots)
            root = find_root_for_path(abs_path, asset_roots)
            if not root:
                raise PermissionError('File not in allowed roots')
            by_root.setdefault(os.path.abspath(root.path), []).append(abs_path)
            updated.append(requested_path)
        except Exception as error:
            errors.append({'path': requested_path, 'error': str(error)})
    for root_path, paths in by_root.items():
        set_asset_ratings(root_path, paths, rating)
    return jsonify({'rating': rating, 'updated': updated, 'errors': errors})


def _image_size(path: str):
    try:
        with Image.open(path) as image:
            return image.size
    except Exception:
        return None


def api_assets_sweep_handler():
    """The labelled XY grid for the sweep an image belongs to (404 when it is not a sweep image)."""
    abs_path, root_path = _resolve_file_in_roots(request.args.get('path'))
    rows = indexed_rows_with_metadata(root_path, like='sweep')
    target = next((row for row in rows if os.path.abspath(row['path']) == abs_path), None)
    if target is None or not sweep_key(target['metadata']):
        return jsonify({'error': 'This image is not part of an XY sweep.'}), 404
    group = build_sweep_group(abs_path, rows, _image_size)
    metadata_by_path = {row['path']: row['metadata'] for row in rows}
    options = current_nsfw_options()
    for entry in [*group['cells'], *([group['sheet']] if group['sheet'] else [])]:
        entry['nsfw'] = nsfw_for_path(root_path, entry['path'], metadata_by_path.get(entry['path'], {}), options)
    return jsonify({'path': abs_path, 'sweep': group})


def _comfyui_user_dir() -> str:
    from settings_model import Settings

    return str(Settings().integrations.comfyui_user_dir or '')


def api_send_targets_handler():
    return jsonify(list_targets(_comfyui_user_dir()))


def _bubba_for(path: str):
    from services.asset_viewer_metadata import parse_png_metadata

    if not path.lower().endswith('.png'):
        return None
    return parse_png_metadata(path, image_module=Image).get('bubba_metadata')


def api_send_handler():
    """Send files to a Bubba Nodes destination. The UI must confirm first and pass confirmed: true."""
    payload = request.get_json(silent=True) or {}
    if payload.get('confirmed') is not True:
        return jsonify({'error': 'Sending needs confirmation.'}), 400
    target = str(payload.get('target') or '')
    requested = payload.get('paths') if isinstance(payload.get('paths'), list) else []
    paths = [_resolve_file_in_roots(path)[0] for path in requested if isinstance(path, str)]
    try:
        validate_send_paths(paths)
        config_dir = bubba_config_dir(_comfyui_user_dir())
        if target.startswith('discord:'):
            result = send_to_discord(
                config_dir, target.split(':', 1)[1], paths, str(payload.get('message') or ''), _bubba_for
            )
        elif target == 'immich':
            result = send_to_immich(config_dir, paths)
        else:
            raise SendError('Choose a destination.')
    except SendError as error:
        return jsonify({'error': str(error)}), error.status
    logger.info('Sent %d file(s) to %s', result['sent'], result['destination'])
    return jsonify(result)


NSFW_SETTING_KEYS = ('preview', 'nsfw_blur', 'nsfw_blur_style', 'nsfw_preset', 'nsfw_sensitivity', 'nsfw_see_through')


def _nsfw_settings_payload(viewer) -> dict:
    return {key: getattr(viewer, key) for key in NSFW_SETTING_KEYS}


def api_nsfw_status_handler():
    from settings_model import Settings

    root_path = _resolve_root(request.args.get('root'))
    task = nsfw_scan_tasks.get_task(root_path)
    return jsonify(
        {
            'settings': _nsfw_settings_payload(Settings().viewer),
            'presets': {name: dict(values) for name, values in PRESETS.items()},
            'models': models_available(current_model_dir()),
            'pending': len(pending_nsfw_scans(root_path)),
            'task': task.snapshot() if task else None,
        }
    )


def api_nsfw_settings_handler():
    """Update only the blur / NSFW viewer settings (the rest of settings.json is left alone)."""
    from services import app_context
    from settings_model import Settings, save_settings, validate_settings_payload

    payload = request.get_json(silent=True) or {}
    current = Settings().model_dump(mode='json')
    for key in NSFW_SETTING_KEYS:
        if key in payload:
            current['viewer'][key] = payload[key]
    preset = current['viewer'].get('nsfw_preset')
    if preset in PRESETS and 'nsfw_preset' in payload:
        # Picking a preset also moves the slider and switch to that preset's values.
        current['viewer']['nsfw_sensitivity'] = PRESETS[preset]['sensitivity']
        current['viewer']['nsfw_see_through'] = PRESETS[preset]['see_through']
    try:
        settings = validate_settings_payload(current)
    except Exception as error:
        return jsonify({'error': str(error)}), 400
    save_settings(app_context.SETTINGS_FILE, settings)
    return jsonify({'settings': _nsfw_settings_payload(settings.viewer)})


def api_nsfw_scan_handler():
    payload = request.get_json(silent=True) or {}
    root_path = _resolve_root(payload.get('root'))
    if payload.get('action') == 'cancel':
        task = nsfw_scan_tasks.request_cancel(root_path)
        return jsonify({'task': task.snapshot() if task else None})
    models = models_available(current_model_dir())
    if not models['onnxruntime']:
        return jsonify({'error': 'Install onnxruntime in the viewer environment to scan (pip install onnxruntime).'}), 400
    if not models['nudenet']:
        return jsonify({'error': f"NudeNet model 640m.onnx not found in {models['model_dir']}."}), 400
    task = nsfw_scan_tasks.start_scan(root_path, current_model_dir())
    return jsonify({'task': task.snapshot()})
