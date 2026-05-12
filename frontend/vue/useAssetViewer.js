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
const UPDATE_NOTICE_KEY = 'bubba_asset_viewer_update_notice';
const UPDATE_CHECK_INTERVAL_MS = 24 * 60 * 60 * 1000;
const UPDATE_SNOOZE_INTERVAL_MS = 24 * 60 * 60 * 1000;
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

function saveObjectToStorage(key, value) {
  try {
    window.localStorage.setItem(key, JSON.stringify(value));
  } catch {
    // ignore localStorage write failures
  }
}

function normalizeVersion(value) {
  return String(value || '')
    .trim()
    .replace(/^v/i, '');
}

function parseVersion(value) {
  const raw = normalizeVersion(value);
  if (!raw) {
    return [0, 0, 0];
  }
  // Compare versions as major.minor.patch and ignore any additional segments.
  const [major = '0', minor = '0', patch = '0'] = raw.split('.').slice(0, 3);
  return [major, minor, patch].map((part) => {
    const numeric = Number.parseInt(String(part).replace(/[^0-9].*$/, ''), 10);
    return Number.isFinite(numeric) ? numeric : 0;
  });
}

function isVersionGreater(candidate, current) {
  const a = parseVersion(candidate);
  const b = parseVersion(current);
  for (let index = 0; index < 3; index += 1) {
    if (a[index] > b[index]) {
      return true;
    }
    if (a[index] < b[index]) {
      return false;
    }
  }
  return false;
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
  const isShortcutsModalVisible = ref(false);

  const tags = ref([]);
  const tagCategoriesList = ref([]);
  const selectedTag = ref(null);
  const tagCopyStatus = ref('');
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
  const appVersion = ref('0.0.0');
  const appRepo = ref('');
  const appReleasePageUrl = ref('');
  const isCheckingUpdates = ref(false);
  const updateCheckStatus = ref('');

  const updateNoticeState = reactive({
    currentVersion: '0.0.0',
    lastCheckedAt: 0,
    latestVersion: '',
    latestName: '',
    latestUrl: '',
    skippedVersion: '',
    snoozedVersion: '',
    snoozeUntil: 0
  });
  const updateNotice = ref(null);

  const favoriteTagNames = ref(new Set(loadArrayFromStorage(FAVORITES_KEY)));
  const recentTagNames = ref(loadArrayFromStorage(RECENT_KEY));
  let tagCopyStatusTimer = null;

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
    stepSelectedTag,
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

  async function fetchAppInfo() {
    try {
      const response = await fetch(API.appInfo);
      if (!response.ok) {
        return;
      }
      const payload = await response.json();
      appVersion.value = String(payload.current_version || appVersion.value || '0.0.0');
      appRepo.value = String(payload.repo || '');
      appReleasePageUrl.value = String(payload.release_page_url || '');
    } catch {
      // ignore app info failures; app can continue without this metadata
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

  function showShortcutsModal() {
    isShortcutsModalVisible.value = true;
  }

  function hideShortcutsModal() {
    isShortcutsModalVisible.value = false;
  }

  async function imageBlobToPngBlob(blob) {
    const bitmap = await window.createImageBitmap(blob);
    const canvas = document.createElement('canvas');
    canvas.width = bitmap.width;
    canvas.height = bitmap.height;
    const context = canvas.getContext('2d');
    if (!context) {
      bitmap.close?.();
      throw new Error('Could not prepare image for clipboard.');
    }
    context.drawImage(bitmap, 0, 0);
    bitmap.close?.();
    return new Promise((resolve, reject) => {
      canvas.toBlob((pngBlob) => {
        if (pngBlob) {
          resolve(pngBlob);
          return;
        }
        reject(new Error('Could not prepare image for clipboard.'));
      }, 'image/png');
    });
  }

  async function copySelectedImageToClipboard(asset = selectedAsset.value) {
    if (!asset?.path) {
      statusText.value = 'Select an image to copy.';
      return;
    }
    if (!isPreviewableAsset(asset)) {
      statusText.value = 'Selected asset is not a copyable image.';
      return;
    }
    if (!navigator.clipboard?.write || !window.ClipboardItem || !window.createImageBitmap) {
      statusText.value = 'Image clipboard copy is not supported by this browser.';
      return;
    }

    const assetName = asset.name || 'selected image';
    statusText.value = `Copying image "${assetName}"...`;
    try {
      const response = await fetch(fileUrl(asset.path));
      if (!response.ok) {
        throw new Error(`Image copy failed (${response.status})`);
      }
      const sourceBlob = await response.blob();
      const clipboardBlob = sourceBlob.type === 'image/png' ? sourceBlob : await imageBlobToPngBlob(sourceBlob);
      await navigator.clipboard.write([
        new window.ClipboardItem({
          [clipboardBlob.type || 'image/png']: clipboardBlob
        })
      ]);
      statusText.value = `Copied image "${assetName}" to clipboard.`;
    } catch (error) {
      console.error(error);
      statusText.value = error?.message || 'Image copy failed.';
    }
  }

  const { onDocumentKeydown } = useKeyboardShortcuts({
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
  });

  function loadUpdateNoticeState() {
    const saved = loadObjectFromStorage(UPDATE_NOTICE_KEY);
    updateNoticeState.currentVersion = String(saved.currentVersion || '0.0.0');
    updateNoticeState.lastCheckedAt = Number(saved.lastCheckedAt) || 0;
    updateNoticeState.latestVersion = String(saved.latestVersion || '');
    updateNoticeState.latestName = String(saved.latestName || '');
    updateNoticeState.latestUrl = String(saved.latestUrl || '');
    updateNoticeState.skippedVersion = String(saved.skippedVersion || '');
    updateNoticeState.snoozedVersion = String(saved.snoozedVersion || '');
    updateNoticeState.snoozeUntil = Number(saved.snoozeUntil) || 0;
  }

  function persistUpdateNoticeState() {
    saveObjectToStorage(UPDATE_NOTICE_KEY, {
      currentVersion: updateNoticeState.currentVersion,
      lastCheckedAt: updateNoticeState.lastCheckedAt,
      latestVersion: updateNoticeState.latestVersion,
      latestName: updateNoticeState.latestName,
      latestUrl: updateNoticeState.latestUrl,
      skippedVersion: updateNoticeState.skippedVersion,
      snoozedVersion: updateNoticeState.snoozedVersion,
      snoozeUntil: updateNoticeState.snoozeUntil
    });
  }

  function shouldShowUpdateNotice(version) {
    const now = Date.now();
    if (!version) {
      return false;
    }
    if (updateNoticeState.skippedVersion === version) {
      return false;
    }
    if (updateNoticeState.snoozedVersion === version && now < updateNoticeState.snoozeUntil) {
      return false;
    }
    return true;
  }

  function isAutoUpdateCheckEnabled() {
    const flag = appSettings.value?.updates?.auto_check_enabled;
    if (typeof flag === 'boolean') {
      return flag;
    }
    return true;
  }

  function setUpdateNoticeFromState(currentVersion) {
    const version = updateNoticeState.latestVersion;
    if (!version || !isVersionGreater(version, currentVersion) || !shouldShowUpdateNotice(version)) {
      updateNotice.value = null;
      return;
    }
    updateNotice.value = {
      currentVersion,
      latestVersion: version,
      latestName: updateNoticeState.latestName,
      latestUrl: updateNoticeState.latestUrl
    };
  }

  async function checkForUpdates(options = {}) {
    const { force = false, userInitiated = false } = options;
    if (userInitiated && isCheckingUpdates.value) {
      return;
    }

    if (userInitiated) {
      isCheckingUpdates.value = true;
      updateCheckStatus.value = 'Checking for updates...';
    }

    loadUpdateNoticeState();
    const now = Date.now();
    const recentlyChecked = now - updateNoticeState.lastCheckedAt < UPDATE_CHECK_INTERVAL_MS;

    if (force) {
      updateNoticeState.lastCheckedAt = 0;
      persistUpdateNoticeState();
    }

    try {
      if (!force && recentlyChecked && updateNoticeState.latestVersion) {
        setUpdateNoticeFromState(updateNoticeState.currentVersion);
        if (userInitiated) {
          if (updateNotice.value) {
            updateCheckStatus.value = `Update available: v${updateNotice.value.latestVersion}.`;
          } else {
            updateCheckStatus.value = 'You are already on the latest version.';
          }
        }
        return;
      }

      const response = await fetch(API.updateLatest, {
        cache: force ? 'no-store' : 'default',
        headers: force ? { 'Cache-Control': 'no-cache' } : undefined
      });
      if (!response.ok) {
        if (userInitiated) {
          updateCheckStatus.value = `Update check failed (${response.status}).`;
        }
        return;
      }
      const payload = await response.json();
      const currentVersion = String(payload.current_version || '0.0.0');
      const latestVersion = normalizeVersion(payload.latest_version || '');

      updateNoticeState.currentVersion = currentVersion;
      updateNoticeState.lastCheckedAt = now;
      updateNoticeState.latestVersion = latestVersion;
      updateNoticeState.latestName = String(payload.latest_name || payload.latest_tag || '');
      updateNoticeState.latestUrl = String(payload.latest_url || '');
      persistUpdateNoticeState();

      if (isVersionGreater(latestVersion, currentVersion) && shouldShowUpdateNotice(latestVersion)) {
        updateNotice.value = {
          currentVersion,
          latestVersion,
          latestName: updateNoticeState.latestName,
          latestUrl: updateNoticeState.latestUrl
        };
        if (userInitiated) {
          updateCheckStatus.value = `Update available: v${latestVersion}.`;
        }
      } else {
        updateNotice.value = null;
        if (userInitiated) {
          updateCheckStatus.value = 'You are already on the latest version.';
        }
      }
    } catch {
      // ignore update check failures; app should continue silently
      if (userInitiated) {
        updateCheckStatus.value = 'Update check failed. Please try again.';
      }
    } finally {
      if (userInitiated) {
        isCheckingUpdates.value = false;
      }
    }
  }

  async function checkForUpdatesNow() {
    await checkForUpdates({ force: true, userInitiated: true });
  }

  function openUpdateRelease() {
    if (!updateNotice.value?.latestUrl) {
      return;
    }
    window.open(updateNotice.value.latestUrl, '_blank', 'noopener,noreferrer');
  }

  function snoozeUpdateNotice() {
    if (!updateNotice.value?.latestVersion) {
      return;
    }
    updateNoticeState.snoozedVersion = updateNotice.value.latestVersion;
    updateNoticeState.snoozeUntil = Date.now() + UPDATE_SNOOZE_INTERVAL_MS;
    persistUpdateNoticeState();
    updateNotice.value = null;
  }

  function skipUpdateVersion() {
    if (!updateNotice.value?.latestVersion) {
      return;
    }
    updateNoticeState.skippedVersion = updateNotice.value.latestVersion;
    if (updateNoticeState.snoozedVersion === updateNotice.value.latestVersion) {
      updateNoticeState.snoozedVersion = '';
      updateNoticeState.snoozeUntil = 0;
    }
    persistUpdateNoticeState();
    updateNotice.value = null;
  }

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

  async function copySelectedTagName(tagName = selectedTag.value?.name) {
    if (!tagName) {
      return;
    }
    await copyText(tagName);
    tagCopyStatus.value = 'Copied \u2713';
    tagStatusText.value = `Copied tag "${tagName}".`;
    if (tagCopyStatusTimer) {
      window.clearTimeout(tagCopyStatusTimer);
    }
    tagCopyStatusTimer = window.setTimeout(() => {
      tagCopyStatus.value = '';
      tagCopyStatusTimer = null;
    }, 1400);
  }

  async function copySelectedName() {
    if (activeTab.value === 'tags') {
      await copySelectedTagName();
      return;
    }
    if (!selectedAsset.value?.name) {
      statusText.value = 'Select media before copying a name.';
      return;
    }
    await copyText(selectedAsset.value.name);
    statusText.value = `Copied name "${selectedAsset.value.name}".`;
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
    copySelectedTagName,
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
    tagCopyStatus,
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
    appVersion,
    appRepo,
    appReleasePageUrl,
    isCheckingUpdates,
    updateCheckStatus,
    checkForUpdatesNow,
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
  });

  return {
    activeTab,
    deleteCount,
    isUploading,
    isDeleting,
    safeDelete,
    isDropOverlayVisible,
    isDeleteConfirmVisible,
    isShortcutsModalVisible,
    updateNotice,
    appVersion,
    appRepo,
    appReleasePageUrl,
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
    openUpdateRelease,
    snoozeUpdateNotice,
    skipUpdateVersion,
    hideShortcutsModal,
    showShortcutsModal,
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
