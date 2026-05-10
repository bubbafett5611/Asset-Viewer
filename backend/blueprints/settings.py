from __future__ import annotations

from flask import Blueprint

from services import settings_api

settings_bp = Blueprint("settings", __name__)


@settings_bp.route('/api/settings', methods=['GET'])
def api_settings():
    return settings_api.api_settings_handler()


@settings_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    return settings_api.api_update_settings_handler()
