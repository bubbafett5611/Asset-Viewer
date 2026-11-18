import { describeLoadedCount } from '../formatters.js';

export function useAssets(options) {
  const {
    API,
    buildQuery,
    nextTick,
    pageSize,
    filters,
    offset,
    assets,
    selectedAsset,
    selectedPath,
    selectedPaths,
    lastSelectedIndex,
    lastSelectedDuplicateIndex,
    details,
    statusText,
    isLoading,
    isLoadingMore,
    assetError,
    paginationError,
    isUploading,
    isDeleting,
    safeDelete,
    hasMore,
    assetTotal,
    notify,
    blurThumbnails,
    isDropOverlayVisible,
    isDeleteConfirmVisible,
    currentRootLabel,
    activeTab,
    duplicateStatusText,
    replaceSelectedPaths,
    measureAssetList,
    removePathsFromDuplicateGroups,
    findAssetByPath,
    isAllowedImageFile,
    onSelectAsset
  } = options;

  let requestId = 0;
  let controller = null;
  let loadedIdentity = '';
  const queryIdentity = () =>
    JSON.stringify([
      filters.root,
      filters.folder,
      filters.q,
      filters.ext,
      filters.metadataBadge,
      filters.favorites,
      filters.sortBy,
      filters.sortDir
    ]);

  async function fetchAssets({ append = false, keepSelection = false, refreshIndex = false } = {}) {
    const id = ++requestId;
    controller?.abort();
    controller = new AbortController();
    const identity = queryIdentity();
    const isCurrent = () => id === requestId && identity === queryIdentity();
    assetError.value = '';
    paginationError.value = false;
    if (!filters.root) {
      assets.value = [];
      isLoading.value = false;
      isLoadingMore.value = false;
      hasMore.value = false;
      if (assetTotal) assetTotal.value = null;
      statusText.value = 'No library selected.';
      return;
    }
    const nextOffset = append ? offset.value + pageSize : 0;
    isLoading.value = !append;
    isLoadingMore.value = append;
    if (!append) {
      statusText.value = 'Loading media...';
    }

    try {
      const url = buildQuery(API.list, {
        root: filters.root,
        q: filters.q,
        folder: filters.folder,
        ext: filters.ext,
        sort_by: filters.sortBy,
        sort_dir: filters.sortDir,
        metadata_badges: filters.metadataBadge,
        favorites: filters.favorites,
        limit: pageSize,
        offset: nextOffset,
        refresh_index: refreshIndex ? 'true' : ''
      });

      const response = await fetch(url, { signal: controller.signal });
      if (!response.ok) {
        throw new Error(`Failed to load media (${response.status})`);
      }

      const payload = await response.json();
      if (!isCurrent()) return;
      const incoming = Array.isArray(payload.assets) ? payload.assets : [];

      offset.value = nextOffset;
      loadedIdentity = identity;
      assets.value = append ? assets.value.concat(incoming) : incoming;
      const total = Number.isFinite(payload.total) ? payload.total : null;
      if (assetTotal) assetTotal.value = total;
      hasMore.value = total === null ? incoming.length === pageSize : assets.value.length < total;
      statusText.value = describeLoadedCount(assets.value.length, total);

      if (!append && !keepSelection) {
        selectedAsset.value = null;
        selectedPath.value = '';
        details.value = null;
        replaceSelectedPaths([]);
        lastSelectedIndex.value = -1;
      }

      if (keepSelection && selectedPath.value) {
        const refreshed = assets.value.find((asset) => asset.path === selectedPath.value);
        selectedAsset.value = refreshed || null;
        if (!refreshed) {
          selectedPath.value = '';
          details.value = null;
        }
      }

      await nextTick();
      measureAssetList();
    } catch (error) {
      if (!isCurrent() || error.name === 'AbortError') return;
      assetError.value = error?.message || 'Failed to load media.';
      paginationError.value = append;
      statusText.value = error?.message || 'Failed to load media.';
    } finally {
      if (id === requestId) {
        isLoading.value = false;
        isLoadingMore.value = false;
      }
    }
  }

  async function refreshAssets(options = {}) {
    const refreshOptions = options instanceof Event ? {} : options;
    await fetchAssets({
      append: false,
      keepSelection: Boolean(refreshOptions.keepSelection),
      refreshIndex: Boolean(refreshOptions.refreshIndex)
    });
  }

  async function loadMore() {
    if (!hasMore.value || isLoading.value || isLoadingMore.value || loadedIdentity !== queryIdentity()) {
      return;
    }
    await fetchAssets({ append: true });
  }

  function toggleBlurThumbnails() {
    blurThumbnails.value = !blurThumbnails.value;
  }

  function requestDeleteSelected(event = null) {
    const deleteCount = selectedPaths.value.size || (selectedPath.value ? 1 : 0);
    if (!deleteCount || isDeleting.value) {
      return;
    }
    if (event?.shiftKey) {
      confirmDelete({ safeDeleteOverride: false, skipConfirm: true });
      return;
    }
    isDeleteConfirmVisible.value = true;
  }

  function requestDeleteAsset(asset, event = null) {
    if (!asset?.path) {
      return;
    }
    selectedAsset.value = asset;
    selectedPath.value = asset.path;
    replaceSelectedPaths([asset.path]);
    lastSelectedIndex.value = assets.value.findIndex((item) => item.path === asset.path);
    if (event?.shiftKey) {
      confirmDelete({ safeDeleteOverride: false, skipConfirm: true });
      return;
    }
    isDeleteConfirmVisible.value = true;
  }

  function hideDeleteConfirm() {
    isDeleteConfirmVisible.value = false;
  }

  async function confirmDelete({ safeDeleteOverride = null, skipConfirm = false } = {}) {
    const paths = Array.from(selectedPaths.value.size ? selectedPaths.value : new Set([selectedPath.value])).filter(
      Boolean
    );
    if (!paths.length) {
      return;
    }

    const shouldSafeDelete = safeDeleteOverride === null ? safeDelete.value : Boolean(safeDeleteOverride);
    isDeleting.value = true;
    isDeleteConfirmVisible.value = false;
    statusText.value =
      skipConfirm && !shouldSafeDelete
        ? `Permanently deleting ${paths.length} media files...`
        : `Deleting ${paths.length} media files...`;

    try {
      const response = await fetch(API.delete, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ root: filters.root, paths, safe_delete: shouldSafeDelete })
      });
      if (!response.ok) {
        throw new Error(`Delete failed (${response.status})`);
      }
      const payload = await response.json();
      const deleted = Array.isArray(payload.deleted) ? payload.deleted.length : 0;
      const errors = Array.isArray(payload.errors) ? payload.errors.length : 0;
      const deletedPaths = Array.isArray(payload.deleted) ? payload.deleted : paths;
      const deletedPathSet = new Set(deletedPaths);
      const selectionAfterDelete = Array.from(selectedPaths.value).filter((path) => !deletedPathSet.has(path));
      const hasNewSelection =
        selectionAfterDelete.length > 0 || (selectedPath.value && !deletedPathSet.has(selectedPath.value));
      removePathsFromDuplicateGroups(deletedPaths);
      assets.value = assets.value.filter((asset) => !deletedPathSet.has(asset.path));
      if (hasNewSelection) {
        replaceSelectedPaths(selectionAfterDelete);
        if (!selectedPath.value || deletedPathSet.has(selectedPath.value)) {
          selectedPath.value = selectionAfterDelete[0] || '';
          selectedAsset.value = findAssetByPath(selectedPath.value);
        }
      } else {
        replaceSelectedPaths([]);
        selectedAsset.value = null;
        selectedPath.value = '';
        details.value = null;
        lastSelectedIndex.value = -1;
        lastSelectedDuplicateIndex.value = -1;
      }
      if (activeTab.value !== 'duplicates') {
        await refreshAssets({ keepSelection: hasNewSelection });
      }
      const deleteVerb = shouldSafeDelete ? 'Deleted' : 'Permanently deleted';
      statusText.value = errors
        ? `${deleteVerb} ${deleted}; ${errors} failed.`
        : `${deleteVerb} ${deleted} media files.`;
      const trashed = Array.isArray(payload.moved) ? payload.moved : [];
      if (notify && shouldSafeDelete && trashed.length) {
        notify({
          message: `Moved ${trashed.length} ${trashed.length === 1 ? 'file' : 'files'} to trash.`,
          tone: 'success',
          timeout: 10000,
          action: { label: 'Undo', run: () => restoreTrashed(trashed) }
        });
      } else if (notify && deleted) {
        notify({ message: statusText.value, tone: errors ? 'warn' : 'success' });
      }
      if (activeTab.value === 'duplicates') {
        duplicateStatusText.value = hasNewSelection
          ? `${selectedPaths.value.size} selected`
          : errors
            ? `${deleteVerb} ${deleted}; ${errors} failed.`
            : `${deleteVerb} ${deleted} duplicate media files.`;
      }
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Delete failed.';
    } finally {
      isDeleting.value = false;
    }
  }

  async function restoreTrashed(items) {
    try {
      const response = await fetch(API.restore, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ items })
      });
      if (!response.ok) {
        throw new Error(`Restore failed (${response.status})`);
      }
      const payload = await response.json();
      const restored = Array.isArray(payload.restored) ? payload.restored.length : 0;
      const failed = Array.isArray(payload.errors) ? payload.errors.length : 0;
      if (activeTab.value !== 'duplicates') {
        await refreshAssets({ keepSelection: true });
      }
      statusText.value = failed
        ? `Restored ${restored} media files; ${failed} failed.`
        : `Restored ${restored} media files.`;
      notify?.({ message: statusText.value, tone: failed ? 'warn' : 'success' });
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Restore failed.';
      notify?.({ message: statusText.value, tone: 'error' });
    }
  }

  async function uploadFiles(files) {
    if (!filters.root) {
      statusText.value = 'Select a folder before uploading.';
      return;
    }

    const allowedFiles = Array.from(files || []).filter(isAllowedImageFile);
    if (!allowedFiles.length) {
      statusText.value = 'Only supported image and video files can be uploaded.';
      return;
    }

    const form = new FormData();
    for (const file of allowedFiles) {
      form.append('files', file, file.name || 'upload.png');
    }

    isUploading.value = true;
    statusText.value = `Uploading ${allowedFiles.length} images to ${currentRootLabel.value}...`;

    try {
      const response = await fetch(buildQuery(API.upload, { root: filters.root }), {
        method: 'POST',
        body: form
      });
      if (!response.ok) {
        throw new Error(`Upload failed (${response.status})`);
      }
      const payload = await response.json();
      const uploaded = Array.isArray(payload.uploaded) ? payload.uploaded : [];
      const skipped = Array.isArray(payload.skipped) ? payload.skipped.length : 0;
      await refreshAssets({ keepSelection: false });
      if (uploaded[0]) {
        const refreshed = assets.value.find((asset) => asset.path === uploaded[0].path) || uploaded[0];
        if (onSelectAsset) {
          await onSelectAsset(refreshed);
        }
      }
      statusText.value = `Uploaded ${uploaded.length} media files${skipped ? `; ${skipped} skipped` : ''}.`;
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Upload failed.';
    } finally {
      isUploading.value = false;
    }
  }

  function eventHasFileDrag(event) {
    const dataTransfer = event.dataTransfer;
    if (!dataTransfer) {
      return false;
    }
    const items = Array.from(dataTransfer.items || []);
    if (items.length) {
      return items.some(
        (item) =>
          item?.kind === 'file' &&
          (String(item.type || '')
            .toLowerCase()
            .startsWith('image/') ||
            String(item?.type || '').toLowerCase() === 'video/mp4' ||
            isAllowedImageFile(item.getAsFile?.()))
      );
    }
    return Array.from(dataTransfer.files || []).some(isAllowedImageFile);
  }

  function hideDropOverlay() {
    isDropOverlayVisible.value = false;
    document.body.classList.remove('drag-upload-active');
  }

  function showDropOverlay() {
    isDropOverlayVisible.value = true;
    document.body.classList.add('drag-upload-active');
  }

  function onWindowDragEnter(event) {
    if (!eventHasFileDrag(event)) {
      return;
    }
    event.preventDefault();
    showDropOverlay();
  }

  function onWindowDragOver(event) {
    if (!eventHasFileDrag(event)) {
      return;
    }
    event.preventDefault();
    event.dataTransfer.dropEffect = 'copy';
    showDropOverlay();
  }

  function onWindowDragLeave(event) {
    if (!eventHasFileDrag(event)) {
      return;
    }
    event.preventDefault();
  }

  function onWindowDrop(event) {
    const files = Array.from(event.dataTransfer?.files || []).filter(isAllowedImageFile);
    hideDropOverlay();
    if (!files.length) {
      return;
    }
    event.preventDefault();
    uploadFiles(files);
  }

  return {
    fetchAssets,
    refreshAssets,
    loadMore,
    toggleBlurThumbnails,
    requestDeleteSelected,
    requestDeleteAsset,
    hideDeleteConfirm,
    confirmDelete,
    restoreTrashed,
    uploadFiles,
    hideDropOverlay,
    onWindowDragEnter,
    onWindowDragOver,
    onWindowDragLeave,
    onWindowDrop
  };
}
