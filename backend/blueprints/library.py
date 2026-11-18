from __future__ import annotations

from flask import Blueprint

from services import library_api

library_bp = Blueprint("library", __name__)


@library_bp.route('/api/assets/copy-formats', methods=['GET'])
def api_copy_formats():
    return library_api.api_copy_formats_handler()


@library_bp.route('/api/assets/rating', methods=['POST'])
def api_assets_rating():
    return library_api.api_assets_rating_handler()


@library_bp.route('/api/assets/sweep', methods=['GET'])
def api_assets_sweep():
    return library_api.api_assets_sweep_handler()


@library_bp.route('/api/send/targets', methods=['GET'])
def api_send_targets():
    return library_api.api_send_targets_handler()


@library_bp.route('/api/send', methods=['POST'])
def api_send():
    return library_api.api_send_handler()


@library_bp.route('/api/nsfw/status', methods=['GET'])
def api_nsfw_status():
    return library_api.api_nsfw_status_handler()


@library_bp.route('/api/nsfw/settings', methods=['POST'])
def api_nsfw_settings():
    return library_api.api_nsfw_settings_handler()


@library_bp.route('/api/nsfw/scan', methods=['POST'])
def api_nsfw_scan():
    return library_api.api_nsfw_scan_handler()
