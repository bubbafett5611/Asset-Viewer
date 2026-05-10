from __future__ import annotations

import importlib

from flask import Blueprint

tags_bp = Blueprint("tags", __name__)


def _server_module():
    return importlib.import_module("server")


@tags_bp.route('/danbooru_e621_merged.csv')
def serve_tag_csv():
    return _server_module().serve_tag_csv()


@tags_bp.route('/api/tags', methods=['GET'])
def api_tags():
    return _server_module().api_tags()


@tags_bp.route('/bubba/tag_examples')
def bubba_tag_examples():
    return _server_module().bubba_tag_examples()


@tags_bp.route('/bubba/tag_example_image')
def bubba_tag_example_image():
    return _server_module().bubba_tag_example_image()
