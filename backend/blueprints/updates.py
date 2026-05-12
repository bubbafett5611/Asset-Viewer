from __future__ import annotations

from flask import Blueprint

from services import update_api

updates_bp = Blueprint("updates", __name__)


@updates_bp.route('/api/update/latest', methods=['GET'])
def api_update_latest():
    return update_api.api_update_latest_handler()


@updates_bp.route('/api/app/info', methods=['GET'])
def api_app_info():
    return update_api.api_app_info_handler()
