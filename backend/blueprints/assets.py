from __future__ import annotations

import importlib

from flask import Blueprint

assets_bp = Blueprint("assets", __name__)


def _server_module():
    # Resolve lazily to avoid import cycles during app factory bootstrap.
    return importlib.import_module("server")


@assets_bp.route('/bubba/assets/roots', methods=['GET'])
def bubba_assets_roots():
    return _server_module().bubba_assets_roots()


@assets_bp.route('/bubba/assets/list', methods=['GET'])
def bubba_assets_list():
    return _server_module().bubba_assets_list()


@assets_bp.route('/bubba/assets/file', methods=['GET'])
def bubba_assets_file():
    return _server_module().bubba_assets_file()


@assets_bp.route('/bubba/assets/thumb', methods=['GET'])
def bubba_assets_thumb():
    return _server_module().bubba_assets_thumb()


@assets_bp.route('/bubba/assets/details', methods=['GET'])
def bubba_assets_details():
    return _server_module().bubba_assets_details()


@assets_bp.route('/bubba/assets/upload', methods=['POST'])
def bubba_assets_upload():
    return _server_module().bubba_assets_upload()


@assets_bp.route('/bubba/assets/delete', methods=['POST'])
def bubba_assets_delete():
    return _server_module().bubba_assets_delete()


@assets_bp.route('/api/roots', methods=['GET'])
def api_roots():
    return _server_module().api_roots()


@assets_bp.route('/api/assets/list', methods=['GET'])
def api_assets_list():
    return _server_module().api_assets_list()


@assets_bp.route('/api/assets/metadata/health', methods=['GET'])
def api_assets_metadata_health():
    return _server_module().api_assets_metadata_health()


@assets_bp.route('/api/assets/stats', methods=['GET'])
def api_assets_stats():
    return _server_module().api_assets_stats()


@assets_bp.route('/api/assets/duplicates', methods=['GET'])
def api_assets_duplicates():
    return _server_module().api_assets_duplicates()


@assets_bp.route('/api/assets/duplicates/stream', methods=['GET'])
def api_assets_duplicates_stream():
    return _server_module().api_assets_duplicates_stream()


@assets_bp.route('/api/assets/file', methods=['GET'])
def api_assets_file():
    return _server_module().api_assets_file()


@assets_bp.route('/api/assets/thumb', methods=['GET'])
def api_assets_thumb():
    return _server_module().api_assets_thumb()


@assets_bp.route('/api/assets/details', methods=['GET'])
def api_assets_details():
    return _server_module().api_assets_details()


@assets_bp.route('/api/assets/metadata/repair', methods=['POST'])
def api_assets_repair_metadata():
    return _server_module().api_assets_repair_metadata()


@assets_bp.route('/api/assets/open-folder', methods=['POST'])
def api_assets_open_folder():
    return _server_module().api_assets_open_folder()
