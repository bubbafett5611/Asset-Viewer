from __future__ import annotations

from flask import Blueprint

from services import asset_api

duplicates_bp = Blueprint("duplicates", __name__)


@duplicates_bp.route('/api/assets/duplicates', methods=['GET'])
def api_assets_duplicates():
    return asset_api.api_assets_duplicates_handler()


@duplicates_bp.route('/api/assets/duplicates/stream', methods=['GET'])
def api_assets_duplicates_stream():
    return asset_api.api_assets_duplicates_stream_handler()


@duplicates_bp.route('/api/assets/duplicates/tasks/<task_id>', methods=['GET'])
def api_assets_duplicate_task_status(task_id: str):
    return asset_api.api_assets_duplicate_task_status_handler(task_id)


@duplicates_bp.route('/api/assets/duplicates/tasks/<task_id>/cancel', methods=['POST'])
def api_assets_duplicate_task_cancel(task_id: str):
    return asset_api.api_assets_duplicate_task_cancel_handler(task_id)