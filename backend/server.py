import requests
from flask import Response

from pathlib import Path
import csv
import re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse
import logging
import queue
import threading
import time
from io import BytesIO
from typing import Optional, Dict, Any, Tuple, List

TAG_LIST_DIR_URL = "https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru_e621_merged"
RAW_BASE = "https://raw.githubusercontent.com/DraconicDragon/dbr-e621-lists-archive/main/tag-lists/danbooru_e621_merged/"
TAG_LIST_LOCAL = Path(__file__).parent.parent / "frontend" / "danbooru_e621_merged.csv"

FALLBACK_FETCH_LIMIT = 50

DISALLOWED_EXTS = {'.webm', '.mp4', '.gif'}


def _has_disallowed_ext_from_url(url: str) -> bool:
    """Return True if the URL appears to point to a disallowed media extension."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        ext = Path(parsed.path).suffix.lower()
        return ext in DISALLOWED_EXTS
    except Exception:
        return False


def _e621_build_image_url_from_post(p: Optional[Dict[str, Any]]) -> str:
    """Return a usable image URL from an e621 post dict, using sample/file/preview or md5+ext CDN fallback."""
    if not isinstance(p, dict):
        return ""
    # Avoid repeated inline p.get(...) expressions to satisfy static analyzers
    s = p.get('sample')
    sample = s if isinstance(s, dict) else {}
    fobj = p.get('file')
    fileobj = fobj if isinstance(fobj, dict) else {}
    pr = p.get('preview')
    preview = pr if isinstance(pr, dict) else {}
    # prefer sample (often has a usable CDN URL), then file, then preview
    candidate = (sample.get('url') or fileobj.get('url') or preview.get('url') or '')
    if not candidate:
        md5 = fileobj.get('md5')
        ext = fileobj.get('ext')
        if md5 and ext:
            candidate = f"https://static1.e621.net/data/{md5[0:2]}/{md5[2:4]}/{md5}.{ext}"
    return candidate or ""


def _e621_get_score(p: Optional[Dict[str, Any]]) -> int:
    """Return an integer score for an e621 post, handling dict or numeric formats."""
    if not isinstance(p, dict):
        return 0
    sc = p.get('score', 0)
    if isinstance(sc, dict):
        try:
            return int(sc.get('total') or sc.get('up') or 0)
        except Exception:
            return 0
    try:
        return int(sc)
    except Exception:
        return 0


def _danbooru_build_image_url_from_post(p: Optional[Dict[str, Any]]) -> str:
    """Return first-usable image URL from a Danbooru post dict."""
    if not isinstance(p, dict):
        return ""
    # Danbooru JSON provides large_file_url, file_url, preview_file_url
    return p.get('large_file_url') or p.get('file_url') or p.get('preview_file_url') or ""


def _danbooru_get_score(p: Optional[Dict[str, Any]]) -> int:
    """Return integer score for Danbooru post (safe conversion)."""
    if not isinstance(p, dict):
        return 0
    sc = p.get('score', 0)
    try:
        return int(sc)
    except Exception:
        return 0


def _api_headers(site: Optional[str] = None, base: Optional[Dict[str, Any]] = None) -> Dict[str, str]:
    """Return a headers dict for API calls, adding UA and sensible Referer per site."""
    h = dict(base or {})
    ua = h.get('User-Agent') or 'BubbaAssetViewer/1.0'
    h['User-Agent'] = f"{ua} (contact: none@example.com)"
    if site == 'e621':
        h['Referer'] = 'https://e621.net'
    elif site == 'danbooru':
        h['Referer'] = 'https://danbooru.donmai.us'
    return h


def _fetch_json_list(url: str, headers: Optional[Dict[str, Any]] = None, timeout: int = 12, list_key: Optional[str] = None) -> List[Any]:
    """Fetch JSON and return a list payload.

    - If `list_key` is provided, expects a dict response and returns the list at that key.
    - If response is a top-level list, returns it directly.
    - On any error or unexpected shape, returns an empty list.
    """
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        if not r.text:
            return []
        data = r.json()
        if list_key and isinstance(data, dict):
            lst = data.get(list_key)
            return lst if isinstance(lst, list) else []
        if isinstance(data, list):
            return data
        return []
    except Exception:
        return []


def _fetch_text(url: str, headers: Optional[Dict[str, Any]] = None, timeout: int = 12) -> str:
    """Fetch text content or return an empty string on error."""
    try:
        r = requests.get(url, headers=headers or {}, timeout=timeout)
        r.raise_for_status()
        return r.text or ''
    except Exception:
        return ''


def _pick_best_post(posts: Any, image_getter, score_getter) -> Tuple[Optional[Dict[str, Any]], int]:
    """Select the highest-score post that has an allowed image URL.

    Returns a tuple (best_post, best_score) or (None, 0).
    """
    if not isinstance(posts, list):
        return None, 0
    best: Optional[Dict[str, Any]] = None
    best_score: int = -2**63
    for p in posts:
        try:
            image_url = image_getter(p)
        except Exception:
            image_url = ""
        if not image_url or _has_disallowed_ext_from_url(image_url):
            continue
        try:
            sc_raw = score_getter(p)
        except Exception:
            sc_raw = 0
        try:
            sc = int(sc_raw)
        except Exception:
            sc = 0
        if best is None or sc > best_score:
            best = p
            best_score = sc
    if best is None:
        return None, 0
    return best, best_score


def _build_example(site: str, p: Optional[Dict[str, Any]], score: int, image_url: str) -> Dict[str, Any]:
    """Build the canonical example dict for frontend consumption."""
    if not isinstance(p, dict):
        return {'status': 'empty'}
    post_id = p.get('id')
    if site == 'danbooru':
        page_url = f"https://danbooru.donmai.us/posts/{post_id}" if post_id is not None else ''
        return {
            'status': 'ok' if image_url else 'empty',
            'post_id': post_id,
            'score': score,
            'image_url': image_url,
            'preview_url': p.get('preview_file_url'),
            'page_url': page_url,
            'post_url': page_url,
            'tags': p.get('tag_string'),
        }
    elif site == 'e621':
        page_url = f"https://e621.net/posts/{post_id}" if post_id is not None else ''
        return {
            'status': 'ok' if image_url else 'empty',
            'post_id': post_id,
            'score': score,
            'image_url': image_url,
            'page_url': page_url,
            'post_url': page_url,
            'tags': p.get('tags') if isinstance(p.get('tags'), (dict, list)) else p.get('tags'),
        }
    else:
        page_url = ''
        return {
            'status': 'ok' if image_url else 'empty',
            'post_id': post_id,
            'score': score,
            'image_url': image_url,
            'page_url': page_url,
            'post_url': page_url,
        }


def ensure_tag_list():
    if not TAG_LIST_LOCAL.exists():
        # Fetch the directory listing from GitHub
        html = _fetch_text(TAG_LIST_DIR_URL)
        if not html:
            raise RuntimeError("Failed to fetch tag list directory listing.")
        soup = BeautifulSoup(html, "html.parser")
        # Find all .csv files in the directory
        files = [a.text for a in soup.find_all('a', href=True) if a.text.endswith('.csv')]
        if not files:
            raise RuntimeError("No CSV files found in tag list directory.")
        # Sort files by name (assuming date/version in filename)
        files.sort(reverse=True)
        latest_file = files[0]
        raw_url = RAW_BASE + latest_file
        raw_text = _fetch_text(raw_url)
        if not raw_text:
            raise RuntimeError(f"Failed to fetch tag list file: {raw_url}")
        lines = raw_text.splitlines()
        # Add heading if missing
        if not lines[0].lower().startswith("name,category,count,aliases"):
            lines.insert(0, "name,category,count,aliases")
        TAG_LIST_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        with open(TAG_LIST_LOCAL, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            for row in csv.reader(lines):
                writer.writerow(row)
    else:
        # Ensure heading row exists
        with open(TAG_LIST_LOCAL, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        if lines and not lines[0].lower().startswith("name,category,count,aliases"):
            lines.insert(0, "name,category,count,aliases")
            with open(TAG_LIST_LOCAL, "w", encoding="utf-8", newline='') as f:
                for line in lines:
                    f.write(line + "\n")

# Call on startup
ensure_tag_list()
from flask import Flask, jsonify, send_file, request, abort, stream_with_context
from pathlib import Path
import os
import mimetypes
import subprocess
import sys

import json
from asset_viewer import (
    resolve_requested_root,
    scan_assets,
    scan_duplicate_assets,
    metadata_health_report,
    folder_stats_report,
    repair_png_bubba_metadata,
    build_asset_item,
    generate_thumbnail_bytes,
    resolve_requested_file,
    find_root_for_path,
    AssetRoot,
    make_unique_destination_path,
    move_file_to_trash,
    sanitize_upload_filename,
    ALLOWED_UPLOAD_IMAGE_EXTENSIONS,
    Image,
)
from settings_model import (
    Settings,
    save_settings,
    validate_settings_payload,
)

app = Flask(__name__)

# Basic logging for uploads/deletes and troubleshooting
logging.basicConfig(level=logging.INFO, format='[%(asctime)s] %(levelname)s in %(module)s: %(message)s')
logger = logging.getLogger('bubba.server')

# --- Simple in-memory caches for tag examples and proxied images ---
# Keep things lightweight: TTL-based, mutex-protected, with simple size pruning.
EXAMPLE_CACHE_TTL = 300  # seconds
IMAGE_CACHE_TTL = 3600  # seconds

_MAX_EXAMPLE_CACHE_ITEMS = 200
_MAX_IMAGE_CACHE_ITEMS = 400

# caches store timestamped entries: examples: tag -> (ts, examples_dict)
# images: url -> (ts, bytes, content_type)
_example_cache: dict = {}
_image_cache: dict = {}
_cache_lock = threading.Lock()


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


def _cache_set_examples(tag: str, payload: dict):
    now = time.time()
    with _cache_lock:
        _example_cache[tag] = (now, payload)
        if len(_example_cache) > _MAX_EXAMPLE_CACHE_ITEMS:
            # prune oldest
            items = sorted(_example_cache.items(), key=lambda kv: kv[1][0])
            for k, _ in items[: len(_example_cache) - _MAX_EXAMPLE_CACHE_ITEMS]:
                del _example_cache[k]


def _cache_get_image(url: str):
    now = time.time()
    with _cache_lock:
        entry = _image_cache.get(url)
        if not entry:
            return None, None
        ts, data, ctype = entry
        if now - ts > IMAGE_CACHE_TTL:
            del _image_cache[url]
            return None, None
        return data, ctype


def _cache_set_image(url: str, data: bytes, content_type: str):
    now = time.time()
    with _cache_lock:
        _image_cache[url] = (now, data, content_type)
        if len(_image_cache) > _MAX_IMAGE_CACHE_ITEMS:
            items = sorted(_image_cache.items(), key=lambda kv: kv[1][0])
            for k, _ in items[: len(_image_cache) - _MAX_IMAGE_CACHE_ITEMS]:
                del _image_cache[k]


@app.after_request
def _add_cors_headers(response):
    # Allow local development cross-origin requests
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    return response

@app.route('/bubba/assets/roots', methods=['GET'])
def bubba_assets_roots():
    return api_roots()

@app.route('/bubba/assets/list', methods=['GET'])
def bubba_assets_list():
    return api_assets_list()

# Forwarding wrappers so frontend paths (/bubba/assets/*) work as expected
@app.route('/bubba/assets/file', methods=['GET'])
def bubba_assets_file():
    return api_assets_file()


@app.route('/bubba/assets/thumb', methods=['GET'])
def bubba_assets_thumb():
    return api_assets_thumb()


@app.route('/bubba/assets/details', methods=['GET'])
def bubba_assets_details():
    return api_assets_details()


@app.route('/bubba/assets/upload', methods=['POST'])
def bubba_assets_upload():
    root_key = request.args.get('root')
    try:
        dest_root = resolve_requested_root(root_key, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))

    files = request.files.getlist('files') if hasattr(request, 'files') else []
    uploaded = []
    skipped = []

    for f in files:
        fname = getattr(f, 'filename', None) or 'upload.png'
        filename = sanitize_upload_filename(fname)
        ext = Path(filename).suffix.lower()
        if ext not in ALLOWED_UPLOAD_IMAGE_EXTENSIONS:
            skipped.append({'filename': fname, 'error': f'Invalid extension: {ext}'})
            logger.warning('Upload skipped invalid extension: %s', fname)
            continue

        try:
            content = f.read()
            # Basic image validation using Pillow when available
            if Image is not None:
                try:
                    bio = BytesIO(content)
                    img = Image.open(bio)
                    img.verify()
                except Exception:
                    skipped.append({'filename': fname, 'error': 'Invalid image file'})
                    logger.warning('Upload skipped invalid image: %s', fname)
                    continue

            dest_path = make_unique_destination_path(dest_root, filename)
            with open(dest_path, 'wb') as fh:
                fh.write(content)

            logger.info('Uploaded file: %s -> %s', filename, dest_path)
            uploaded.append(build_asset_item(dest_path, dest_root))
        except Exception as ex:
            logger.exception('Upload failed for %s', fname)
            skipped.append({'filename': fname, 'error': str(ex)})

    return jsonify({'uploaded': uploaded, 'skipped': skipped})


@app.route('/bubba/assets/delete', methods=['POST'])
def bubba_assets_delete():
    payload = request.get_json(silent=True) or {}
    paths = []
    if isinstance(payload.get('paths'), list):
        paths = payload.get('paths')
    elif isinstance(payload.get('path'), str):
        paths = [payload.get('path')]

    if not paths:
        abort(400, 'No paths provided')
    safe_delete = payload.get('safe_delete', True) is not False

    deleted = []
    moved = []
    errors = []
    for p in paths:
        try:
            abs_path = resolve_requested_file(p, ASSET_ROOTS)
            root = find_root_for_path(abs_path, ASSET_ROOTS)
            if not root:
                raise PermissionError('File not in allowed roots')
            if os.path.exists(abs_path):
                if safe_delete:
                    destination = move_file_to_trash(abs_path, root.path)
                    moved.append({'path': p, 'destination': destination})
                else:
                    os.remove(abs_path)
                deleted.append(p)
                logger.info('Deleted file: %s', abs_path)
            else:
                errors.append({'path': p, 'error': 'File not found'})
        except Exception as e:
            logger.exception('Delete failed for %s', p)
            errors.append({'path': p, 'error': str(e)})

    return jsonify({'deleted': deleted, 'moved': moved, 'safe_delete': safe_delete, 'errors': errors})

@app.route('/')
def index():
    frontend_root = Path(__file__).parent.parent / 'frontend'
    frontend_path = frontend_root / 'asset_viewer_vue.html'
    if not frontend_path.exists():
        return '<h1>Frontend not found</h1>', 404
    return send_file(frontend_path)


@app.route('/asset_viewer.css')
def asset_viewer_css():
    css_path = Path(__file__).parent.parent / 'frontend' / 'asset_viewer.css'
    if not css_path.exists():
        return '', 404
    return send_file(css_path, mimetype='text/css')


@app.route('/styles/<path:filename>')
def asset_viewer_style_file(filename):
    styles_root = (Path(__file__).parent.parent / 'frontend' / 'styles').resolve()
    requested = (styles_root / filename).resolve()
    if os.path.commonpath([str(styles_root), str(requested)]) != str(styles_root):
        abort(403, 'Invalid style path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='text/css')


@app.route('/asset_viewer_vue.js')
def asset_viewer_vue_js():
    js_path = Path(__file__).parent.parent / 'frontend' / 'asset_viewer_vue.js'
    if not js_path.exists():
        return '', 404
    return send_file(js_path, mimetype='application/javascript')


@app.route('/vue/<path:filename>')
def asset_viewer_vue_module(filename):
    vue_root = (Path(__file__).parent.parent / 'frontend' / 'vue').resolve()
    requested = (vue_root / filename).resolve()
    if os.path.commonpath([str(vue_root), str(requested)]) != str(vue_root):
        abort(403, 'Invalid module path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='application/javascript')

@app.route('/danbooru_e621_merged.csv')
def serve_tag_csv():
    if not TAG_LIST_LOCAL.exists():
        return '', 404
    return send_file(TAG_LIST_LOCAL, mimetype='text/csv')

@app.route('/api/tags', methods=['GET'])
def api_tags():
    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    try:
        limit = max(1, min(int(request.args.get('limit', 300)), 1000))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        abort(400, 'Invalid pagination parameter')

    normalized_q = re.sub(r'[\s_-]+', '_', q.lower()).strip('_')
    tags = []
    categories = set()
    matched_count = 0
    with open(TAG_LIST_LOCAL, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f)
        for row in reader:
            row_category = str(row.get('category') or '')
            categories.add(row_category)
            if category and row_category != category:
                continue
            if normalized_q:
                search_blob = re.sub(
                    r'[\s_-]+',
                    '_',
                    f"{row.get('name', '')} {row.get('aliases', '')}".lower(),
                )
                if normalized_q not in search_blob:
                    continue
            if matched_count >= offset and len(tags) < limit:
                tags.append(row)
            matched_count += 1
    return jsonify({
        'tags': tags,
        'total': matched_count,
        'limit': limit,
        'offset': offset,
        'categories': sorted([value for value in categories if value]),
    })

@app.route('/bubba/tag_examples')
def bubba_tag_examples():
    tag = request.args.get('tag', '').strip()
    if not tag:
        return jsonify({'examples': {}})
    # Serve from cache when available to avoid repeated external API calls
    cached = _cache_get_examples(tag)
    if cached is not None:
        logger.info('Tag examples cache hit: %s', tag)
        return jsonify({'examples': cached})

    examples = {}
    headers = {
        'User-Agent': 'BubbaAssetViewer/1.0 (contact: none@example.com)',
        'Referer': 'http://127.0.0.1'
    }

    # Danbooru: prefer ordered query by score restricted to the last month, with fallbacks
    # Primary: `tag order:score age:<1month limit:1`
    posts = []
    # Primary: prefer recent high-score images and exclude mp4/gif at the query level
    dan_tags = quote_plus(f"{tag} order:score age:<1month -is:mp4 -is:gif")
    dan_url = f"https://danbooru.donmai.us/posts.json?tags={dan_tags}&limit=1"
    posts = _fetch_json_list(dan_url, headers=_api_headers('danbooru', headers), timeout=10)

    # Accept the primary result only if it isn't a disallowed media type
    if isinstance(posts, list) and posts:
        p = posts[0]
        image_url = _danbooru_build_image_url_from_post(p)
        if not _has_disallowed_ext_from_url(image_url):
            sc_val = _danbooru_get_score(p)
            examples['danbooru'] = _build_example('danbooru', p, sc_val, image_url)
        else:
            posts = []

    if not examples.get('danbooru'):
        # Fallback 1: fetch a small batch constrained to the last month and pick the highest score
        try:
            dan_tags_age = quote_plus(f"{tag} age:<1month")
            dan_url = f"https://danbooru.donmai.us/posts.json?tags={dan_tags_age}&limit={FALLBACK_FETCH_LIMIT}"
            posts = _fetch_json_list(dan_url, headers=_api_headers('danbooru', headers), timeout=12)

            best, best_score = _pick_best_post(posts, _danbooru_build_image_url_from_post, _danbooru_get_score)
            if best:
                examples['danbooru'] = _build_example('danbooru', best, best_score, _danbooru_build_image_url_from_post(best))
            else:
                # Fallback 2: fetch an unfiltered batch and pick the highest-score post
                try:
                    dan_tags_simple = quote_plus(tag)
                    dan_url2 = f"https://danbooru.donmai.us/posts.json?tags={dan_tags_simple}&limit={FALLBACK_FETCH_LIMIT}"
                    posts = _fetch_json_list(dan_url2, headers=_api_headers('danbooru', headers), timeout=12)

                    best, best_score = _pick_best_post(posts, _danbooru_build_image_url_from_post, _danbooru_get_score)
                    if best:
                        examples['danbooru'] = _build_example('danbooru', best, best_score, _danbooru_build_image_url_from_post(best))
                    else:
                        examples['danbooru'] = {'status': 'empty', 'error': 'No posts found'}
                except Exception as e3:
                    examples['danbooru'] = {'status': 'error', 'error': str(e3)}
        except Exception as e2:
            examples['danbooru'] = {'status': 'error', 'error': str(e2)}

    # e621: prefer recent high-score images; exclude webm/mp4/gif and fall back by selecting highest score
    posts = []
    e_tags = quote_plus(f"{tag} order:score -type:webm -type:mp4 -type:gif")
    e_url = f"https://e621.net/posts.json?tags={e_tags}&limit=1"
    posts = _fetch_json_list(e_url, headers=_api_headers('e621', headers), timeout=10, list_key='posts')

    if isinstance(posts, list) and posts:
        p = posts[0]
        image_url = _e621_build_image_url_from_post(p)
        if not _has_disallowed_ext_from_url(image_url):
            sc_val = _e621_get_score(p)
            examples['e621'] = {
                'status': 'ok',
                'post_id': p.get('id'),
                'score': sc_val,
                'image_url': image_url,
                'page_url': f"https://e621.net/posts/{p.get('id')}",
                'post_url': f"https://e621.net/posts/{p.get('id')}",
                'tags': p.get('tags') if isinstance(p.get('tags'), (dict, list)) else p.get('tags'),
            }
        else:
            posts = []

    if not examples.get('e621'):
        # Fallback 1: recent batch (last month) and choose the highest-scoring non-disallowed post
        try:
            e_tags_age = quote_plus(f"{tag} date:month -type:webm -type:mp4 -type:gif")
            e_url2 = f"https://e621.net/posts.json?tags={e_tags_age}&limit={FALLBACK_FETCH_LIMIT}"
            posts = _fetch_json_list(e_url2, headers=_api_headers('e621', headers), timeout=12, list_key='posts')

            best, best_score = _pick_best_post(posts, _e621_build_image_url_from_post, _e621_get_score)
            if best:
                examples['e621'] = _build_example('e621', best, best_score, _e621_build_image_url_from_post(best))
            else:
                # Fallback 2: unfiltered batch, pick highest non-disallowed
                try:
                    e_tags_simple = quote_plus(tag)
                    e_url3 = f"https://e621.net/posts.json?tags={e_tags_simple}&limit={FALLBACK_FETCH_LIMIT}"
                    posts = _fetch_json_list(e_url3, headers=_api_headers('e621', headers), timeout=12, list_key='posts')

                    best, best_score = _pick_best_post(posts, _e621_build_image_url_from_post, _e621_get_score)
                    if best:
                        examples['e621'] = _build_example('e621', best, best_score, _e621_build_image_url_from_post(best))
                    else:
                        examples['e621'] = {'status': 'empty', 'error': 'No posts found'}
                except Exception as e3:
                    examples['e621'] = {'status': 'error', 'error': str(e3)}
        except Exception as e2:
            examples['e621'] = {'status': 'error', 'error': str(e2)}

    # Store in cache for subsequent requests
    try:
        _cache_set_examples(tag, examples)
    except Exception:
        pass
    return jsonify({'examples': examples})

@app.route('/bubba/tag_example_image')
def bubba_tag_example_image():
    url = request.args.get('url', '').strip()
    if not url:
        return '', 404
    # Check in-memory image cache first
    cached_data, cached_ct = _cache_get_image(url)
    if cached_data is not None:
        return Response(cached_data, content_type=cached_ct)
    try:
        # Provide sensible headers to avoid CDN hotlink/forbidden responses
        from urllib.parse import urlparse
        parsed = urlparse(url)
        host = (parsed.netloc or '').lower()
        headers = {
            'User-Agent': 'BubbaAssetViewer/1.0 (contact: none@example.com)'
        }
        if host.endswith('donmai.us'):
            headers['Referer'] = 'https://danbooru.donmai.us'
        elif host.endswith('e621.net') or host.endswith('static1.e621.net'):
            headers['Referer'] = 'https://e621.net'

        resp = requests.get(url, headers=headers, stream=True, timeout=10)
        resp.raise_for_status()
        content_type = resp.headers.get('Content-Type', 'image/jpeg')
        body = resp.content
        # Cache proxied image to save repeated downloads
        try:
            _cache_set_image(url, body, content_type)
        except Exception:
            pass
        return Response(body, content_type=content_type)
    except Exception as e:
        return f'Failed to fetch image: {e}', 404

SETTINGS_FILE = Path(__file__).parent.parent / 'settings.json'


def _asset_roots_from_settings(settings: Settings):
    return [
        AssetRoot(key=os.path.basename(path), label=os.path.basename(path), path=path)
        for path in settings.general.asset_roots
    ]


# Load asset roots from settings.json
def load_asset_roots():
    settings = Settings()
    return _asset_roots_from_settings(settings)

ASSET_ROOTS = load_asset_roots()


@app.route('/api/settings', methods=['GET'])
def api_settings():
    settings = Settings()
    return jsonify({
        'settings': settings.model_dump(mode='json'),
        'schema': Settings.model_json_schema(),
    })


@app.route('/api/settings', methods=['PUT'])
def api_update_settings():
    global ASSET_ROOTS
    payload = request.get_json(silent=True) or {}
    try:
        settings = validate_settings_payload(payload)
    except Exception as e:
        abort(400, str(e))
    save_settings(SETTINGS_FILE, settings)
    ASSET_ROOTS = _asset_roots_from_settings(settings)
    return jsonify({
        'settings': settings.model_dump(mode='json'),
        'schema': Settings.model_json_schema(),
        'roots': [root.__dict__ for root in ASSET_ROOTS],
    })

@app.route('/api/roots', methods=['GET'])
def api_roots():
    return jsonify({
        'roots': [root.__dict__ for root in ASSET_ROOTS]
    })

@app.route('/api/assets/list', methods=['GET'])
def api_assets_list():
    root_key = request.args.get('root')
    q = request.args.get('q', '')
    ext = request.args.get('ext', '')
    try:
        limit = int(request.args.get('limit', 100))
        offset = int(request.args.get('offset', 0))
    except ValueError:
        abort(400, 'Invalid pagination parameter')
    include_metadata = request.args.get('include_metadata', 'false').lower() == 'true'
    sort_by = request.args.get('sort_by', 'modified')
    sort_dir = request.args.get('sort_dir', 'desc')
    min_size_bytes = request.args.get('min_size_bytes')
    max_size_bytes = request.args.get('max_size_bytes')
    modified_after_ts = request.args.get('modified_after_ts')
    metadata_mode = request.args.get('metadata_mode', 'all')
    metadata_badges = [
        item.strip()
        for item in request.args.get('metadata_badges', '').split(',')
        if item.strip()
    ]
    try:
        min_size_filter = int(min_size_bytes) if min_size_bytes else None
        max_size_filter = int(max_size_bytes) if max_size_bytes else None
        modified_after_filter = float(modified_after_ts) if modified_after_ts else None
    except ValueError:
        abort(400, 'Invalid numeric filter')

    try:
        root_path = resolve_requested_root(root_key, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))

    assets = scan_assets(
        root=root_path,
        query=q,
        extensions=[ext] if ext else None,
        limit=limit,
        include_metadata=include_metadata,
        offset=offset,
        sort_by=sort_by,
        sort_dir=sort_dir,
        min_size_bytes=min_size_filter,
        max_size_bytes=max_size_filter,
        modified_after_ts=modified_after_filter,
        metadata_mode=metadata_mode,
        metadata_badge_filter=metadata_badges,
    )
    return jsonify({'assets': assets, 'root': root_key})


@app.route('/api/assets/metadata/health', methods=['GET'])
def api_assets_metadata_health():
    root_key = request.args.get('root')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    cache_only = request.args.get('cache_only', 'false').lower() == 'true'
    try:
        limit = int(request.args.get('limit', 10000))
    except ValueError:
        abort(400, 'Invalid metadata health parameter')
    try:
        root_path = resolve_requested_root(root_key, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))
    report, cached = metadata_health_report(root_path, limit=limit, refresh=refresh, cache_only=cache_only)
    return jsonify({'root': root_key, 'stats': report.model_dump(mode='json') if report else None, 'cached': cached})


@app.route('/api/assets/stats', methods=['GET'])
def api_assets_stats():
    root_key = request.args.get('root')
    refresh = request.args.get('refresh', 'false').lower() == 'true'
    cache_only = request.args.get('cache_only', 'false').lower() == 'true'
    try:
        root_path = resolve_requested_root(root_key, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))
    report, cached = folder_stats_report(root_path, refresh=refresh, cache_only=cache_only)
    return jsonify({'root': root_key, 'stats': report.model_dump(mode='json') if report else None, 'cached': cached})


@app.route('/api/assets/duplicates', methods=['GET'])
def api_assets_duplicates():
    root_key = request.args.get('root')
    include_near = request.args.get('include_near', 'false').lower() == 'true'
    try:
        near_threshold = int(request.args.get('near_threshold', 6))
        limit = int(request.args.get('limit', 5000))
    except ValueError:
        abort(400, 'Invalid duplicate scan parameter')

    try:
        root_path = resolve_requested_root(root_key, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))

    payload = scan_duplicate_assets(
        root=root_path,
        include_near=include_near,
        near_threshold=near_threshold,
        limit=limit,
    )
    return jsonify({'root': root_key, **payload})


@app.route('/api/assets/duplicates/stream', methods=['GET'])
def api_assets_duplicates_stream():
    root_key = request.args.get('root')
    include_near = request.args.get('include_near', 'false').lower() == 'true'
    try:
        near_threshold = int(request.args.get('near_threshold', 6))
        limit = int(request.args.get('limit', 5000))
    except ValueError:
        abort(400, 'Invalid duplicate scan parameter')

    try:
        root_path = resolve_requested_root(root_key, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))

    events: queue.Queue[dict[str, Any]] = queue.Queue()

    def progress_callback(progress: dict[str, Any]) -> None:
        events.put({'type': 'progress', 'progress': progress})

    def worker() -> None:
        try:
            payload = scan_duplicate_assets(
                root=root_path,
                include_near=include_near,
                near_threshold=near_threshold,
                limit=limit,
                progress_callback=progress_callback,
            )
            events.put({'type': 'result', 'root': root_key, **payload})
        except Exception as exc:
            logger.exception('Duplicate scan failed')
            events.put({'type': 'error', 'error': str(exc)})
        finally:
            events.put({'type': 'done'})

    threading.Thread(target=worker, daemon=True).start()

    @stream_with_context
    def generate():
        while True:
            event = events.get()
            yield json.dumps(event) + "\n"
            if event.get('type') == 'done':
                break

    return Response(generate(), mimetype='application/x-ndjson')

@app.route('/api/assets/file', methods=['GET'])
def api_assets_file():
    path = request.args.get('path')
    try:
        abs_path = resolve_requested_file(path, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))
    mime, _ = mimetypes.guess_type(abs_path)
    return send_file(abs_path, mimetype=mime or 'application/octet-stream')

@app.route('/api/assets/thumb', methods=['GET'])
def api_assets_thumb():
    path = request.args.get('path')
    size = int(request.args.get('size', 256))
    try:
        abs_path = resolve_requested_file(path, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))
    thumb = generate_thumbnail_bytes(abs_path, max_size=size)
    if not thumb:
        abort(404, 'Could not generate thumbnail')
    from io import BytesIO
    return send_file(
        BytesIO(thumb),
        mimetype='image/png',
        as_attachment=False,
        download_name=Path(abs_path).name + '_thumb.png'
    )

@app.route('/api/assets/details', methods=['GET'])
def api_assets_details():
    path = request.args.get('path')
    try:
        abs_path = resolve_requested_file(path, ASSET_ROOTS)
        root = find_root_for_path(abs_path, ASSET_ROOTS)
        if not root:
            abort(400, 'File not in allowed roots')
        item = build_asset_item(abs_path, root.path, include_metadata=True)
    except Exception as e:
        abort(400, str(e))
    return jsonify({'asset': item})


@app.route('/api/assets/metadata/repair', methods=['POST'])
def api_assets_repair_metadata():
    payload = request.get_json(silent=True) or {}
    path = payload.get('path')
    overwrite = payload.get('overwrite', False) is True
    try:
        abs_path = resolve_requested_file(path, ASSET_ROOTS)
        root = find_root_for_path(abs_path, ASSET_ROOTS)
        if not root:
            raise PermissionError('File not in allowed roots')
        result = repair_png_bubba_metadata(abs_path, overwrite=overwrite)
        item = build_asset_item(abs_path, root.path, include_metadata=True)
    except Exception as e:
        abort(400, str(e))
    return jsonify({'result': result, 'asset': item})


@app.route('/api/assets/open-folder', methods=['POST'])
def api_assets_open_folder():
    payload = request.get_json(silent=True) or {}
    path = payload.get('path')
    try:
        abs_path = resolve_requested_file(path, ASSET_ROOTS)
    except Exception as e:
        abort(400, str(e))

    folder = os.path.dirname(abs_path)
    try:
        if os.name == 'nt':
            os.startfile(folder)  # type: ignore[attr-defined]
        elif sys.platform == 'darwin':
            subprocess.Popen(['open', folder])
        else:
            subprocess.Popen(['xdg-open', folder])
    except Exception as e:
        logger.exception('Open folder failed for %s', folder)
        abort(500, str(e))
    return jsonify({'opened': folder})

if __name__ == '__main__':
    logger.info('Bubba Asset Viewer server started on http://localhost:5001')
    app.run(debug=True, port=5001)
    
