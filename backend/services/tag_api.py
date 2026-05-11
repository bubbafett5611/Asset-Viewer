from __future__ import annotations

import csv
from pathlib import Path
import re
import threading
import time
from typing import Any
from urllib.parse import quote_plus, urlparse

import requests
from bs4 import BeautifulSoup
from flask import Response, abort, jsonify, request, send_file

from runtime_paths import frontend_root
from services import app_context

TAG_LIST_DIR_URL = 'https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru_e621_merged'
RAW_BASE = 'https://raw.githubusercontent.com/DraconicDragon/dbr-e621-lists-archive/main/tag-lists/danbooru_e621_merged/'
TAG_LIST_LOCAL = frontend_root() / 'danbooru_e621_merged.csv'
FALLBACK_FETCH_LIMIT = 50
DISALLOWED_EXTS = {'.webm', '.mp4', '.gif'}
TAG_LIST_HEADER = 'name,category,count,aliases'

_tag_list_lock = threading.Lock()
_tag_list_ready = False
_cache_lock = threading.Lock()
_example_cache: dict[str, tuple[float, dict[str, Any]]] = {}
_image_cache: dict[str, tuple[float, bytes, str]] = {}

EXAMPLE_CACHE_TTL = 300
IMAGE_CACHE_TTL = 3600
_MAX_EXAMPLE_CACHE_ITEMS = 200
_MAX_IMAGE_CACHE_ITEMS = 400


def _has_disallowed_ext_from_url(url: str) -> bool:
    if not url:
        return False
    try:
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower()
        return ext in DISALLOWED_EXTS
    except Exception:
        return False


def _fetch_text(url: str, headers: dict[str, Any] | None = None, timeout: int = 12) -> str:
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
        response.raise_for_status()
        return response.text or ''
    except Exception:
        return ''


def _fetch_json_list(url: str, headers: dict[str, Any] | None = None, timeout: int = 12, list_key: str | None = None) -> list[Any]:
    try:
        response = requests.get(url, headers=headers or {}, timeout=timeout)
        response.raise_for_status()
        if not response.text:
            return []
        payload = response.json()
        if list_key and isinstance(payload, dict):
            value = payload.get(list_key)
            return value if isinstance(value, list) else []
        return payload if isinstance(payload, list) else []
    except Exception:
        return []


def _api_headers(site: str | None = None, base: dict[str, Any] | None = None) -> dict[str, str]:
    headers = dict(base or {})
    ua = headers.get('User-Agent') or 'BubbaAssetViewer/1.0'
    headers['User-Agent'] = f'{ua} (contact: none@example.com)'
    if site == 'e621':
        headers['Referer'] = 'https://e621.net'
    elif site == 'danbooru':
        headers['Referer'] = 'https://danbooru.donmai.us'
    return headers


def _build_example(site: str, post: dict[str, Any] | None, score: int, image_url: str) -> dict[str, Any]:
    if not isinstance(post, dict):
        return {'status': 'empty'}
    post_id = post.get('id')
    if site == 'danbooru':
        page_url = f'https://danbooru.donmai.us/posts/{post_id}' if post_id is not None else ''
        return {
            'status': 'ok' if image_url else 'empty',
            'post_id': post_id,
            'score': score,
            'image_url': image_url,
            'preview_url': post.get('preview_file_url'),
            'page_url': page_url,
            'post_url': page_url,
            'tags': post.get('tag_string'),
        }
    page_url = f'https://e621.net/posts/{post_id}' if post_id is not None else ''
    return {
        'status': 'ok' if image_url else 'empty',
        'post_id': post_id,
        'score': score,
        'image_url': image_url,
        'page_url': page_url,
        'post_url': page_url,
        'tags': post.get('tags') if isinstance(post.get('tags'), (dict, list)) else post.get('tags'),
    }


