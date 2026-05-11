from __future__ import annotations

import os

from flask import abort, send_file

from runtime_paths import frontend_root


FRONTEND_ROOT = frontend_root()


def index_handler():
    frontend_path = FRONTEND_ROOT / 'asset_viewer_vue.html'
    if not frontend_path.exists():
        return '<h1>Frontend not found</h1>', 404
    return send_file(frontend_path)


def asset_viewer_css_handler():
    css_path = FRONTEND_ROOT / 'asset_viewer.css'
    if not css_path.exists():
        return '', 404
    return send_file(css_path, mimetype='text/css')


def asset_viewer_style_file_handler(filename: str):
    styles_root = (FRONTEND_ROOT / 'styles').resolve()
    requested = (styles_root / filename).resolve()
    if os.path.commonpath([str(styles_root), str(requested)]) != str(styles_root):
        abort(403, 'Invalid style path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='text/css')


def asset_viewer_vue_js_handler():
    js_path = FRONTEND_ROOT / 'asset_viewer_vue.js'
    if not js_path.exists():
        return '', 404
    return send_file(js_path, mimetype='application/javascript')


def asset_viewer_vue_module_handler(filename: str):
    vue_root = (FRONTEND_ROOT / 'vue').resolve()
    requested = (vue_root / filename).resolve()
    if os.path.commonpath([str(vue_root), str(requested)]) != str(vue_root):
        abort(403, 'Invalid module path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='application/javascript')


def asset_viewer_vendor_module_handler(filename: str):
    vendor_root = (FRONTEND_ROOT / 'vendor').resolve()
    requested = (vendor_root / filename).resolve()
    if os.path.commonpath([str(vendor_root), str(requested)]) != str(vendor_root):
        abort(403, 'Invalid vendor path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='application/javascript')
