from __future__ import annotations

from flask import abort, jsonify, request

from services import app_context
from settings_model import Settings, save_settings, validate_settings_payload


def api_settings_handler():
    settings = Settings()
    return jsonify({'settings': settings.model_dump(mode='json'), 'schema': Settings.model_json_schema()})


def api_update_settings_handler():
    payload = request.get_json(silent=True) or {}
    try:
        settings = validate_settings_payload(payload)
    except Exception as error:
        abort(400, str(error))
    save_settings(app_context.SETTINGS_FILE, settings)
    updated_roots = app_context._asset_roots_from_settings(settings)
    app_context._set_asset_roots(updated_roots)
    return jsonify(
        {
            'settings': settings.model_dump(mode='json'),
            'schema': Settings.model_json_schema(),
            'roots': [root.__dict__ for root in updated_roots],
        }
    )