def _danbooru_build_image_url_from_post(post: dict[str, Any] | None) -> str:
    if not isinstance(post, dict):
        return ''
    return post.get('large_file_url') or post.get('file_url') or post.get('preview_file_url') or ''


def _danbooru_get_score(post: dict[str, Any] | None) -> int:
    if not isinstance(post, dict):
        return 0
    try:
        return int(post.get('score', 0))
    except Exception:
        return 0


def _e621_build_image_url_from_post(post: dict[str, Any] | None) -> str:
    if not isinstance(post, dict):
        return ''
    sample_raw = post.get('sample')
    file_raw = post.get('file')
    preview_raw = post.get('preview')
    sample: dict[str, Any] = sample_raw if isinstance(sample_raw, dict) else {}
    fileobj: dict[str, Any] = file_raw if isinstance(file_raw, dict) else {}
    preview: dict[str, Any] = preview_raw if isinstance(preview_raw, dict) else {}
    candidate = sample.get('url') or fileobj.get('url') or preview.get('url') or ''
    if not candidate:
        md5 = fileobj.get('md5')
        ext = fileobj.get('ext')
        if md5 and ext:
            candidate = f'https://static1.e621.net/data/{md5[0:2]}/{md5[2:4]}/{md5}.{ext}'
    return candidate or ''


def _e621_get_score(post: dict[str, Any] | None) -> int:
    if not isinstance(post, dict):
        return 0
    score = post.get('score', 0)
    if isinstance(score, dict):
        try:
            return int(score.get('total') or score.get('up') or 0)
        except Exception:
            return 0
    try:
        return int(score)
    except Exception:
        return 0


def _pick_best_post(posts: Any, image_getter, score_getter) -> tuple[dict[str, Any] | None, int]:
    if not isinstance(posts, list):
        return None, 0
    best: dict[str, Any] | None = None
    best_score = -2**63
    for post in posts:
        image_url = image_getter(post)
        if not image_url or _has_disallowed_ext_from_url(image_url):
            continue
        score = score_getter(post)
        if best is None or score > best_score:
            best = post
            best_score = score
    if best is None:
        return None, 0
    return best, best_score


def ensure_tag_list() -> None:
    global _tag_list_ready
    with _tag_list_lock:
        if _tag_list_ready:
            return
    if not TAG_LIST_LOCAL.exists():
        html = _fetch_text(TAG_LIST_DIR_URL)
        if not html:
            raise RuntimeError('Failed to fetch tag list directory listing.')
        soup = BeautifulSoup(html, 'html.parser')
        files = [link.text for link in soup.find_all('a', href=True) if link.text.endswith('.csv')]
        if not files:
            raise RuntimeError('No CSV files found in tag list directory.')
        files.sort(reverse=True)
        raw_text = _fetch_text(RAW_BASE + files[0])
        if not raw_text:
            raise RuntimeError(f'Failed to fetch tag list file: {RAW_BASE + files[0]}')
        lines = raw_text.splitlines()
        if not lines[0].lower().startswith(TAG_LIST_HEADER):
            lines.insert(0, TAG_LIST_HEADER)
        TAG_LIST_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        with open(TAG_LIST_LOCAL, 'w', encoding='utf-8', newline='') as handle:
            writer = csv.writer(handle)
            for row in csv.reader(lines):
                writer.writerow(row)
    else:
        with open(TAG_LIST_LOCAL, 'r', encoding='utf-8') as handle:
            lines = handle.read().splitlines()
        if lines and not lines[0].lower().startswith(TAG_LIST_HEADER):
            lines.insert(0, TAG_LIST_HEADER)
            with open(TAG_LIST_LOCAL, 'w', encoding='utf-8', newline='') as handle:
                for line in lines:
                    handle.write(line + '\n')
    _tag_list_ready = True


def _ensure_tag_list_available():
    try:
        ensure_tag_list()
        return None
    except Exception as error:
        app_context.logger.exception('Failed to ensure local tag list is available')
        return jsonify({'error': f'Failed to prepare tag list: {error}'}), 503


