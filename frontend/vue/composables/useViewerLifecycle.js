import { onMounted, onUnmounted, watch } from '/vendor/vue.esm-browser.prod.js';

export function useViewerLifecycle(options) {
  const {
    settingsKey,
    activeTab,
    filters,
    duplicateIncludeNear,
    duplicateNearThreshold,
    offset,
    fetchAssets,
    fetchTags,
    hasLoadedTags,
    isLoadingTags,
    fetchFolderStats,
    isLoadingFolderStats,
    fetchMetadataHealth,
    isLoadingMetadataHealth,
    tagFilters,
    scheduleTagSearch,
    clearTagSearchTimer,
    fetchSettings,
    fetchAppInfo,
    isAutoUpdateCheckEnabled,
    fetchRoots,
    statusText,
    onWindowDragEnter,
    onWindowDragOver,
    onWindowDragLeave,
    onWindowDrop,
    hideDropOverlay,
    measureAssetList,
    onDocumentKeydown,
    checkForUpdates
  } = options;

  let searchTimer = null;
  const cleanupCallbacks = [];

  function addWindowListener(name, handler, options) {
    window.addEventListener(name, handler, options);
    cleanupCallbacks.push(() => window.removeEventListener(name, handler, options));
  }

  function addDocumentListener(name, handler, options) {
    document.addEventListener(name, handler, options);
    cleanupCallbacks.push(() => document.removeEventListener(name, handler, options));
  }

  watch(
    () => ({
      activeTab: activeTab.value,
      root: filters.root,
      sortBy: filters.sortBy,
      sortDir: filters.sortDir,
      duplicateIncludeNear: duplicateIncludeNear.value,
      duplicateNearThreshold: duplicateNearThreshold.value
    }),
    (settings) => {
      try {
        window.localStorage.setItem(settingsKey, JSON.stringify(settings));
      } catch {
        // ignore settings persistence failures
      }
    },
    { deep: true }
  );

  watch(
    () => [filters.root, filters.ext, filters.metadataBadge, filters.sortBy, filters.sortDir],
    async () => {
      offset.value = 0;
      await fetchAssets({ append: false });
    }
  );

  watch(
    () => filters.q,
    () => {
      if (searchTimer) {
        clearTimeout(searchTimer);
      }
      searchTimer = setTimeout(async () => {
        offset.value = 0;
        await fetchAssets({ append: false });
      }, 220);
    }
  );

  watch(
    () => activeTab.value,
    async (tab) => {
      if (tab === 'tags' && !hasLoadedTags.value && !isLoadingTags.value) {
        await fetchTags();
      }
      if (tab === 'stats' && !isLoadingFolderStats.value) {
        await fetchFolderStats();
      }
      if (tab === 'stats' && !isLoadingMetadataHealth.value) {
        await fetchMetadataHealth({ refresh: false, cacheOnly: true });
      }
    }
  );

  watch(
    () => [tagFilters.q, tagFilters.category, tagFilters.view],
    () => {
      scheduleTagSearch();
    }
  );

  onMounted(async () => {
    addWindowListener('dragenter', onWindowDragEnter);
    addWindowListener('dragover', onWindowDragOver);
    addWindowListener('dragleave', onWindowDragLeave);
    addWindowListener('drop', onWindowDrop);
    addWindowListener('dragend', hideDropOverlay);
    addWindowListener('blur', hideDropOverlay);
    addWindowListener('resize', measureAssetList);
    addDocumentListener('keydown', onDocumentKeydown);
    addDocumentListener('visibilitychange', () => {
      if (document.hidden) {
        hideDropOverlay();
      }
    });

    try {
      await fetchSettings();
      await fetchAppInfo?.();
      await fetchRoots();
      await fetchAssets({ append: false });
      if (activeTab.value === 'stats') {
        await fetchFolderStats();
        await fetchMetadataHealth({ refresh: false, cacheOnly: true });
      }
      if (isAutoUpdateCheckEnabled?.()) {
        await checkForUpdates?.();
      }
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Initialization failed.';
    }
  });

  onUnmounted(() => {
    if (searchTimer) {
      clearTimeout(searchTimer);
    }
    clearTagSearchTimer();
    cleanupCallbacks.forEach((cleanup) => cleanup());
    hideDropOverlay();
  });
}
