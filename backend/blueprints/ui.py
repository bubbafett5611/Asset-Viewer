from __future__ import annotations

from flask import Blueprint

from services import ui_api

ui_bp = Blueprint("ui", __name__)


@ui_bp.route('/')
def index():
    return ui_api.index_handler()


@ui_bp.route('/asset_viewer.css')
def asset_viewer_css():
    return ui_api.asset_viewer_css_handler()


@ui_bp.route('/styles/<path:filename>')
def asset_viewer_style_file(filename):
    return ui_api.asset_viewer_style_file_handler(filename)


@ui_bp.route('/asset_viewer_vue.js')
def asset_viewer_vue_js():
    return ui_api.asset_viewer_vue_js_handler()


@ui_bp.route('/vue/<path:filename>')
def asset_viewer_vue_module(filename):
    return ui_api.asset_viewer_vue_module_handler(filename)


@ui_bp.route('/vendor/<path:filename>')
def asset_viewer_vendor_module(filename):
    return ui_api.asset_viewer_vendor_module_handler(filename)
