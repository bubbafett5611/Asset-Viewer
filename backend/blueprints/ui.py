from __future__ import annotations

import importlib

from flask import Blueprint

ui_bp = Blueprint("ui", __name__)


def _server_module():
    return importlib.import_module("server")


@ui_bp.route('/')
def index():
    return _server_module().index()


@ui_bp.route('/asset_viewer.css')
def asset_viewer_css():
    return _server_module().asset_viewer_css()


@ui_bp.route('/styles/<path:filename>')
def asset_viewer_style_file(filename):
    return _server_module().asset_viewer_style_file(filename)


@ui_bp.route('/asset_viewer_vue.js')
def asset_viewer_vue_js():
    return _server_module().asset_viewer_vue_js()


@ui_bp.route('/vue/<path:filename>')
def asset_viewer_vue_module(filename):
    return _server_module().asset_viewer_vue_module(filename)
