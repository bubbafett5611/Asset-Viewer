import requests
from flask import Response

from pathlib import Path
import csv
import re
from bs4 import BeautifulSoup
from urllib.parse import quote_plus, urlparse
import logging
import threading
import time
from typing import Optional, Dict, Any, Tuple, List

TAG_LIST_DIR_URL = "https://github.com/DraconicDragon/dbr-e621-lists-archive/tree/main/tag-lists/danbooru_e621_merged"
RAW_BASE = "https://raw.githubusercontent.com/DraconicDragon/dbr-e621-lists-archive/main/tag-lists/danbooru_e621_merged/"
TAG_LIST_LOCAL = Path(__file__).parent.parent / "frontend" / "danbooru_e621_merged.csv"

FALLBACK_FETCH_LIMIT = 50

DISALLOWED_EXTS = {'.webm', '.mp4', '.gif'}
TAG_LIST_HEADER = "name,category,count,aliases"

_tag_list_lock = threading.Lock()
_tag_list_ready = False


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
    global _tag_list_ready
    with _tag_list_lock:
        if _tag_list_ready:
            return
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
        if not lines[0].lower().startswith(TAG_LIST_HEADER):
            lines.insert(0, TAG_LIST_HEADER)
        TAG_LIST_LOCAL.parent.mkdir(parents=True, exist_ok=True)
        with open(TAG_LIST_LOCAL, "w", encoding="utf-8", newline='') as f:
            writer = csv.writer(f)
            for row in csv.reader(lines):
                writer.writerow(row)
    else:
        # Ensure heading row exists
        with open(TAG_LIST_LOCAL, "r", encoding="utf-8") as f:
            lines = f.read().splitlines()
        if lines and not lines[0].lower().startswith(TAG_LIST_HEADER):
            lines.insert(0, TAG_LIST_HEADER)
            with open(TAG_LIST_LOCAL, "w", encoding="utf-8", newline='') as f:
                for line in lines:
                    f.write(line + "\n")
    _tag_list_ready = True


def _ensure_tag_list_available():
    try:
        ensure_tag_list()
        return None
    except Exception as exc:
        logger.exception('Failed to ensure local tag list is available')
        return jsonify({'error': f'Failed to prepare tag list: {exc}'}), 503

from flask import Flask, jsonify, send_file, request, abort
from pathlib import Path
import os
from services import asset_api
import asset_viewer as _asset_viewer
from settings_model import (
    Settings,
    save_settings,
    validate_settings_payload,
)

# Compatibility exports for service-context lookups and tests that monkeypatch server.* symbols.
resolve_requested_root = _asset_viewer.resolve_requested_root
scan_assets = _asset_viewer.scan_assets
scan_duplicate_assets = _asset_viewer.scan_duplicate_assets
metadata_health_report = _asset_viewer.metadata_health_report
folder_stats_report = _asset_viewer.folder_stats_report
repair_png_bubba_metadata = _asset_viewer.repair_png_bubba_metadata
build_asset_item = _asset_viewer.build_asset_item
generate_thumbnail_bytes = _asset_viewer.generate_thumbnail_bytes
resolve_requested_file = _asset_viewer.resolve_requested_file
find_root_for_path = _asset_viewer.find_root_for_path
AssetRoot = _asset_viewer.AssetRoot
make_unique_destination_path = _asset_viewer.make_unique_destination_path
move_file_to_trash = _asset_viewer.move_file_to_trash
sanitize_upload_filename = _asset_viewer.sanitize_upload_filename
ALLOWED_UPLOAD_IMAGE_EXTENSIONS = _asset_viewer.ALLOWED_UPLOAD_IMAGE_EXTENSIONS
Image = _asset_viewer.Image

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


def _add_cors_headers(response):
    # Allow local development cross-origin requests
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Methods'] = 'GET,POST,OPTIONS'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type,Authorization'
    return response

def bubba_assets_roots():
    return api_roots()

def bubba_assets_list():
    return api_assets_list()

# Forwarding wrappers so frontend paths (/bubba/assets/*) work as expected
def bubba_assets_file():
    return api_assets_file()


def bubba_assets_thumb():
    return api_assets_thumb()


def bubba_assets_details():
    return api_assets_details()


def bubba_assets_upload():
    return asset_api.bubba_assets_upload_handler()


def bubba_assets_delete():
    return asset_api.bubba_assets_delete_handler()

def index():
    frontend_root = Path(__file__).parent.parent / 'frontend'
    frontend_path = frontend_root / 'asset_viewer_vue.html'
    if not frontend_path.exists():
        return '<h1>Frontend not found</h1>', 404
    return send_file(frontend_path)


