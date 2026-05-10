from __future__ import annotations

from flask import Blueprint

from services import asset_api

assets_bp = Blueprint("assets", __name__)


@assets_bp.route('/bubba/assets/roots', methods=['GET'])
def bubba_assets_roots():
    return asset_api.api_roots_handler()


@assets_bp.route('/bubba/assets/list', methods=['GET'])
def bubba_assets_list():
    return asset_api.api_assets_list_handler()


@assets_bp.route('/bubba/assets/file', methods=['GET'])
def bubba_assets_file():
    return asset_api.api_assets_file_handler()


@assets_bp.route('/bubba/assets/thumb', methods=['GET'])
def bubba_assets_thumb():
    return asset_api.api_assets_thumb_handler()


@assets_bp.route('/bubba/assets/details', methods=['GET'])
def bubba_assets_details():
    return asset_api.api_assets_details_handler()


@assets_bp.route('/bubba/assets/upload', methods=['POST'])
def bubba_assets_upload():
    return asset_api.bubba_assets_upload_handler()


@assets_bp.route('/bubba/assets/delete', methods=['POST'])
def bubba_assets_delete():
    return asset_api.bubba_assets_delete_handler()


@assets_bp.route('/api/roots', methods=['GET'])
def api_roots():
    return asset_api.api_roots_handler()


@assets_bp.route('/api/assets/list', methods=['GET'])
def api_assets_list():
    return asset_api.api_assets_list_handler()


@assets_bp.route('/api/assets/metadata/health', methods=['GET'])
def api_assets_metadata_health():
    return asset_api.api_assets_metadata_health_handler()


@assets_bp.route('/api/assets/stats', methods=['GET'])
def api_assets_stats():
    return asset_api.api_assets_stats_handler()


@assets_bp.route('/api/assets/file', methods=['GET'])
def api_assets_file():
    return asset_api.api_assets_file_handler()


@assets_bp.route('/api/assets/thumb', methods=['GET'])
def api_assets_thumb():
    return asset_api.api_assets_thumb_handler()


@assets_bp.route('/api/assets/details', methods=['GET'])
def api_assets_details():
    return asset_api.api_assets_details_handler()


@assets_bp.route('/api/assets/metadata/repair', methods=['POST'])
def api_assets_repair_metadata():
    return asset_api.api_assets_repair_metadata_handler()


@assets_bp.route('/api/assets/open-folder', methods=['POST'])
def api_assets_open_folder():
    return asset_api.api_assets_open_folder_handler()
