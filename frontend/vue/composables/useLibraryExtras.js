import { markRaw, onBeforeUnmount, provide, reactive, ref, watch } from '/vendor/vue.esm-browser.prod.js';
import { API, buildQuery } from '/vue/api.js';
import { showToast } from '/vue/components/ToastHost.js';
import { NsfwOverlay } from '/vue/components/NsfwOverlay.js';

export const LIBRARY_KEY = 'bubba-library';
const LIVE_POLL_MS = 5000;

async function readJson(response, fallbackMessage) {
  let payload = {};
  try {
    payload = await response.json();
  } catch {
    // non-JSON error page
  }
  if (!response.ok) {
    throw new Error(payload.error || payload.description || `${fallbackMessage} (${response.status})`);
  }
  return payload;
}

/** Quote a search value when it contains spaces so the smart-search parser keeps it whole. */
export function searchToken(field, value, { exact = false } = {}) {
  const text = String(value || '').replace(/"/g, '');
  const operator = exact ? ':=' : ':';
  return `${field}${operator}${/\s/.test(text) ? `"${text}"` : text}`;
}

/**
 * Library-level features shared across views: facets (search suggestions, insights, timeline),
 * per-root collections, the live "N new" feed, Find similar, and ComfyUI re-queue.
 * Exposed to components with provide/inject under LIBRARY_KEY.
 */
export function useLibraryExtras({
  filters,
  activeTab,
  assets,
  listServerTime,
  refreshAssets,
  fetchFolders,
  assetListRef,
  details = null,
  selectedAsset = null,
  selectedPath = null,
  selectedPaths = null,
  stepSelectedAsset = null,
  confirmDelete = null,
  blurThumbnails = null
}) {
  const facets = ref(null);
  const collections = ref([]);
  const liveNewCount = ref(0);
  const comfyBusy = ref(false);
  let facetsController = null;
  let pollTimer = null;
  let polling = false;

  async function fetchFacets() {
    if (!filters.root) {
      facets.value = null;
      return;
    }
    facetsController?.abort();
    facetsController = new AbortController();
    const requestedRoot = filters.root;
    try {
      const response = await fetch(buildQuery(API.facets, { root: requestedRoot }), {
        signal: facetsController.signal
      });
      const payload = await readJson(response, 'Failed to load library insights');
      if (filters.root === requestedRoot) facets.value = payload.facets || null;
    } catch (error) {
      if (error.name !== 'AbortError') console.error(error);
    }
  }

  async function fetchCollections() {
    if (!filters.root) {
      collections.value = [];
      return;
    }
    try {
      const payload = await readJson(
        await fetch(buildQuery(API.collections, { root: filters.root })),
        'Failed to load collections'
      );
      collections.value = Array.isArray(payload.collections) ? payload.collections : [];
      if (filters.collection && !collections.value.some((item) => String(item.id) === String(filters.collection))) {
        filters.collection = '';
      }
    } catch (error) {
      console.error(error);
    }
  }

  async function collectionRequest(url, options, successMessage) {
    try {
      const payload = await readJson(
        await fetch(url, { headers: { 'Content-Type': 'application/json' }, ...options }),
        'Collection update failed'
      );
      if (Array.isArray(payload.collections)) collections.value = payload.collections;
      if (successMessage) showToast({ message: successMessage, tone: 'success' });
      return payload;
    } catch (error) {
      showToast({ message: error.message, tone: 'error' });
      return null;
    }
  }

  async function createCollection(paths = []) {
    const name = window.prompt(paths.length ? `New collection with ${paths.length} selected:` : 'New collection name:');
    if (!name || !name.trim()) return null;
    const payload = await collectionRequest(
      API.collections,
      { method: 'POST', body: JSON.stringify({ root: filters.root, name, paths }) },
      paths.length ? `Added ${paths.length} to “${name.trim()}”.` : `Created “${name.trim()}”.`
    );
    return payload?.collection || null;
  }

  async function addToCollection(collection, paths) {
    if (!paths.length) return;
    await collectionRequest(
      `${API.collections}/${collection.id}/items`,
      { method: 'POST', body: JSON.stringify({ root: filters.root, paths, action: 'add' }) },
      `Added ${paths.length} to “${collection.name}”.`
    );
  }

  async function removeFromCollection(collection, paths) {
    if (!paths.length) return;
    const payload = await collectionRequest(
      `${API.collections}/${collection.id}/items`,
      { method: 'POST', body: JSON.stringify({ root: filters.root, paths, action: 'remove' }) },
      `Removed ${paths.length} from “${collection.name}”.`
    );
    if (payload && String(filters.collection) === String(collection.id)) {
      await refreshAssets({ keepSelection: false });
    }
  }

  async function renameCollection(collection) {
    const name = window.prompt('Rename collection:', collection.name);
    if (!name || !name.trim() || name.trim() === collection.name) return;
    await collectionRequest(`${API.collections}/${collection.id}`, {
      method: 'PATCH',
      body: JSON.stringify({ root: filters.root, name })
    });
  }

  async function deleteCollection(collection) {
    if (!window.confirm(`Delete the collection “${collection.name}”? The media files are not deleted.`)) return;
    const payload = await collectionRequest(
      buildQuery(`${API.collections}/${collection.id}`, { root: filters.root }),
      { method: 'DELETE' },
      `Deleted collection “${collection.name}”.`
    );
    if (payload && String(filters.collection) === String(collection.id)) filters.collection = '';
  }

  function collectionById(id) {
    return collections.value.find((item) => String(item.id) === String(id)) || null;
  }

  // ---- Live feed -------------------------------------------------------
  async function pollForNewMedia() {
    if (polling || document.hidden || activeTab.value !== 'assets' || !filters.root || filters.similarTo) return;
    if (!listServerTime.value) return;
    polling = true;
    try {
      const response = await fetch(
        buildQuery(API.changes, {
          root: filters.root,
          folder: filters.folder,
          q: filters.q,
          ext: filters.ext,
          metadata_badges: filters.metadataBadge,
          favorites: filters.favorites,
          collection: filters.collection,
          since: listServerTime.value
        })
      );
      const payload = await readJson(response, 'Live update failed');
      liveNewCount.value = Number(payload.new_count) || 0;
    } catch (error) {
      console.debug(error);
    } finally {
      polling = false;
    }
  }

  async function applyLiveUpdates() {
    liveNewCount.value = 0;
    await refreshAssets({ keepSelection: true });
    assetListRef?.value?.scrollTo?.({ top: 0, behavior: 'smooth' });
    fetchFolders?.();
    fetchFacets();
  }

  watch(listServerTime, () => {
    liveNewCount.value = 0;
  });
  pollTimer = setInterval(pollForNewMedia, LIVE_POLL_MS);
  const onVisible = () => {
    if (!document.hidden) pollForNewMedia();
  };
  document.addEventListener('visibilitychange', onVisible);
  onBeforeUnmount(() => {
    clearInterval(pollTimer);
    document.removeEventListener('visibilitychange', onVisible);
  });

  // ---- Search / similar / ComfyUI --------------------------------------
  function applySearch(query, { replaceField = null } = {}) {
    let next = String(query || '').trim();
    if (replaceField) {
      // Replace an existing token for the same field (e.g. a previous on:date) instead of stacking.
      const pattern = new RegExp(`(^|\\s)-?${replaceField}:("[^"]*"|\\S+)`, 'g');
      const rest = String(filters.q || '')
        .replace(pattern, ' ')
        .trim();
      next = [rest, next].filter(Boolean).join(' ');
    }
    filters.similarTo = '';
    filters.q = next;
    activeTab.value = 'assets';
  }

  function findSimilar(asset) {
    if (!asset?.path) return;
    filters.similarTo = asset.path;
    filters.similarToName = asset.name || '';
    activeTab.value = 'assets';
  }

  async function queueInComfy(asset) {
    if (!asset?.path || comfyBusy.value) return;
    comfyBusy.value = true;
    try {
      const payload = await readJson(
        await fetch(API.comfyQueue, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ path: asset.path })
        }),
        'ComfyUI queue failed'
      );
      showToast({
        message: `Queued “${asset.name}” in ComfyUI${payload.number !== undefined && payload.number !== null ? ` (#${payload.number})` : ''}.`,
        tone: 'success',
        action: payload.comfyui_url
          ? { label: 'Open ComfyUI', run: () => window.open(payload.comfyui_url, '_blank', 'noopener,noreferrer') }
          : null
      });
    } catch (error) {
      showToast({ message: error.message, tone: 'error', timeout: 9000 });
    } finally {
      comfyBusy.value = false;
    }
  }

  // ---- Cull mode (keep / reject) ----------------------------------------
  const RATING_FILTER_PATTERN = /(^|\s)-?is:(keep|kept|keeper|reject|rejected|unrated)(?=\s|$)/gi;

  function applyRatingLocally(paths, rating) {
    const targets = new Set(paths);
    for (const asset of assets.value) {
      if (targets.has(asset.path)) asset.rating = rating || undefined;
    }
    if (details?.value && targets.has(details.value.path))
      details.value = { ...details.value, rating: rating || undefined };
    if (selectedAsset?.value && targets.has(selectedAsset.value.path)) {
      selectedAsset.value = { ...selectedAsset.value, rating: rating || undefined };
    }
  }

  function ratingOf(path) {
    return assets.value.find((asset) => asset.path === path)?.rating || '';
  }

  /** Rate paths keep/reject (null clears). Optimistic; rolls back and toasts on failure. */
  async function rate(paths, rating) {
    const targets = (paths || []).filter(Boolean);
    if (!targets.length) return false;
    const previous = new Map(targets.map((path) => [path, ratingOf(path)]));
    applyRatingLocally(targets, rating);
    try {
      await readJson(
        await fetch(API.rating, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ paths: targets, rating: rating || null })
        }),
        'Rating update failed'
      );
      return true;
    } catch (error) {
      for (const [path, value] of previous) applyRatingLocally([path], value || null);
      showToast({ message: error.message, tone: 'error' });
      return false;
    }
  }

  /** Keys 1/2 in the grid: rate the selection; a single image advances to the next one. */
  async function rateSelection(rating) {
    const multi = selectedPaths?.value?.size > 1;
    const targets = multi ? Array.from(selectedPaths.value) : [selectedPath?.value].filter(Boolean);
    if (!targets.length) return;
    // Pressing the key that matches the current rating clears it.
    const next = !multi && ratingOf(targets[0]) === rating ? null : rating;
    const ok = await rate(targets, next);
    if (!ok) return;
    if (multi) {
      showToast({ message: `Marked ${targets.length} as ${next || 'unrated'}.`, tone: 'success' });
    } else if (next) {
      stepSelectedAsset?.(1);
    }
  }

  function setRatingFilter(value) {
    const rest = String(filters.q || '')
      .replace(RATING_FILTER_PATTERN, ' ')
      .replace(/\s+/g, ' ')
      .trim();
    filters.similarTo = '';
    filters.q = [rest, value ? `is:${value}` : ''].filter(Boolean).join(' ');
    activeTab.value = 'assets';
  }

  const cullBusy = ref(false);
  async function trashAllRejects() {
    if (!filters.root || cullBusy.value || !confirmDelete) return;
    cullBusy.value = true;
    try {
      const payload = await readJson(
        await fetch(buildQuery(API.list, { root: filters.root, folder: filters.folder, q: 'is:reject', limit: 3000 })),
        'Could not list rejects'
      );
      const paths = (payload.assets || []).map((asset) => asset.path);
      const where = filters.folder ? `“${filters.folder}”` : 'this library';
      if (!paths.length) {
        showToast({ message: `No rejected media in ${where}.`, tone: 'info' });
        return;
      }
      const noun = paths.length === 1 ? 'reject' : 'rejects';
      if (!window.confirm(`Move ${paths.length} ${noun} in ${where} to the trash? You can undo this.`)) return;
      await confirmDelete({ paths, safeDeleteOverride: true });
    } catch (error) {
      showToast({ message: error.message, tone: 'error' });
    } finally {
      cullBusy.value = false;
    }
  }

  // ---- NSFW detection and blur ------------------------------------------
  const nsfw = reactive({
    settings: {
      preview: false,
      nsfw_blur: true,
      nsfw_blur_style: 'regions',
      nsfw_preset: 'strict',
      nsfw_sensitivity: 33,
      nsfw_see_through: false
    },
    presets: {},
    models: null,
    pending: 0,
    task: null,
    saving: false
  });
  let nsfwPollTimer = null;

  async function fetchNsfwStatus() {
    if (!filters.root) return;
    try {
      const payload = await readJson(
        await fetch(buildQuery(API.nsfwStatus, { root: filters.root })),
        'Could not load NSFW status'
      );
      Object.assign(nsfw.settings, payload.settings || {});
      nsfw.presets = payload.presets || {};
      nsfw.models = payload.models || null;
      nsfw.pending = Number(payload.pending) || 0;
      const wasRunning = nsfw.task?.status === 'running';
      nsfw.task = payload.task || null;
      if (nsfw.task?.status === 'running') {
        clearTimeout(nsfwPollTimer);
        nsfwPollTimer = setTimeout(fetchNsfwStatus, 1500);
      } else if (wasRunning) {
        await refreshAssets({ keepSelection: true });
        if (nsfw.task?.status === 'completed') {
          showToast({ message: `NSFW scan finished: ${nsfw.task.done} images analysed.`, tone: 'success' });
        }
      }
    } catch (error) {
      console.debug(error);
    }
  }

  async function updateNsfwSettings(patch) {
    nsfw.saving = true;
    try {
      const payload = await readJson(
        await fetch(API.nsfwSettings, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(patch)
        }),
        'Could not save blur settings'
      );
      Object.assign(nsfw.settings, payload.settings || {});
      if (blurThumbnails && 'preview' in patch) blurThumbnails.value = Boolean(nsfw.settings.preview);
      const reclassify = ['nsfw_preset', 'nsfw_sensitivity', 'nsfw_see_through'].some((key) => key in patch);
      if (reclassify) await refreshAssets({ keepSelection: true });
    } catch (error) {
      showToast({ message: error.message, tone: 'error' });
    } finally {
      nsfw.saving = false;
    }
  }

  /** Blur mode for the menu: 'all' (everything), 'nsfw' (only NSFW) or 'off'. */
  function setBlurMode(mode) {
    updateNsfwSettings({ preview: mode === 'all', nsfw_blur: mode !== 'off' });
  }

  async function nsfwScan(action = 'start') {
    if (!filters.root) return;
    try {
      const payload = await readJson(
        await fetch(API.nsfwScan, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ root: filters.root, action })
        }),
        'NSFW scan failed'
      );
      nsfw.task = payload.task || null;
      await fetchNsfwStatus();
    } catch (error) {
      showToast({ message: error.message, tone: 'error', timeout: 9000 });
    }
  }

  /** How to blur an asset: null, { mode: 'image' } or { mode: 'regions', regions }. */
  function blurFor(asset) {
    if (!asset) return null;
    if (blurThumbnails?.value) return { mode: 'image' };
    const verdict = asset.nsfw;
    if (!nsfw.settings.nsfw_blur || verdict?.rating !== 'nsfw') return null;
    if (nsfw.settings.nsfw_blur_style === 'regions' && Array.isArray(verdict.regions) && verdict.regions.length) {
      return { mode: 'regions', regions: verdict.regions };
    }
    return { mode: 'image' };
  }

  onBeforeUnmount(() => clearTimeout(nsfwPollTimer));

  watch(
    () => filters.root,
    () => {
      liveNewCount.value = 0;
      filters.collection = '';
      filters.similarTo = '';
      fetchFacets();
      fetchCollections();
      fetchNsfwStatus();
    },
    { immediate: true }
  );

  const library = {
    facets,
    collections,
    liveNewCount,
    comfyBusy,
    fetchFacets,
    fetchCollections,
    createCollection,
    addToCollection,
    removeFromCollection,
    renameCollection,
    deleteCollection,
    collectionById,
    applyLiveUpdates,
    applySearch,
    findSimilar,
    queueInComfy,
    rate,
    rateSelection,
    setRatingFilter,
    trashAllRejects,
    cullBusy,
    nsfw,
    fetchNsfwStatus,
    updateNsfwSettings,
    setBlurMode,
    nsfwScan,
    blurFor,
    overlayComponent: markRaw(NsfwOverlay),
    assets
  };
  // reactive() unwraps the refs so templates can read library.facets, library.liveNewCount directly.
  const exposed = reactive(library);
  provide(LIBRARY_KEY, exposed);
  return exposed;
}
