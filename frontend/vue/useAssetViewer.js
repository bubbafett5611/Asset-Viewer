import { computed, nextTick, reactive, ref } from '/vendor/vue.esm-browser.prod.js';
import { API, buildQuery, fileUrl, thumbUrl } from '/vue/api.js';
import { useSelection } from '/vue/composables/useSelection.js';
import { useTags } from '/vue/composables/useTags.js';
import { useDuplicates } from '/vue/composables/useDuplicates.js';
import { useKeyboardShortcuts } from '/vue/composables/useKeyboardShortcuts.js';
import { useAssets } from '/vue/composables/useAssets.js';
import { useSettings } from '/vue/composables/useSettings.js';
import { useStats } from '/vue/composables/useStats.js';
import { useViewerLayout } from '/vue/composables/useViewerLayout.js';
import { useViewerLifecycle } from '/vue/composables/useViewerLifecycle.js';
import { useViewerProps } from '/vue/composables/useViewerProps.js';

const FAVORITES_KEY = 'bubba_asset_viewer_tag_favorites';
const RECENT_KEY = 'bubba_asset_viewer_tag_recent';
const SETTINGS_KEY = 'bubba_asset_viewer_settings';
const ALLOWED_UPLOAD_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff']);
const PREVIEWABLE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff']);
const METADATA_FILTERS = [
  { key: 'bubba_metadata', label: 'Bubba' },
  { key: 'workflow', label: 'Workflow' },
  { key: 'parameters', label: 'Params' },
  { key: 'no_tracked_metadata', label: 'No metadata' }
];

function loadArrayFromStorage(key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return [];
    }
    const parsed = JSON.parse(raw);
    return Array.isArray(parsed) ? parsed : [];
  } catch {
    return [];
  }
}

function loadObjectFromStorage(key) {
  try {
    const raw = window.localStorage.getItem(key);
    if (!raw) {
      return {};
    }
    const parsed = JSON.parse(raw);
    return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? parsed : {};
  } catch {
    return {};
  }
}

function saveArrayToStorage(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore localStorage write failures
  }
}

function parseAliases(value) {
  const raw = String(value || '').trim();
  if (!raw) {
    return [];
  }
  const parts = raw.includes('|') ? raw.split('|') : raw.split(',');
  return parts.map((item) => item.trim()).filter(Boolean);
}

function normalizeTagQuery(value) {
  return String(value || '')
    .trim()
    .toLowerCase()
    .replace(/[\s_-]+/g, '_')
    .replace(/^_+|_+$/g, '');
}

function isTypingTarget(target) {
  const tagName = String(target?.tagName || '').toLowerCase();
  return tagName === 'input' || tagName === 'textarea' || tagName === 'select' || target?.isContentEditable;
}

function fileExtension(name) {
  const match = String(name || '')
    .toLowerCase()
    .match(/\.[^.]+$/);
  return match ? match[0] : '';
}

function isAllowedImageFile(file) {
  if (!file) {
    return false;
  }
  const type = String(file.type || '').toLowerCase();
  if (type.startsWith('image/')) {
    return true;
  }
  return ALLOWED_UPLOAD_EXTENSIONS.has(fileExtension(file.name));
}

function isPreviewableAsset(asset) {
  return PREVIEWABLE_EXTENSIONS.has(String(asset?.extension || '').toLowerCase());
}

function getDensityConfig(density) {
  if (density === 'compact') {
    return { minWidth: 150, rowHeight: 228 };
  }
  if (density === 'large') {
    return { minWidth: 220, rowHeight: 318 };
  }
  return { minWidth: 180, rowHeight: 270 };
}

