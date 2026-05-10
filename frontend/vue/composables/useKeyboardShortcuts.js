export function useKeyboardShortcuts(options) {
  const {
    isTypingTarget,
    compareLeft,
    compareRight,
    closeCompare,
    isDeleteConfirmVisible,
    hideDeleteConfirm,
    isShortcutsModalVisible,
    hideShortcutsModal,
    selectedPaths,
    selectedAsset,
    selectedTag,
    clearSelection,
    activeTab,
    selectAllCurrentItems,
    copyText,
    copySelectedTagName,
    copySelectedName,
    copySelectedPaths,
    copySelectedImageToClipboard,
    toggleBlurThumbnails,
    refreshAssets,
    fetchTags,
    fetchFolderStats,
    fetchMetadataHealth,
    fetchSettings,
    scanDuplicates,
    exportSelectedAssets,
    exportDuplicateGroups,
    openContainingFolder,
    toggleTagFavorite,
    stepSelectedTag,
    showShortcutsModal,
    searchInputRef,
    virtualColumnCount,
    stepSelectedAsset,
    openSelectedAssetFull,
    selectedPath,
    replaceSelectedPaths,
    updateSelectionStatus,
    duplicateStatusText,
    deleteCount,
    requestDeleteSelected
  } = options;

  function onDocumentKeydown(event) {
    if (event.defaultPrevented || isTypingTarget(event.target)) {
      return;
    }

    if (event.key === 'Escape') {
      if (isShortcutsModalVisible.value) {
        hideShortcutsModal();
        event.preventDefault();
        return;
      }
      if (compareLeft.value && compareRight.value) {
        closeCompare();
        event.preventDefault();
        return;
      }
      if (isDeleteConfirmVisible.value) {
        hideDeleteConfirm();
        event.preventDefault();
        return;
      }
      if (selectedPaths.value.size) {
        clearSelection();
        event.preventDefault();
        return;
      }
    }

    if (isShortcutsModalVisible.value) {
      return;
    }

    const key = String(event.key || '').toLowerCase();
    const isCommandKey = Boolean(event.ctrlKey || event.metaKey);

    if (key === 'shift' || key === 'control' || key === 'alt' || key === 'meta') {
      return;
    }

    const isMediaTab = activeTab.value === 'assets';
    const isTagTab = activeTab.value === 'tags';
    const isDuplicateTab = activeTab.value === 'duplicates';
    const hasPathSelection = selectedPaths.value.size > 0 || Boolean(selectedPath.value);

    if (isCommandKey && key === 'a' && (activeTab.value === 'assets' || activeTab.value === 'duplicates')) {
      event.preventDefault();
      selectAllCurrentItems();
      return;
    }

    if (isCommandKey && event.shiftKey && key === 'c' && (isMediaTab || isDuplicateTab) && hasPathSelection) {
      event.preventDefault();
      copySelectedPaths();
      return;
    }

    if (isCommandKey && key === 'c' && isTagTab && selectedTag.value?.name) {
      event.preventDefault();
      copySelectedTagName();
      return;
    }

    if (isCommandKey && key === 'c' && isMediaTab && selectedAsset.value?.path) {
      event.preventDefault();
      copySelectedImageToClipboard();
      return;
    }

    if (isCommandKey && key === 'c' && isDuplicateTab && selectedPaths.value.size > 0) {
      event.preventDefault();
      copyText(Array.from(selectedPaths.value).join('\n'));
      return;
    }

    if (isCommandKey && key === 'o' && event.shiftKey && isMediaTab) {
      event.preventDefault();
      openContainingFolder();
      return;
    }

    if (isCommandKey && key === 'o' && isMediaTab) {
      event.preventDefault();
      openSelectedAssetFull();
      return;
    }

    if (isCommandKey && key === 'e' && (isMediaTab || isDuplicateTab)) {
      event.preventDefault();
      if (isDuplicateTab) {
        exportDuplicateGroups();
      } else {
        exportSelectedAssets();
      }
      return;
    }

    if (isCommandKey && event.shiftKey && key === 'd') {
      event.preventDefault();
      activeTab.value = 'duplicates';
      scanDuplicates();
      return;
    }

    if (isCommandKey && event.shiftKey && key === 'f' && isTagTab && selectedTag.value) {
      event.preventDefault();
      toggleTagFavorite(selectedTag.value);
      return;
    }

    if (isCommandKey && key === 'f' && isMediaTab) {
      event.preventDefault();
      searchInputRef.value?.focus();
      searchInputRef.value?.select();
      return;
    }

    if (isCommandKey && key === 'f' && isTagTab) {
      event.preventDefault();
      document.getElementById('tagSearchInput')?.focus();
      document.getElementById('tagSearchInput')?.select();
      return;
    }

    if (isCommandKey && key === 'l' && (isMediaTab || isTagTab)) {
      event.preventDefault();
      copySelectedName();
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }

    if (compareLeft.value && compareRight.value) {
      return;
    }

    if (key === '?') {
      event.preventDefault();
      showShortcutsModal();
      return;
    }

    if (['m', 't', 'd', 's'].includes(key)) {
      event.preventDefault();
      activeTab.value = { m: 'assets', t: 'tags', d: 'duplicates', s: 'stats' }[key];
      return;
    }

    if (key === 'b' && isMediaTab) {
      event.preventDefault();
      toggleBlurThumbnails();
      return;
    }

    if (key === 'r') {
      event.preventDefault();
      if (isMediaTab) {
        refreshAssets();
      } else if (isTagTab) {
        fetchTags();
      } else if (activeTab.value === 'stats') {
        fetchFolderStats();
        fetchMetadataHealth();
      } else if (activeTab.value === 'settings') {
        fetchSettings();
      }
      return;
    }

    if (key === '/' && isMediaTab) {
      event.preventDefault();
      searchInputRef.value?.focus();
      searchInputRef.value?.select();
      return;
    }

    if (key === '/' && isTagTab) {
      event.preventDefault();
      document.getElementById('tagSearchInput')?.focus();
      document.getElementById('tagSearchInput')?.select();
      return;
    }

    if (isTagTab) {
      if (event.key === 'ArrowDown') {
        event.preventDefault();
        stepSelectedTag(1);
        return;
      }
      if (event.key === 'ArrowUp') {
        event.preventDefault();
        stepSelectedTag(-1);
      }
      return;
    }

    if (activeTab.value !== 'assets' && activeTab.value !== 'duplicates') {
      return;
    }

    const rowStep = activeTab.value === 'assets' ? Math.max(1, virtualColumnCount.value) : 1;
    if (event.key === 'ArrowDown') {
      event.preventDefault();
      stepSelectedAsset(rowStep, { extend: event.shiftKey });
      return;
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      stepSelectedAsset(-rowStep, { extend: event.shiftKey });
      return;
    }
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      stepSelectedAsset(1, { extend: event.shiftKey });
      return;
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      stepSelectedAsset(-1, { extend: event.shiftKey });
      return;
    }
    if (event.key === 'Enter' && activeTab.value === 'assets') {
      event.preventDefault();
      openSelectedAssetFull();
      return;
    }
    if (event.key === ' ' && selectedPath.value) {
      event.preventDefault();
      if (selectedPaths.value.has(selectedPath.value) && selectedPaths.value.size === 1) {
        replaceSelectedPaths([]);
      } else {
        replaceSelectedPaths([selectedPath.value]);
      }
      updateSelectionStatus();
      if (activeTab.value === 'duplicates') {
        duplicateStatusText.value = selectedPaths.value.size
          ? `${selectedPaths.value.size} selected`
          : 'Selection cleared.';
      }
      return;
    }
    if (event.key === 'Delete' && deleteCount.value > 0) {
      event.preventDefault();
      requestDeleteSelected(event);
    }
  }

  return {
    onDocumentKeydown
  };
}
