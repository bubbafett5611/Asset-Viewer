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
    isUploading,
    isDeleting,
    safeDelete,
    hasMore,
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

  async function fetchAssets({ append = false, keepSelection = false } = {}) {
    if (!filters.root) {
      assets.value = [];
      return;
    }

    if (append) {
      isLoadingMore.value = true;
    } else {
      isLoading.value = true;
      statusText.value = 'Loading media...';
    }

    try {
      const url = buildQuery(API.list, {
        root: filters.root,
        q: filters.q,
        ext: filters.ext,
        sort_by: filters.sortBy,
        sort_dir: filters.sortDir,
        metadata_badges: filters.metadataBadge,
        limit: pageSize,
        offset: offset.value
      });

      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to load media (${response.status})`);
      }

      const payload = await response.json();
      const incoming = Array.isArray(payload.assets) ? payload.assets : [];

      assets.value = append ? assets.value.concat(incoming) : incoming;
      hasMore.value = incoming.length === pageSize;
      statusText.value = `Loaded ${assets.value.length} media item(s).`;

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
      console.error(error);
      statusText.value = error?.message || 'Failed to load media.';
    } finally {
      isLoading.value = false;
      isLoadingMore.value = false;
    }
  }

  async function refreshAssets(options = {}) {
    offset.value = 0;
    await fetchAssets({ append: false, keepSelection: Boolean(options.keepSelection) });
  }

  async function loadMore() {
    offset.value += pageSize;
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
        ? `Permanently deleting ${paths.length} media item(s)...`
        : `Deleting ${paths.length} media item(s)...`;

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
        : `${deleteVerb} ${deleted} media item(s).`;
      if (activeTab.value === 'duplicates') {
        duplicateStatusText.value = hasNewSelection
          ? `${selectedPaths.value.size} selected`
          : errors
            ? `${deleteVerb} ${deleted}; ${errors} failed.`
            : `${deleteVerb} ${deleted} duplicate media item(s).`;
      }
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Delete failed.';
    } finally {
      isDeleting.value = false;
    }
  }

  async function uploadFiles(files) {
    if (!filters.root) {
      statusText.value = 'Select a folder before uploading.';
      return;
    }

    const allowedFiles = Array.from(files || []).filter(isAllowedImageFile);
    if (!allowedFiles.length) {
      statusText.value = 'Only image files can be uploaded.';
      return;
    }

    const form = new FormData();
    for (const file of allowedFiles) {
      form.append('files', file, file.name || 'upload.png');
    }

    isUploading.value = true;
    statusText.value = `Uploading ${allowedFiles.length} image(s) to ${currentRootLabel.value}...`;

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
      statusText.value = `Uploaded ${uploaded.length} image(s)${skipped ? `; ${skipped} skipped` : ''}.`;
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
    uploadFiles,
    hideDropOverlay,
    onWindowDragEnter,
    onWindowDragOver,
    onWindowDragLeave,
    onWindowDrop
  };
}
