from __future__ import annotations

from flask import Blueprint

from services import tag_api

tags_bp = Blueprint("tags", __name__)


@tags_bp.route('/danbooru_e621_merged.csv')
def serve_tag_csv():
    return tag_api.serve_tag_csv_handler()


@tags_bp.route('/api/tags', methods=['GET'])
def api_tags():
    return tag_api.api_tags_handler()


@tags_bp.route('/bubba/tag_examples')
def bubba_tag_examples():
    return tag_api.bubba_tag_examples_handler()


@tags_bp.route('/bubba/tag_example_image')
def bubba_tag_example_image():
    return tag_api.bubba_tag_example_image_handler()