function formatBytes(bytes) {
  const value = Number(bytes || 0);
  if (!Number.isFinite(value) || value <= 0) {
    return '0 B';
  }
  const units = ['B', 'KB', 'MB', 'GB'];
  let size = value;
  let unitIndex = 0;
  while (size >= 1024 && unitIndex < units.length - 1) {
    size /= 1024;
    unitIndex += 1;
  }
  return `${size.toFixed(unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

export function useAssetViewerState() {
  const savedSettings = loadObjectFromStorage(SETTINGS_KEY);
  const activeTab = ref(
    ['assets', 'tags', 'duplicates', 'stats', 'settings'].includes(savedSettings.activeTab)
      ? savedSettings.activeTab
      : 'assets'
  );
  const roots = ref([]);
  const assets = ref([]);
  const selectedAsset = ref(null);
  const selectedPath = ref('');
  const selectedPaths = ref(new Set());
  const lastSelectedIndex = ref(-1);
  const lastSelectedDuplicateIndex = ref(-1);
  const details = ref(null);
  const statusText = ref('Loading roots...');
  const isLoading = ref(false);
  const isLoadingMore = ref(false);
  const isUploading = ref(false);
  const isDeleting = ref(false);
  const safeDelete = ref(true);
  const hasMore = ref(false);
  const blurThumbnails = ref(false);
  const isDropOverlayVisible = ref(false);
  const isDeleteConfirmVisible = ref(false);

  const tags = ref([]);
  const tagCategoriesList = ref([]);
  const selectedTag = ref(null);
  const tagStatusText = ref('Open Tag Browser to load local CSV...');
  const isLoadingTags = ref(false);
  const tagExamplesLoading = ref(false);
  const tagExamples = ref({});
  const hasLoadedTags = ref(false);
  const tagTotal = ref(0);
  const tagOffset = ref(0);
  const tagPageSize = 300;

  const duplicateGroups = ref([]);
  const duplicateSummary = ref(null);
  const duplicateStatusText = ref('Run a duplicate scan for the selected folder.');
  const duplicateTaskId = ref('');
  const duplicateTaskStatusText = ref('');
  const duplicateIncludeNear = ref(Boolean(savedSettings.duplicateIncludeNear));
  const duplicateNearThreshold = ref(
    Number.isFinite(Number(savedSettings.duplicateNearThreshold)) ? Number(savedSettings.duplicateNearThreshold) : 6
  );
  const duplicateSettings = reactive({
    includeNear: duplicateIncludeNear,
    nearThreshold: duplicateNearThreshold
  });
  const isScanningDuplicates = ref(false);
  const isCancellingDuplicateScan = ref(false);
  const duplicateScanProgress = ref(0);
  const duplicateScanPhase = ref('');
  const compareLeft = ref(null);
  const compareRight = ref(null);
  const compareSlider = ref(50);
  const compareStageRef = ref(null);
  const isCompareDragging = ref(false);
  const metadataHealth = ref(null);
  const metadataHealthStatus = ref('Metadata report not loaded.');
  const isLoadingMetadataHealth = ref(false);
  const folderStats = ref(null);
  const folderStatsStatus = ref('Folder stats not loaded.');
  const isLoadingFolderStats = ref(false);
  const rootStatsReports = reactive({});
  const appSettings = ref(null);
  const appSettingsSchema = ref(null);
  const settingsStatus = ref('Settings not loaded.');
  const isLoadingSettings = ref(false);
  const isSavingSettings = ref(false);
  const settingsListDrafts = reactive({});

  const favoriteTagNames = ref(new Set(loadArrayFromStorage(FAVORITES_KEY)));
  const recentTagNames = ref(loadArrayFromStorage(RECENT_KEY));

  const pageSize = 120;
  const offset = ref(0);

  const filters = reactive({
    root: String(savedSettings.root || ''),
    q: '',
    ext: '',
    metadataBadge: '',
    sortBy: ['name', 'modified', 'size', 'metadata'].includes(savedSettings.sortBy) ? savedSettings.sortBy : 'modified',
    sortDir: ['asc', 'desc'].includes(savedSettings.sortDir) ? savedSettings.sortDir : 'desc',
    density: 'comfortable'
  });

  const tagFilters = reactive({
    q: '',
    category: '',
    view: 'all'
  });

  const {
    detailsWidth,
    previewHeight,
    assetListRef,
    searchInputRef,
    densityClass,
    densityConfig,
    layoutStyle,
    assetListStyle,
    shouldVirtualize,
    virtualColumnCount,
    virtualRowHeight,
    visibleAssets,
    virtualSpacerStyle,
    virtualWindowStyle,
    measureAssetList,
    onAssetListScroll,
    setAssetListRef,
    setSearchInputRef,
    startDetailsResize,
    startPreviewResize
  } = useViewerLayout({
    assets,
    filters,
    getDensityConfig
  });

  const selectedCount = computed(() => selectedPaths.value.size);
  const deleteCount = computed(() => selectedPaths.value.size || (selectedPath.value ? 1 : 0));
  const currentRootLabel = computed(() => {
    const root = roots.value.find((item) => item.key === filters.root);
    return root?.label || root?.key || filters.root || 'selected folder';
  });
  const duplicateAssets = computed(() => {
    return duplicateGroups.value.flatMap((group) => (Array.isArray(group.assets) ? group.assets : []));
  });

  const {
    tagCategories,
    filteredTags,
    visibleTags,
    tagHasMore,
    tagCountText,
    selectedTagAliases,
    selectedTagExamples,
    fetchTags,
    isTagFavorite,
    toggleTagFavorite,
    loadMoreTags,
    selectTag,
    exampleImageUrl,
    tagSearchUrl,
    scheduleTagSearch,
    clearTagSearchTimer
  } = useTags({
    API,
    buildQuery,
    saveArrayToStorage,
    favoritesKey: FAVORITES_KEY,
    recentKey: RECENT_KEY,
    normalizeTagQuery,
    parseAliases,
    tags,
    tagFilters,
    tagCategoriesList,
    selectedTag,
    tagStatusText,
    isLoadingTags,
    tagExamplesLoading,
    tagExamples,
    hasLoadedTags,
    tagTotal,
    tagOffset,
    tagPageSize,
    favoriteTagNames,
    recentTagNames
  });

  const {
    folderStatsSummary,
    folderStatsMetrics,
    metadataStatsMetrics,
    statsPrimaryCount,
    statsRootReports,
    isLoadingAnyFolderStats,
    isLoadingAnyMetadataHealth,
    fetchRootMetadataHealth,
    fetchMetadataHealth,
    fetchRootFolderStats,
    fetchFolderStats
  } = useStats({
    API,
    buildQuery,
    roots,
    filters,
    rootStatsReports,
    metadataHealth,
    metadataHealthStatus,
    isLoadingMetadataHealth,
    folderStats,
    folderStatsStatus,
    isLoadingFolderStats,
    formatBytes
  });

  const {
    settingsSections,
    fetchSettings,
    settingsFieldValue,
    settingsListValue,
    settingsListDraftValue,
    updateSettingsListDraft,
    updateSetting,
    updateStringListItem,
    addStringListSetting,
    removeStringListItem
  } = useSettings({
    API,
    appSettings,
    appSettingsSchema,
    settingsStatus,
    isLoadingSettings,
    isSavingSettings,
    settingsListDrafts,
    roots,
    filters,
    blurThumbnails
  });

  const metadataFilterList = computed(() => METADATA_FILTERS);

  function blurActionButton(event) {
    event?.currentTarget?.blur?.();
  }

  function findAssetByPath(path, source = 'all') {
    if (!path) {
      return null;
    }
    if (source !== 'duplicates') {
      const asset = assets.value.find((item) => item.path === path);
      if (asset) {
        return asset;
      }
    }
    if (source !== 'assets') {
      for (const group of duplicateGroups.value) {
        const duplicateAsset = (group.assets || []).find((item) => item.path === path);
        if (duplicateAsset) {
          return duplicateAsset;
        }
      }
    }
    return null;
  }

  function updateSelectionStatus() {
    if (selectedPaths.value.size > 0) {
      statusText.value = `${selectedPaths.value.size} selected`;
    }
  }

  async function fetchRoots() {
    const response = await fetch(API.roots);
    if (!response.ok) {
      throw new Error(`Failed to load roots (${response.status})`);
    }
    const payload = await response.json();
    roots.value = Array.isArray(payload.roots) ? payload.roots : [];
    if (filters.root && !roots.value.some((root) => root.key === filters.root)) {
      filters.root = '';
    }
    if (!filters.root && roots.value.length > 0) {
      filters.root = roots.value[0].key;
    }
  }

  function metadataBadges(asset) {
    return Array.isArray(asset?.metadata_badges) ? asset.metadata_badges : [];
  }

  async function loadAssetDetails(asset) {
    details.value = null;
    try {
      const url = buildQuery(API.details, { path: asset.path });
      const response = await fetch(url);
      if (!response.ok) {
        throw new Error(`Failed to load details (${response.status})`);
      }
      const payload = await response.json();
      details.value = payload.asset || null;
    } catch (error) {
      console.error(error);
      details.value = null;
    }
  }

  function ensureSelectedVisible(index = assets.value.findIndex((asset) => asset.path === selectedPath.value)) {
    const element = assetListRef.value;
    if (!element || index < 0) {
      return;
    }
    if (shouldVirtualize.value) {
      const row = Math.floor(index / virtualColumnCount.value);
      element.scrollTop = Math.max(0, row * virtualRowHeight.value - virtualRowHeight.value);
      return;
    }
    const card = element.querySelectorAll('.asset-card')[index];
    card?.scrollIntoView({ block: 'nearest' });
  }

  const {
    selectedPathSetHas,
    replaceSelectedPaths,
    selectAsset,
    selectDuplicateAsset,
    focusDuplicateAsset,
    clearSelection,
    selectAllCurrentItems,
    stepSelectedAsset
  } = useSelection({
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
    ensureSelectedVisible
  });

  const {
    duplicateCountText,
    duplicateScanProgressText,
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
    cancelDuplicateScan
  } = useDuplicates({
    API,
    buildQuery,
    formatBytes,
    duplicateGroups,
    duplicateSummary,
    duplicateStatusText,
    duplicateTaskId,
    duplicateTaskStatusText,
    duplicateIncludeNear,
    duplicateNearThreshold,
    isScanningDuplicates,
    isCancellingDuplicateScan,
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
    isPreviewableAsset
  });

  const {
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
  } = useAssets({
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
    onSelectAsset: async (asset) => {
      await selectAsset(asset);
    }
  });

  function openSelectedAssetFull() {
    if (!selectedPath.value) {
      return;
    }
    window.open(fileUrl(selectedPath.value), '_blank', 'noopener,noreferrer');
  }

  async function openContainingFolder(asset = selectedAsset.value) {
    if (!asset?.path) {
      return;
    }
    try {
      const response = await fetch(API.openFolder, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: asset.path })
      });
      if (!response.ok) {
        throw new Error(`Open folder failed (${response.status})`);
      }
      statusText.value = 'Opened containing folder.';
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Open folder failed.';
    }
  }

  async function repairSelectedMetadata(asset = selectedAsset.value) {
    if (!asset?.path) {
      return;
    }
    statusText.value = 'Repairing metadata...';
    try {
      const response = await fetch(API.repairMetadata, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ path: asset.path })
      });
      if (!response.ok) {
        throw new Error(await responseErrorMessage(response, `Metadata repair failed (${response.status})`));
      }
      const payload = await response.json();
      const repairedAsset = payload.asset || null;
      if (repairedAsset) {
        const index = assets.value.findIndex((item) => item.path === repairedAsset.path);
        if (index >= 0) {
          assets.value[index] = { ...assets.value[index], ...repairedAsset };
        }
        selectedAsset.value = repairedAsset;
        details.value = repairedAsset;
      } else {
        await loadAssetDetails(asset);
      }
      statusText.value = payload.result?.repaired
        ? 'Bubba Metadata repaired.'
        : payload.result?.reason || 'Bubba Metadata already repaired.';
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Metadata repair failed.';
    }
  }

  async function copyText(value) {
    if (!value) {
      return;
    }
    try {
      await navigator.clipboard.writeText(String(value));
    } catch {
      // ignore clipboard failures
    }
  }

  const { onDocumentKeydown } = useKeyboardShortcuts({
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
  });

  async function responseErrorMessage(response, fallback) {
    try {
      const text = await response.text();
      const match = text.match(/<p>(.*?)<\/p>/i);
      if (match?.[1]) {
        return match[1];
      }
      if (text.trim()) {
        return text.trim();
      }
    } catch {
      // ignore response parsing failures
    }
    return fallback;
  }

  function selectedExportAssets() {
    const paths = Array.from(
      selectedPaths.value.size ? selectedPaths.value : new Set(selectedPath.value ? [selectedPath.value] : [])
    );
    return paths.map((path) => findAssetByPath(path)).filter(Boolean);
  }

  function downloadTextFile(filename, content, type = 'application/json') {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = document.createElement('a');
    link.href = url;
    link.download = filename;
    document.body.appendChild(link);
    link.click();
    link.remove();
    URL.revokeObjectURL(url);
  }

  function csvEscape(value) {
    const text = String(value ?? '');
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  }

  async function copySelectedPaths() {
    const assetsToCopy = selectedExportAssets();
    await copyText(assetsToCopy.map((asset) => asset.path).join('\n'));
    statusText.value = `Copied ${assetsToCopy.length} path(s).`;
    if (activeTab.value === 'duplicates') {
      duplicateStatusText.value = `Copied ${assetsToCopy.length} path(s).`;
    }
  }

  function exportSelectedAssets(format = 'json') {
    const rows = selectedExportAssets();
    if (!rows.length) {
      return;
    }
    if (format === 'csv') {
      const header = ['name', 'path', 'relative_path', 'extension', 'size_bytes', 'modified_ts'];
      const body = rows.map((asset) => header.map((key) => csvEscape(asset[key])).join(','));
      downloadTextFile('asset-selection.csv', [header.join(','), ...body].join('\n'), 'text/csv');
      return;
    }
    downloadTextFile('asset-selection.json', JSON.stringify(rows, null, 2));
  }

  function exportDuplicateGroups(format = 'json') {
    if (!duplicateGroups.value.length) {
      return;
    }
    if (format === 'csv') {
      const header = ['group_kind', 'group_key', 'name', 'path', 'relative_path', 'size_bytes', 'modified_ts'];
      const rows = duplicateGroups.value.flatMap((group) => {
        return (group.assets || []).map((asset) =>
          [group.kind, group.key, asset.name, asset.path, asset.relative_path, asset.size_bytes, asset.modified_ts]
            .map(csvEscape)
            .join(',')
        );
      });
      downloadTextFile('duplicate-groups.csv', [header.join(','), ...rows].join('\n'), 'text/csv');
      return;
    }
    downloadTextFile(
      'duplicate-groups.json',
      JSON.stringify({ summary: duplicateSummary.value, groups: duplicateGroups.value }, null, 2)
    );
  }

  function exportMetadataHealth(format = 'json', report = metadataHealth.value, rootLabel = 'metadata') {
    if (!report) {
      return;
    }
    const safeLabel =
      String(rootLabel || 'metadata')
        .replace(/[^a-z0-9_-]+/gi, '-')
        .replace(/^-+|-+$/g, '') || 'metadata';
    if (format === 'csv') {
      const rows = Object.entries(report).map(([key, value]) => `${csvEscape(key)},${csvEscape(value)}`);
      downloadTextFile(`${safeLabel}-metadata-health.csv`, ['metric,value', ...rows].join('\n'), 'text/csv');
      return;
    }
    downloadTextFile(`${safeLabel}-metadata-health.json`, JSON.stringify(report, null, 2));
  }

  const { assetsViewProps, tagsViewProps, duplicatesViewProps, statsViewProps, settingsViewProps } = useViewerProps({
    layoutStyle,
    filters,
    roots,
    metadataFilterList,
    assets,
    selectedAsset,
    details,
    selectedPath,
    selectedPathSetHas,
    blurThumbnails,
    statusText,
    selectedCount,
    deleteCount,
    isLoading,
    isLoadingMore,
    isDeleting,
    hasMore,
    currentRootLabel,
    densityClass,
    assetListStyle,
    shouldVirtualize,
    visibleAssets,
    virtualSpacerStyle,
    virtualWindowStyle,
    setAssetListRef,
    setSearchInputRef,
    onAssetListScroll,
    refreshAssets,
    loadMore,
    selectAsset,
    clearSelection,
    copySelectedPaths,
    exportSelectedAssets,
    openCompareSelection,
    requestDeleteSelected,
    requestDeleteAsset,
    hideDeleteConfirm,
    confirmDelete,
    safeDelete,
    startDetailsResize,
    startPreviewResize,
    openContainingFolder,
    repairSelectedMetadata,
    tagFilters,
    tagCategories,
    tagStatusText,
    tagCountText,
    visibleTags,
    selectedTag,
    selectedTagAliases,
    selectedTagExamples,
    tagExamplesLoading,
    isLoadingTags,
    tagHasMore,
    isTagFavorite,
    fetchTags,
    selectTag,
    toggleTagFavorite,
    loadMoreTags,
    exampleImageUrl,
    tagSearchUrl,
    duplicateSettings,
    isScanningDuplicates,
    isCancellingDuplicateScan,
    duplicateStatusText,
    duplicateTaskId,
    duplicateTaskStatusText,
    duplicateCountText,
    duplicateScanProgress,
    duplicateScanPhase,
    duplicateScanProgressText,
    duplicateGroups,
    canCompareSelection,
    scanDuplicates,
    cancelDuplicateScan,
    selectAllDuplicateGroupsExcept,
    exportDuplicateGroups,
    selectDuplicateAsset,
    selectDuplicateGroupPaths,
    selectDuplicateGroupExcept,
    duplicateKindLabel,
    duplicateGroupSubtitle,
    markDuplicateThumbFailed,
    statsRootReports,
    isLoadingAnyFolderStats,
    isLoadingAnyMetadataHealth,
    fetchFolderStats,
    fetchMetadataHealth,
    fetchRootFolderStats,
    fetchRootMetadataHealth,
    exportMetadataHealth,
    settingsSections,
    settingsStatus,
    isSavingSettings,
    settingsFieldValue,
    settingsListValue,
    settingsListDraftValue,
    updateSettingsListDraft,
    updateSetting,
    updateStringListItem,
    addStringListSetting,
    removeStringListItem
  });

  useViewerLifecycle({
    settingsKey: SETTINGS_KEY,
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
    fetchRoots,
    statusText,
    onWindowDragEnter,
    onWindowDragOver,
    onWindowDragLeave,
    onWindowDrop,
    hideDropOverlay,
    measureAssetList,
    onDocumentKeydown
  });

  return {
    activeTab,
    deleteCount,
    isUploading,
    isDeleting,
    safeDelete,
    isDropOverlayVisible,
    isDeleteConfirmVisible,
    currentRootLabel,
    duplicateTaskId,
    duplicateTaskStatusText,
    compareLeft,
    compareRight,
    compareSlider,
    compareStageRef,
    compareClipStyle,
    closeCompare,
    fileUrl,
    hideDeleteConfirm,
    confirmDelete,
    startCompareDrag,
    dragCompareDivider,
    stopCompareDrag,
    nudgeCompareDivider,
    assetsViewProps,
    tagsViewProps,
    duplicatesViewProps,
    statsViewProps,
    settingsViewProps
  };
}