def asset_viewer_css():
    css_path = Path(__file__).parent.parent / 'frontend' / 'asset_viewer.css'
    if not css_path.exists():
        return '', 404
    return send_file(css_path, mimetype='text/css')


def asset_viewer_style_file(filename):
    styles_root = (Path(__file__).parent.parent / 'frontend' / 'styles').resolve()
    requested = (styles_root / filename).resolve()
    if os.path.commonpath([str(styles_root), str(requested)]) != str(styles_root):
        abort(403, 'Invalid style path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='text/css')


def asset_viewer_vue_js():
    js_path = Path(__file__).parent.parent / 'frontend' / 'asset_viewer_vue.js'
    if not js_path.exists():
        return '', 404
    return send_file(js_path, mimetype='application/javascript')


def asset_viewer_vue_module(filename):
    vue_root = (Path(__file__).parent.parent / 'frontend' / 'vue').resolve()
    requested = (vue_root / filename).resolve()
    if os.path.commonpath([str(vue_root), str(requested)]) != str(vue_root):
        abort(403, 'Invalid module path')
    if not requested.exists() or not requested.is_file():
        return '', 404
    return send_file(requested, mimetype='application/javascript')

def serve_tag_csv():
    failure = _ensure_tag_list_available()
    if failure is not None:
        return failure
    return send_file(TAG_LIST_LOCAL, mimetype='text/csv')

def api_tags():
    failure = _ensure_tag_list_available()
    if failure is not None:
        return failure

    q = request.args.get('q', '').strip()
    category = request.args.get('category', '').strip()
    try:
        limit = max(1, min(int(request.args.get('limit', 300)), 1000))
        offset = max(0, int(request.args.get('offset', 0)))
    except ValueError:
        abort(400, 'Invalid pagination parameter')

    normalized_q = re.sub(r'[\s_-]+', '_', q.lower()).strip('_')
    tags: list[dict[str, Any]] = []
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
_asset_roots_lock = threading.Lock()


def _get_asset_roots_snapshot() -> list[AssetRoot]:
    with _asset_roots_lock:
        return list(ASSET_ROOTS)


def _set_asset_roots(new_roots: list[AssetRoot]) -> None:
    global ASSET_ROOTS
    with _asset_roots_lock:
        ASSET_ROOTS = list(new_roots)


def api_settings():
    settings = Settings()
    return jsonify({
        'settings': settings.model_dump(mode='json'),
        'schema': Settings.model_json_schema(),
    })


def api_update_settings():
    payload = request.get_json(silent=True) or {}
    try:
        settings = validate_settings_payload(payload)
    except Exception as e:
        abort(400, str(e))
    save_settings(SETTINGS_FILE, settings)
    updated_roots = _asset_roots_from_settings(settings)
    _set_asset_roots(updated_roots)
    return jsonify({
        'settings': settings.model_dump(mode='json'),
        'schema': Settings.model_json_schema(),
        'roots': [root.__dict__ for root in updated_roots],
    })

def api_roots():
    return asset_api.api_roots_handler()

def api_assets_list():
    return asset_api.api_assets_list_handler()


def api_assets_metadata_health():
    return asset_api.api_assets_metadata_health_handler()


def api_assets_stats():
    return asset_api.api_assets_stats_handler()


def api_assets_duplicates():
    return asset_api.api_assets_duplicates_handler()


def api_assets_duplicates_stream():
    return asset_api.api_assets_duplicates_stream_handler()

def api_assets_file():
    return asset_api.api_assets_file_handler()

def api_assets_thumb():
    return asset_api.api_assets_thumb_handler()

def api_assets_details():
    return asset_api.api_assets_details_handler()


def api_assets_repair_metadata():
    return asset_api.api_assets_repair_metadata_handler()


def api_assets_open_folder():
    return asset_api.api_assets_open_folder_handler()

def create_app() -> Flask:
    app = Flask(__name__)
    app.after_request(_add_cors_headers)

    from blueprints.assets import assets_bp
    from blueprints.settings import settings_bp
    from blueprints.tags import tags_bp
    from blueprints.ui import ui_bp

    app.register_blueprint(ui_bp)
    app.register_blueprint(tags_bp)
    app.register_blueprint(settings_bp)
    app.register_blueprint(assets_bp)
    return app


app = create_app()


if __name__ == '__main__':
    logger.info('Bubba Asset Viewer server started on http://localhost:5001')
    app.run(debug=True, port=5001)
    
