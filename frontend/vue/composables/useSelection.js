export function useSelection(options) {
    const {
        assets,
        duplicateAssets,
        activeTab,
        selectedAsset,
        selectedPath,
        selectedPaths,
        lastSelectedIndex,
        lastSelectedDuplicateIndex,
        statusText,
        duplicateStatusText,
        loadAssetDetails,
        updateSelectionStatus,
        ensureSelectedVisible,
    } = options;

    function selectedPathSetHas(path) {
        return selectedPaths.value.has(path);
    }

    function replaceSelectedPaths(paths) {
        selectedPaths.value = new Set(paths.filter(Boolean));
    }

    async function selectAsset(asset, event = null) {
        if (!asset) {
            return;
        }

        const index = assets.value.findIndex((item) => item.path === asset.path);
        const isMultiKey = Boolean(event?.ctrlKey || event?.metaKey);
        const isRangeKey = Boolean(event?.shiftKey);

        if (isRangeKey && lastSelectedIndex.value >= 0 && index >= 0) {
            const start = Math.min(lastSelectedIndex.value, index);
            const end = Math.max(lastSelectedIndex.value, index);
            const next = new Set(selectedPaths.value);
            for (let i = start; i <= end; i += 1) {
                if (assets.value[i]?.path) {
                    next.add(assets.value[i].path);
                }
            }
            selectedPaths.value = next;
            updateSelectionStatus();
        } else if (isMultiKey) {
            const next = new Set(selectedPaths.value);
            if (next.has(asset.path)) {
                next.delete(asset.path);
            } else {
                next.add(asset.path);
            }
            selectedPaths.value = next;
            lastSelectedIndex.value = index;
            updateSelectionStatus();
        } else {
            replaceSelectedPaths([]);
            lastSelectedIndex.value = index;
        }

        selectedAsset.value = asset;
        selectedPath.value = asset.path;
        await loadAssetDetails(asset);
    }

    async function selectDuplicateAsset(asset, event = null) {
        if (!asset?.path) {
            return;
        }

        const isMultiKey = Boolean(event?.ctrlKey || event?.metaKey);
        const isRangeKey = Boolean(event?.shiftKey);
        const index = duplicateAssets.value.findIndex((item) => item.path === asset.path);
        if (isRangeKey && lastSelectedDuplicateIndex.value >= 0 && index >= 0) {
            const start = Math.min(lastSelectedDuplicateIndex.value, index);
            const end = Math.max(lastSelectedDuplicateIndex.value, index);
            const rangePaths = duplicateAssets.value.slice(start, end + 1).map((item) => item.path);
            replaceSelectedPaths(isMultiKey ? [...selectedPaths.value, ...rangePaths] : rangePaths);
        } else if (isMultiKey) {
            const next = new Set(selectedPaths.value);
            if (next.has(asset.path)) {
                next.delete(asset.path);
            } else {
                next.add(asset.path);
            }
            selectedPaths.value = next;
        } else {
            replaceSelectedPaths(selectedPaths.value.has(asset.path) && selectedPaths.value.size === 1 ? [] : [asset.path]);
        }

        selectedAsset.value = asset;
        selectedPath.value = asset.path;
        if (!isRangeKey) {
            lastSelectedDuplicateIndex.value = index;
        }
        duplicateStatusText.value = selectedPaths.value.size ? `${selectedPaths.value.size} selected` : "Selection cleared.";
    }

    function focusDuplicateAsset(asset) {
        if (!asset?.path) {
            return;
        }
        selectedAsset.value = asset;
        selectedPath.value = asset.path;
        lastSelectedDuplicateIndex.value = duplicateAssets.value.findIndex((item) => item.path === asset.path);
        replaceSelectedPaths([asset.path]);
        duplicateStatusText.value = "1 selected";
    }

    function clearSelection() {
        replaceSelectedPaths([]);
        lastSelectedIndex.value = -1;
        lastSelectedDuplicateIndex.value = -1;
        statusText.value = `Loaded ${assets.value.length} media item(s).`;
    }

    function selectAllAssets() {
        replaceSelectedPaths(assets.value.map((asset) => asset.path));
        updateSelectionStatus();
    }

    function selectAllCurrentItems() {
        if (activeTab.value === "duplicates") {
            replaceSelectedPaths(duplicateAssets.value.map((asset) => asset.path));
            duplicateStatusText.value = `${selectedPaths.value.size} selected`;
            return;
        }
        selectAllAssets();
    }

    async function stepSelectedAsset(delta, { extend = false } = {}) {
        const items = activeTab.value === "duplicates" ? duplicateAssets.value : assets.value;
        if (!items.length) {
            return;
        }
        const currentIndex = items.findIndex((asset) => asset.path === selectedPath.value);
        const startIndex = currentIndex >= 0 ? currentIndex : (delta < 0 ? items.length : -1);
        const nextIndex = Math.max(0, Math.min(items.length - 1, startIndex + delta));
        const nextAsset = items[nextIndex];
        if (!nextAsset) {
            return;
        }

        if (activeTab.value === "duplicates") {
            if (extend && selectedPath.value) {
                const anchor = lastSelectedDuplicateIndex.value >= 0 ? lastSelectedDuplicateIndex.value : currentIndex;
                const start = Math.min(anchor, nextIndex);
                const end = Math.max(anchor, nextIndex);
                replaceSelectedPaths(items.slice(start, end + 1).map((asset) => asset.path));
                selectedAsset.value = nextAsset;
                selectedPath.value = nextAsset.path;
                duplicateStatusText.value = `${selectedPaths.value.size} selected`;
            } else {
                focusDuplicateAsset(nextAsset);
            }
            return;
        }

        if (extend && selectedPath.value) {
            await selectAsset(nextAsset, { shiftKey: true });
        } else {
            await selectAsset(nextAsset);
        }
        ensureSelectedVisible(nextIndex);
    }

    return {
        selectedPathSetHas,
        replaceSelectedPaths,
        selectAsset,
        selectDuplicateAsset,
        focusDuplicateAsset,
        clearSelection,
        selectAllAssets,
        selectAllCurrentItems,
        stepSelectedAsset,
    };
}
