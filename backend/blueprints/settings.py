from __future__ import annotations

import importlib

from flask import Blueprint

settings_bp = Blueprint("settings", __name__)


def _server_module():
    return importlib.import_module("server")


@settings_bp.route('/api/settings', methods=['GET'])
def api_settings():
    return _server_module().api_settings()


@settings_bp.route('/api/settings', methods=['PUT'])
def api_update_settings():
    return _server_module().api_update_settings()
