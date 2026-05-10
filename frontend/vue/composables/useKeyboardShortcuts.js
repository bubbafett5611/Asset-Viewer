export function useKeyboardShortcuts(options) {
  const {
    isTypingTarget,
    compareLeft,
    compareRight,
    closeCompare,
    isDeleteConfirmVisible,
    hideDeleteConfirm,
    selectedPaths,
    clearSelection,
    activeTab,
    selectAllCurrentItems,
    copyText,
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

    const key = String(event.key || '').toLowerCase();
    const isCommandKey = Boolean(event.ctrlKey || event.metaKey);

    if (key === 'shift' || key === 'control' || key === 'alt' || key === 'meta') {
      return;
    }

    if (isCommandKey && key === 'a' && (activeTab.value === 'assets' || activeTab.value === 'duplicates')) {
      event.preventDefault();
      selectAllCurrentItems();
      return;
    }

    if (isCommandKey && key === 'c' && selectedPaths.value.size > 0) {
      event.preventDefault();
      copyText(Array.from(selectedPaths.value).join('\n'));
      return;
    }

    if (isCommandKey && key === 'f' && activeTab.value === 'assets') {
      event.preventDefault();
      searchInputRef.value?.focus();
      searchInputRef.value?.select();
      return;
    }

    if (event.ctrlKey || event.metaKey || event.altKey) {
      return;
    }

    if (compareLeft.value && compareRight.value) {
      return;
    }

    if (key === '/' && activeTab.value === 'assets') {
      event.preventDefault();
      searchInputRef.value?.focus();
      searchInputRef.value?.select();
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
    if ((event.key === 'Delete' || event.key === 'Backspace') && deleteCount.value > 0) {
      event.preventDefault();
      requestDeleteSelected(event);
    }
  }

  return {
    onDocumentKeydown
  };
}
