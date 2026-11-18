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


@assets_bp.route('/api/assets/folders', methods=['GET'])
def api_assets_folders():
    return asset_api.api_assets_folders_handler()


@assets_bp.route('/api/assets/folders', methods=['POST'])
def api_assets_create_folder():
    return asset_api.api_assets_create_folder_handler()


@assets_bp.route('/api/assets/move', methods=['POST'])
def api_assets_move():
    return asset_api.api_assets_move_handler()


@assets_bp.route('/api/assets/changes', methods=['GET'])
def api_assets_changes():
    return asset_api.api_assets_changes_handler()


@assets_bp.route('/api/assets/facets', methods=['GET'])
def api_assets_facets():
    return asset_api.api_assets_facets_handler()


@assets_bp.route('/api/collections', methods=['GET'])
def api_collections_list():
    return asset_api.api_collections_list_handler()


@assets_bp.route('/api/collections', methods=['POST'])
def api_collections_create():
    return asset_api.api_collections_create_handler()


@assets_bp.route('/api/collections/<int:collection_id>/items', methods=['POST'])
def api_collection_items(collection_id):
    return asset_api.api_collection_items_handler(collection_id)


@assets_bp.route('/api/collections/<int:collection_id>', methods=['PATCH'])
def api_collection_update(collection_id):
    return asset_api.api_collection_update_handler(collection_id)


@assets_bp.route('/api/collections/<int:collection_id>', methods=['DELETE'])
def api_collection_delete(collection_id):
    return asset_api.api_collection_delete_handler(collection_id)


@assets_bp.route('/api/comfy/queue', methods=['POST'])
def api_comfy_queue():
    return asset_api.api_comfy_queue_handler()


@assets_bp.route('/api/assets/favorite', methods=['POST'])
def api_assets_favorite():
    return asset_api.api_assets_favorite_handler()


@assets_bp.route('/api/assets/restore', methods=['POST'])
def api_assets_restore():
    return asset_api.api_assets_restore_handler()


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