def _cache_get_examples(tag: str):
    now = time.time()
    with _cache_lock:
        entry = _example_cache.get(tag)
        if not entry:
            return None
        ts, payload = entry
        if now - ts > EXAMPLE_CACHE_TTL:
            del _example_cache[tag]
            return None
        return payload


def _cache_set_examples(tag: str, payload: dict[str, Any]) -> None:
    now = time.time()
    with _cache_lock:
        _example_cache[tag] = (now, payload)
        if len(_example_cache) > _MAX_EXAMPLE_CACHE_ITEMS:
            items = sorted(_example_cache.items(), key=lambda item: item[1][0])
            for key, _ in items[: len(_example_cache) - _MAX_EXAMPLE_CACHE_ITEMS]:
                del _example_cache[key]


def _cache_get_image(url: str):
    now = time.time()
    with _cache_lock:
        entry = _image_cache.get(url)
        if not entry:
            return None, None
        ts, data, content_type = entry
        if now - ts > IMAGE_CACHE_TTL:
            del _image_cache[url]
            return None, None
        return data, content_type


def _cache_set_image(url: str, data: bytes, content_type: str) -> None:
    now = time.time()
    with _cache_lock:
        _image_cache[url] = (now, data, content_type)
        if len(_image_cache) > _MAX_IMAGE_CACHE_ITEMS:
            items = sorted(_image_cache.items(), key=lambda item: item[1][0])
            for key, _ in items[: len(_image_cache) - _MAX_IMAGE_CACHE_ITEMS]:
                del _image_cache[key]


def serve_tag_csv_handler():
    failure = _ensure_tag_list_available()
    if failure is not None:
        return failure
    return send_file(TAG_LIST_LOCAL, mimetype='text/csv')


def api_tags_handler():
    failure = _ensure_tag_list_available()
    if failure is not None:
        return failure
    query = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    try:
        limit = max(1, min(int(request.args.get('limit', 300)), 1000))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        abort(400, 'Invalid pagination parameter')

    normalized_query = re.sub(r'[\s_-]+', '_', query.lower()).strip('_')
    tags: list[dict[str, Any]] = []
    categories: set[str] = set()
    matched_count = 0
    with open(TAG_LIST_LOCAL, 'r', encoding='utf-8') as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            row_category = str(row.get('category') or '')
            categories.add(row_category)
            if category and row_category != category:
                continue
            if normalized_query:
                search_blob = re.sub(r'[\s_-]+', '_', f"{row.get('name', '')} {row.get('aliases', '')}".lower())
                if normalized_query not in search_blob:
                    continue
            if matched_count >= offset and len(tags) < limit:
                tags.append(row)
            matched_count += 1
    return jsonify(
        {
            'tags': tags,
            'total': matched_count,
            'limit': limit,
            'offset': offset,
            'categories': sorted(value for value in categories if value),
        }
    )


