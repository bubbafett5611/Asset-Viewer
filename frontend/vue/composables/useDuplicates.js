import { computed } from "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js";

export function useDuplicates(options) {
    const {
        API,
        buildQuery,
        formatBytes,
        duplicateGroups,
        duplicateSummary,
        duplicateStatusText,
        duplicateIncludeNear,
        duplicateNearThreshold,
        isScanningDuplicates,
        duplicateScanProgress,
        duplicateScanPhase,
        compareLeft,
        compareRight,
        compareSlider,
        compareStageRef,
        isCompareDragging,
        selectedPaths,
        selectedPath,
        selectedAsset,
        lastSelectedDuplicateIndex,
        duplicateAssets,
        activeTab,
        filters,
        replaceSelectedPaths,
        findAssetByPath,
        blurActionButton,
        statusText,
        isPreviewableAsset,
    } = options;

    const duplicateCountText = computed(() => {
        if (!duplicateSummary.value) {
            return "No scan yet";
        }
        const summary = duplicateSummary.value;
        return `${summary.groups || 0} group(s) / ${summary.assets || 0} media item(s)`;
    });
    const duplicateScanProgressText = computed(() => {
        const percent = Math.round(Number(duplicateScanProgress.value || 0));
        return `${percent}%`;
    });
    const selectedCompareAssets = computed(() => {
        const paths = Array.from(selectedPaths.value);
        if (paths.length !== 2) {
            return [];
        }
        const source = activeTab.value === "duplicates" ? "duplicates" : "assets";
        const pair = paths.map((path) => findAssetByPath(path, source));
        if (pair.some((asset) => !asset || !isPreviewableAsset(asset))) {
            return [];
        }
        return pair;
    });
    const canCompareSelection = computed(() => selectedCompareAssets.value.length === 2);
    const compareClipStyle = computed(() => ({
        clipPath: `inset(0 ${100 - Number(compareSlider.value || 50)}% 0 0)`,
    }));

    function duplicateKindLabel(kind) {
        if (kind === "exact") {
            return "Exact files";
        }
        if (kind === "pixel") {
            return "Same pixels";
        }
        if (kind === "near") {
            return "Near duplicates";
        }
        return "Duplicates";
    }

    function duplicateGroupSubtitle(group) {
        const parts = [`${group.count || 0} media item(s)`];
        if (Number(group.wasted_bytes || 0) > 0) {
            parts.push(`${formatBytes(group.wasted_bytes)} reclaimable`);
        }
        if (group.kind === "near" && Number.isFinite(Number(group.distance))) {
            parts.push(`max distance ${group.distance}`);
        }
        return parts.join(" / ");
    }

    function markDuplicateThumbFailed(event) {
        event?.target?.closest?.(".duplicate-thumb")?.classList.add("thumb-failed");
    }

    function refreshDuplicateSummary() {
        if (!duplicateSummary.value) {
            return;
        }
        const groups = duplicateGroups.value;
        duplicateSummary.value = {
            ...duplicateSummary.value,
            groups: groups.length,
            assets: groups.reduce((total, group) => total + Number(group.count || 0), 0),
            exact_groups: groups.filter((group) => group.kind === "exact").length,
            pixel_groups: groups.filter((group) => group.kind === "pixel").length,
            near_groups: groups.filter((group) => group.kind === "near").length,
        };
    }

    function removePathsFromDuplicateGroups(paths) {
        const deletedPaths = new Set(paths.filter(Boolean));
        if (!deletedPaths.size || !duplicateGroups.value.length) {
            return;
        }
        duplicateGroups.value = duplicateGroups.value
            .map((group) => {
                const remainingAssets = Array.isArray(group.assets) ? group.assets.filter((asset) => !deletedPaths.has(asset.path)) : [];
                const sizes = remainingAssets.map((asset) => Number(asset.size_bytes || 0));
                return {
                    ...group,
                    assets: remainingAssets,
                    count: remainingAssets.length,
                    total_bytes: sizes.reduce((total, size) => total + size, 0),
                    wasted_bytes: sizes.length ? sizes.reduce((total, size) => total + size, 0) - Math.max(...sizes) : 0,
                };
            })
            .filter((group) => group.count > 1);
        refreshDuplicateSummary();
    }

    function setDuplicateSelection(paths) {
        const uniquePaths = [...new Set(paths.filter(Boolean))];
        replaceSelectedPaths(uniquePaths);
        const anchorPath = uniquePaths[0] || "";
        selectedPath.value = anchorPath;
        selectedAsset.value = anchorPath ? findAssetByPath(anchorPath, "duplicates") : null;
        lastSelectedDuplicateIndex.value = anchorPath ? duplicateAssets.value.findIndex((asset) => asset.path === anchorPath) : -1;
        duplicateStatusText.value = uniquePaths.length ? `${uniquePaths.length} selected` : "Selection cleared.";
    }

    function selectDuplicateGroupPaths(group, event = null) {
        blurActionButton(event);
        setDuplicateSelection((group?.assets || []).map((asset) => asset.path));
    }

    function duplicateKeepPath(groupAssets, keepMode) {
        const sorted = [...groupAssets].sort((left, right) => {
            if (keepMode === "largest") {
                return Number(right.size_bytes || 0) - Number(left.size_bytes || 0);
            }
            return Number(right.modified_ts || 0) - Number(left.modified_ts || 0);
        });
        return sorted[0]?.path;
    }

    function selectDuplicateGroupExcept(group, keepMode, event = null) {
        blurActionButton(event);
        const groupAssets = Array.isArray(group?.assets) ? group.assets : [];
        if (groupAssets.length < 2) {
            return;
        }
        const keepPath = duplicateKeepPath(groupAssets, keepMode);
        setDuplicateSelection(groupAssets.map((asset) => asset.path).filter((path) => path && path !== keepPath));
    }

    function selectAllDuplicateGroupsExcept(keepMode, event = null) {
        blurActionButton(event);
        const paths = [];
        duplicateGroups.value.forEach((group) => {
            const groupAssets = Array.isArray(group?.assets) ? group.assets : [];
            if (groupAssets.length < 2) {
                return;
            }
            const keepPath = duplicateKeepPath(groupAssets, keepMode);
            groupAssets.forEach((asset) => {
                if (asset.path && asset.path !== keepPath) {
                    paths.push(asset.path);
                }
            });
        });
        setDuplicateSelection(paths);
    }

    function openCompareSelection() {
        const pair = selectedCompareAssets.value;
        if (pair.length !== 2) {
            duplicateStatusText.value = "Need at least two previewable images to compare.";
            statusText.value = "Need exactly two previewable images selected to compare.";
            return;
        }
        compareLeft.value = pair[0];
        compareRight.value = pair[1];
        compareSlider.value = 50;
    }

    function setCompareSliderFromClientX(clientX) {
        const stage = compareStageRef.value;
        if (!stage) {
            return;
        }
        const rect = stage.getBoundingClientRect();
        const ratio = (Number(clientX) - rect.left) / Math.max(1, rect.width);
        compareSlider.value = Math.max(0, Math.min(100, Math.round(ratio * 1000) / 10));
    }

    function startCompareDrag(event) {
        isCompareDragging.value = true;
        event.currentTarget?.setPointerCapture?.(event.pointerId);
        setCompareSliderFromClientX(event.clientX);
        event.preventDefault();
    }

    function dragCompareDivider(event) {
        if (!isCompareDragging.value) {
            return;
        }
        setCompareSliderFromClientX(event.clientX);
        event.preventDefault();
    }

    function stopCompareDrag(event) {
        isCompareDragging.value = false;
        if (event.currentTarget?.hasPointerCapture?.(event.pointerId)) {
            event.currentTarget.releasePointerCapture(event.pointerId);
        }
    }

    function nudgeCompareDivider(event) {
        const step = event.shiftKey ? 10 : 2;
        if (event.key === "ArrowLeft") {
            compareSlider.value = Math.max(0, compareSlider.value - step);
            event.preventDefault();
        } else if (event.key === "ArrowRight") {
            compareSlider.value = Math.min(100, compareSlider.value + step);
            event.preventDefault();
        } else if (event.key === "Home") {
            compareSlider.value = 0;
            event.preventDefault();
        } else if (event.key === "End") {
            compareSlider.value = 100;
            event.preventDefault();
        }
    }

    function closeCompare() {
        isCompareDragging.value = false;
        compareLeft.value = null;
        compareRight.value = null;
    }

    function applyDuplicateProgress(progress) {
        if (!progress || typeof progress !== "object") {
            return;
        }
        duplicateScanProgress.value = Math.max(0, Math.min(Number(progress.percent || 0), 100));
        duplicateScanPhase.value = String(progress.stage || "");
        if (progress.message) {
            duplicateStatusText.value = String(progress.message);
        }
    }

    async function readDuplicateStream(response) {
        if (!response.body?.getReader) {
            return null;
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let buffer = "";
        let resultPayload = null;

        while (true) {
            const { value, done } = await reader.read();
            if (done) {
                break;
            }
            buffer += decoder.decode(value, { stream: true });
            const lines = buffer.split("\n");
            buffer = lines.pop() || "";
            for (const line of lines) {
                if (!line.trim()) {
                    continue;
                }
                const event = JSON.parse(line);
                if (event.type === "progress") {
                    applyDuplicateProgress(event.progress);
                } else if (event.type === "result") {
                    resultPayload = event;
                } else if (event.type === "error") {
                    throw new Error(event.error || "Duplicate scan failed.");
                }
            }
        }

        if (buffer.trim()) {
            const event = JSON.parse(buffer);
            if (event.type === "result") {
                resultPayload = event;
            }
        }
        return resultPayload;
    }

    async function scanDuplicates() {
        if (!filters.root) {
            duplicateStatusText.value = "Select a folder before scanning.";
            duplicateGroups.value = [];
            duplicateSummary.value = null;
            duplicateScanProgress.value = 0;
            duplicateScanPhase.value = "";
            return;
        }

        isScanningDuplicates.value = true;
        duplicateScanProgress.value = 0;
        duplicateScanPhase.value = "starting";
        duplicateGroups.value = [];
        duplicateSummary.value = null;
        duplicateStatusText.value = duplicateIncludeNear.value ? "Scanning duplicates and near duplicates..." : "Scanning duplicates...";
        try {
            const params = {
                root: filters.root,
                include_near: duplicateIncludeNear.value,
                near_threshold: duplicateNearThreshold.value,
            };
            const response = await fetch(buildQuery(API.duplicatesStream, params));
            if (!response.ok) {
                throw new Error(`Duplicate scan failed (${response.status})`);
            }
            const payload = await readDuplicateStream(response) || await fetch(buildQuery(API.duplicates, params)).then((fallbackResponse) => {
                if (!fallbackResponse.ok) {
                    throw new Error(`Duplicate scan failed (${fallbackResponse.status})`);
                }
                return fallbackResponse.json();
            });
            duplicateGroups.value = Array.isArray(payload.groups) ? payload.groups : [];
            duplicateSummary.value = payload.summary || null;
            duplicateScanProgress.value = 100;
            duplicateScanPhase.value = "complete";
            const groupCount = duplicateSummary.value?.groups || duplicateGroups.value.length;
            duplicateStatusText.value = groupCount ? `Found ${groupCount} duplicate group(s).` : "No duplicates found.";
        } catch (error) {
            console.error(error);
            duplicateGroups.value = [];
            duplicateSummary.value = null;
            duplicateScanProgress.value = 0;
            duplicateScanPhase.value = "";
            duplicateStatusText.value = error?.message || "Duplicate scan failed.";
        } finally {
            isScanningDuplicates.value = false;
        }
    }

    return {
        duplicateCountText,
        duplicateScanProgressText,
        selectedCompareAssets,
        canCompareSelection,
        compareClipStyle,
        duplicateKindLabel,
        duplicateGroupSubtitle,
        markDuplicateThumbFailed,
        removePathsFromDuplicateGroups,
        selectDuplicateGroupPaths,
        selectDuplicateGroupExcept,
        selectAllDuplicateGroupsExcept,
        openCompareSelection,
        startCompareDrag,
        dragCompareDivider,
        stopCompareDrag,
        nudgeCompareDivider,
        closeCompare,
        scanDuplicates,
    };
}