def bubba_tag_examples_handler():
    tag = request.args.get('tag', '').strip()
    if not tag:
        return jsonify({'examples': {}})
    cached = _cache_get_examples(tag)
    if cached is not None:
        app_context.logger.info('Tag examples cache hit: %s', tag)
        return jsonify({'examples': cached})

    examples: dict[str, Any] = {}
    headers = {'User-Agent': 'BubbaAssetViewer/1.0 (contact: none@example.com)', 'Referer': 'http://127.0.0.1'}

    dan_tags = quote_plus(f'{tag} order:score age:<1month -is:mp4 -is:gif')
    dan_posts = _fetch_json_list(
        f'https://danbooru.donmai.us/posts.json?tags={dan_tags}&limit=1', headers=_api_headers('danbooru', headers), timeout=10
    )
    if dan_posts:
        dan_post = dan_posts[0]
        image_url = _danbooru_build_image_url_from_post(dan_post)
        if not _has_disallowed_ext_from_url(image_url):
            examples['danbooru'] = _build_example('danbooru', dan_post, _danbooru_get_score(dan_post), image_url)
    if not examples.get('danbooru'):
        dan_posts = _fetch_json_list(
            f'https://danbooru.donmai.us/posts.json?tags={quote_plus(f"{tag} age:<1month")}&limit={FALLBACK_FETCH_LIMIT}',
            headers=_api_headers('danbooru', headers),
            timeout=12,
        )
        best, best_score = _pick_best_post(dan_posts, _danbooru_build_image_url_from_post, _danbooru_get_score)
        if not best:
            dan_posts = _fetch_json_list(
                f'https://danbooru.donmai.us/posts.json?tags={quote_plus(tag)}&limit={FALLBACK_FETCH_LIMIT}',
                headers=_api_headers('danbooru', headers),
                timeout=12,
            )
            best, best_score = _pick_best_post(dan_posts, _danbooru_build_image_url_from_post, _danbooru_get_score)
        examples['danbooru'] = (
            _build_example('danbooru', best, best_score, _danbooru_build_image_url_from_post(best))
            if best
            else {'status': 'empty', 'error': 'No posts found'}
        )

    e_posts = _fetch_json_list(
        f'https://e621.net/posts.json?tags={quote_plus(f"{tag} order:score -type:webm -type:mp4 -type:gif")}&limit=1',
        headers=_api_headers('e621', headers),
        timeout=10,
        list_key='posts',
    )
    if e_posts:
        e_post = e_posts[0]
        image_url = _e621_build_image_url_from_post(e_post)
        if not _has_disallowed_ext_from_url(image_url):
            examples['e621'] = _build_example('e621', e_post, _e621_get_score(e_post), image_url)
    if not examples.get('e621'):
        e_posts = _fetch_json_list(
            f'https://e621.net/posts.json?tags={quote_plus(f"{tag} date:month -type:webm -type:mp4 -type:gif")}&limit={FALLBACK_FETCH_LIMIT}',
            headers=_api_headers('e621', headers),
            timeout=12,
            list_key='posts',
        )
        best, best_score = _pick_best_post(e_posts, _e621_build_image_url_from_post, _e621_get_score)
        if not best:
            e_posts = _fetch_json_list(
                f'https://e621.net/posts.json?tags={quote_plus(tag)}&limit={FALLBACK_FETCH_LIMIT}',
                headers=_api_headers('e621', headers),
                timeout=12,
                list_key='posts',
            )
            best, best_score = _pick_best_post(e_posts, _e621_build_image_url_from_post, _e621_get_score)
        examples['e621'] = (
            _build_example('e621', best, best_score, _e621_build_image_url_from_post(best))
            if best
            else {'status': 'empty', 'error': 'No posts found'}
        )

    _cache_set_examples(tag, examples)
    return jsonify({'examples': examples})


def bubba_tag_example_image_handler():
    url = request.args.get('url', '').strip()
    if not url:
        return '', 404
    cached_data, cached_content_type = _cache_get_image(url)
    if cached_data is not None:
        return Response(cached_data, content_type=cached_content_type)
    try:
        parsed = urlparse(url)
        host = (parsed.netloc or '').lower()
        headers = {'User-Agent': 'BubbaAssetViewer/1.0 (contact: none@example.com)'}
        if host.endswith('donmai.us'):
            headers['Referer'] = 'https://danbooru.donmai.us'
        elif host.endswith('e621.net') or host.endswith('static1.e621.net'):
            headers['Referer'] = 'https://e621.net'
        response = requests.get(url, headers=headers, stream=True, timeout=10)
        response.raise_for_status()
        content_type = response.headers.get('Content-Type', 'image/jpeg')
        body = response.content
        _cache_set_image(url, body, content_type)
        return Response(body, content_type=content_type)
    except Exception as error:
        return f'Failed to fetch image: {error}', 404
