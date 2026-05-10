import { computed, nextTick, onMounted, onUnmounted, reactive, ref, watch } from "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js";
import { API, buildQuery, fileUrl, thumbUrl } from "/vue/api.js";

const FAVORITES_KEY = "bubba_asset_viewer_tag_favorites";
const RECENT_KEY = "bubba_asset_viewer_tag_recent";
const SETTINGS_KEY = "bubba_asset_viewer_settings";
const ALLOWED_UPLOAD_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"]);
const PREVIEWABLE_EXTENSIONS = new Set([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"]);
const METADATA_FILTERS = [
    { key: "bubba_metadata", label: "Bubba" },
    { key: "workflow", label: "Workflow" },
    { key: "parameters", label: "Params" },
    { key: "no_tracked_metadata", label: "No metadata" },
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
        return parsed && typeof parsed === "object" && !Array.isArray(parsed) ? parsed : {};
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
    const raw = String(value || "").trim();
    if (!raw) {
        return [];
    }
    const parts = raw.includes("|") ? raw.split("|") : raw.split(",");
    return parts.map((item) => item.trim()).filter(Boolean);
}

function normalizeTagQuery(value) {
    return String(value || "").trim().toLowerCase().replace(/[\s_-]+/g, "_").replace(/^_+|_+$/g, "");
}

function isTypingTarget(target) {
    const tagName = String(target?.tagName || "").toLowerCase();
    return tagName === "input" || tagName === "textarea" || tagName === "select" || target?.isContentEditable;
}

function fileExtension(name) {
    const match = String(name || "").toLowerCase().match(/\.[^.]+$/);
    return match ? match[0] : "";
}

function isAllowedImageFile(file) {
    if (!file) {
        return false;
    }
    const type = String(file.type || "").toLowerCase();
    if (type.startsWith("image/")) {
        return true;
    }
    return ALLOWED_UPLOAD_EXTENSIONS.has(fileExtension(file.name));
}

function isPreviewableAsset(asset) {
    return PREVIEWABLE_EXTENSIONS.has(String(asset?.extension || "").toLowerCase());
}

function getDensityConfig(density) {
    if (density === "compact") {
        return { minWidth: 150, rowHeight: 228 };
    }
    if (density === "large") {
        return { minWidth: 220, rowHeight: 318 };
    }
    return { minWidth: 180, rowHeight: 270 };
}

function formatBytes(bytes) {
    const value = Number(bytes || 0);
    if (!Number.isFinite(value) || value <= 0) {
        return "0 B";
    }
    const units = ["B", "KB", "MB", "GB"];
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
    const activeTab = ref(["assets", "tags", "duplicates", "stats", "settings"].includes(savedSettings.activeTab) ? savedSettings.activeTab : "assets");
    const roots = ref([]);
    const assets = ref([]);
    const selectedAsset = ref(null);
    const selectedPath = ref("");
    const selectedPaths = ref(new Set());
    const lastSelectedIndex = ref(-1);
    const lastSelectedDuplicateIndex = ref(-1);
    const details = ref(null);
    const statusText = ref("Loading roots...");
    const isLoading = ref(false);
    const isLoadingMore = ref(false);
    const isUploading = ref(false);
    const isDeleting = ref(false);
    const safeDelete = ref(true);
    const hasMore = ref(false);
    const blurThumbnails = ref(false);
    const detailsWidth = ref(420);
    const previewHeight = ref(320);
    const isDropOverlayVisible = ref(false);
    const isDeleteConfirmVisible = ref(false);

    const assetListRef = ref(null);
    const searchInputRef = ref(null);
    const assetScrollTop = ref(0);
    const assetViewportHeight = ref(0);
    const assetListWidth = ref(0);

    const tags = ref([]);
    const tagCategoriesList = ref([]);
    const selectedTag = ref(null);
    const tagStatusText = ref("Open Tag Browser to load local CSV...");
    const isLoadingTags = ref(false);
    const tagExamplesLoading = ref(false);
    const tagExamples = ref({});
    const hasLoadedTags = ref(false);
    const tagTotal = ref(0);
    const tagOffset = ref(0);
    const tagPageSize = 300;
    let tagSearchTimer = null;

    const duplicateGroups = ref([]);
    const duplicateSummary = ref(null);
    const duplicateStatusText = ref("Run a duplicate scan for the selected folder.");
    const duplicateIncludeNear = ref(Boolean(savedSettings.duplicateIncludeNear));
    const duplicateNearThreshold = ref(Number.isFinite(Number(savedSettings.duplicateNearThreshold)) ? Number(savedSettings.duplicateNearThreshold) : 6);
    const isScanningDuplicates = ref(false);
    const duplicateScanProgress = ref(0);
    const duplicateScanPhase = ref("");
    const compareLeft = ref(null);
    const compareRight = ref(null);
    const compareSlider = ref(50);
    const compareStageRef = ref(null);
    const isCompareDragging = ref(false);
    const metadataHealth = ref(null);
    const metadataHealthStatus = ref("Metadata report not loaded.");
    const isLoadingMetadataHealth = ref(false);
    const folderStats = ref(null);
    const folderStatsStatus = ref("Folder stats not loaded.");
    const isLoadingFolderStats = ref(false);
    const rootStatsReports = reactive({});
    const appSettings = ref(null);
    const appSettingsSchema = ref(null);
    const settingsStatus = ref("Settings not loaded.");
    const isLoadingSettings = ref(false);
    const isSavingSettings = ref(false);
    const settingsListDrafts = reactive({});

    const favoriteTagNames = ref(new Set(loadArrayFromStorage(FAVORITES_KEY)));
    const recentTagNames = ref(loadArrayFromStorage(RECENT_KEY));

    const pageSize = 120;
    const offset = ref(0);
    let searchTimer = null;
    let resizeObserver = null;
    const cleanupCallbacks = [];

    const filters = reactive({
        root: String(savedSettings.root || ""),
        q: "",
        ext: "",
        metadataBadge: "",
        sortBy: ["name", "modified", "size", "metadata"].includes(savedSettings.sortBy) ? savedSettings.sortBy : "modified",
        sortDir: ["asc", "desc"].includes(savedSettings.sortDir) ? savedSettings.sortDir : "desc",
        density: "comfortable",
    });

    const tagFilters = reactive({
        q: "",
        category: "",
        view: "all",
    });

    const densityClass = computed(() => `density-${filters.density}`);
    const densityConfig = computed(() => getDensityConfig(filters.density));
    const layoutStyle = computed(() => ({
        "--details-width": `${detailsWidth.value}px`,
        "--preview-height": `${previewHeight.value}px`,
    }));
    const assetListStyle = computed(() => ({
        "--asset-min-col-width": `${densityConfig.value.minWidth}px`,
    }));
    const selectedCount = computed(() => selectedPaths.value.size);
    const deleteCount = computed(() => selectedPaths.value.size || (selectedPath.value ? 1 : 0));
    const currentRootLabel = computed(() => {
        const root = roots.value.find((item) => item.key === filters.root);
        return root?.label || root?.key || filters.root || "selected folder";
    });

    const shouldVirtualize = computed(() => assets.value.length > 240);
    const virtualColumnCount = computed(() => {
        if (!shouldVirtualize.value) {
            return 1;
        }
        const width = Math.max(1, assetListWidth.value || assetListRef.value?.clientWidth || 1);
        return Math.max(1, Math.floor(width / densityConfig.value.minWidth));
    });
    const virtualRowHeight = computed(() => densityConfig.value.rowHeight);
    const virtualRowCount = computed(() => Math.ceil(assets.value.length / virtualColumnCount.value));
    const virtualStartRow = computed(() => Math.max(0, Math.floor(assetScrollTop.value / virtualRowHeight.value) - 2));
    const virtualVisibleRows = computed(() => Math.ceil((assetViewportHeight.value || 1) / virtualRowHeight.value) + 5);
    const virtualStartIndex = computed(() => virtualStartRow.value * virtualColumnCount.value);
    const virtualEndIndex = computed(() => Math.min(assets.value.length, (virtualStartRow.value + virtualVisibleRows.value) * virtualColumnCount.value));
    const visibleAssets = computed(() => {
        if (!shouldVirtualize.value) {
            return assets.value;
        }
        return assets.value.slice(virtualStartIndex.value, virtualEndIndex.value);
    });
    const duplicateAssets = computed(() => {
        return duplicateGroups.value.flatMap((group) => Array.isArray(group.assets) ? group.assets : []);
    });
    const virtualSpacerStyle = computed(() => ({ height: `${virtualRowCount.value * virtualRowHeight.value}px` }));
    const virtualWindowStyle = computed(() => ({
        transform: `translateY(${virtualStartRow.value * virtualRowHeight.value}px)`,
        gridTemplateColumns: `repeat(${virtualColumnCount.value}, minmax(0, 1fr))`,
    }));

    const tagCategories = computed(() => {
        return tagCategoriesList.value;
    });

    const filteredTags = computed(() => {
        const q = normalizeTagQuery(tagFilters.q);

        return tags.value.filter((tag) => {
            if (tagFilters.view === "favorites" && !favoriteTagNames.value.has(tag.name)) {
                return false;
            }
            if (tagFilters.view === "recent" && !recentTagNames.value.includes(tag.name)) {
                return false;
            }
            if (!q) {
                return true;
            }
            return normalizeTagQuery(`${tag.name} ${tag.aliases}`).includes(q);
        });
    });

    const visibleTags = computed(() => filteredTags.value);
    const tagHasMore = computed(() => tagFilters.view === "all" && tags.value.length < tagTotal.value);
    const tagCountText = computed(() => `Showing ${visibleTags.value.length} of ${tagTotal.value} tag(s)`);
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
    const metadataFilterList = computed(() => METADATA_FILTERS);
    const selectedTagAliases = computed(() => parseAliases(selectedTag.value?.aliases));
    const folderStatsSummary = computed(() => {
        if (!folderStats.value) {
            return [];
        }
        return [
            `Files ${folderStats.value.total_files || 0}`,
            `Size ${formatBytes(folderStats.value.total_bytes || 0)}`,
            `Images ${folderStats.value.image_files || 0}`,
            `Bubba ${folderStats.value.bubba_metadata || 0}`,
            `Workflow ${folderStats.value.workflow || 0}`,
            `Params ${folderStats.value.parameters || 0}`,
            `Missing ${folderStats.value.no_tracked_metadata || 0}`,
        ];
    });
    const folderStatsMetrics = computed(() => {
        return buildFolderStatsMetrics(folderStats.value);
    });
    const metadataStatsMetrics = computed(() => {
        const source = metadataHealth.value || folderStats.value;
        return buildMetadataStatsMetrics(source);
    });
    const statsPrimaryCount = computed(() => {
        const source = metadataHealth.value || folderStats.value;
        if (!source) {
            return 0;
        }
        return source.total_assets || source.png_assets || source.image_files || source.total_files || 0;
    });
    const statsRootReports = computed(() => roots.value.map((root) => {
        const state = statsStateForRoot(root);
        const metadataSource = state.metadataHealth || state.folderStats;
        return {
            key: root.key,
            label: root.label || root.key,
            folderStats: state.folderStats,
            metadataHealth: state.metadataHealth,
            folderStatsStatus: state.folderStatsStatus,
            metadataHealthStatus: state.metadataHealthStatus,
            isLoadingFolderStats: state.isLoadingFolderStats,
            isLoadingMetadataHealth: state.isLoadingMetadataHealth,
            folderMetrics: buildFolderStatsMetrics(state.folderStats),
            metadataMetrics: buildMetadataStatsMetrics(metadataSource),
        };
    }));
    const isLoadingAnyFolderStats = computed(() => statsRootReports.value.some((report) => report.isLoadingFolderStats));
    const isLoadingAnyMetadataHealth = computed(() => statsRootReports.value.some((report) => report.isLoadingMetadataHealth));
    const settingsSections = computed(() => {
        const schema = appSettingsSchema.value;
        if (!schema || typeof schema !== "object") {
            return [];
        }
        const rootProperties = schema.properties || {};
        return Object.entries(rootProperties).map(([sectionKey, sectionSchema]) => {
            const resolvedSection = resolveSettingsSchemaRef(sectionSchema);
            const fields = Object.entries(resolvedSection.properties || {}).map(([fieldKey, fieldSchema]) => {
                const resolvedField = resolveSettingsSchemaRef(fieldSchema);
                return {
                    key: fieldKey,
                    label: resolvedField.title || titleCaseSettingKey(fieldKey),
                    type: settingsInputType(resolvedField),
                    description: resolvedField.description || "",
                    options: Array.isArray(resolvedField.enum) ? resolvedField.enum.map((value) => ({ value, label: titleCaseSettingKey(value) })) : [],
                };
            });
            return {
                key: sectionKey,
                label: sectionSchema.title || resolvedSection.title || titleCaseSettingKey(sectionKey),
                fields,
            };
        });
    });
    const selectedTagExamples = computed(() => {
        if (!selectedTag.value) {
            return [];
        }
        const examples = tagExamples.value[selectedTag.value.name] || {};
        return Object.entries(examples)
            .map(([site, value]) => ({
                site,
                score: typeof value?.score === "number" ? value.score : null,
                image_url: value?.image_url || "",
                page_url: value?.page_url || value?.post_url || "",
            }))
            .filter((item) => item.image_url || item.page_url);
    });

    function measureAssetList() {
        const element = assetListRef.value;
        if (!element) {
            return;
        }
        assetViewportHeight.value = element.clientHeight;
        assetListWidth.value = element.clientWidth;
        assetScrollTop.value = element.scrollTop;
    }

    function onAssetListScroll() {
        assetScrollTop.value = assetListRef.value?.scrollTop || 0;
    }

    function selectedPathSetHas(path) {
        return selectedPaths.value.has(path);
    }

    function replaceSelectedPaths(paths) {
        selectedPaths.value = new Set(paths.filter(Boolean));
    }

    function blurActionButton(event) {
        event?.currentTarget?.blur?.();
    }

    function findAssetByPath(path, source = "all") {
        if (!path) {
            return null;
        }
        if (source !== "duplicates") {
            const asset = assets.value.find((item) => item.path === path);
            if (asset) {
                return asset;
            }
        }
        if (source !== "assets") {
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
            filters.root = "";
        }
        if (!filters.root && roots.value.length > 0) {
            filters.root = roots.value[0].key;
        }
    }

    function applySettings(settings) {
        if (!settings || typeof settings !== "object") {
            return;
        }
        appSettings.value = settings;
        const viewer = settings.viewer || {};
        if (["compact", "comfortable", "large"].includes(viewer.density)) {
            filters.density = viewer.density;
        }
        blurThumbnails.value = Boolean(viewer.preview);
    }

    function resolveSettingsSchemaRef(schema) {
        if (!schema || typeof schema !== "object") {
            return {};
        }
        if (schema.$ref && appSettingsSchema.value?.$defs) {
            const refName = String(schema.$ref).replace("#/$defs/", "");
            return appSettingsSchema.value.$defs[refName] || schema;
        }
        return schema;
    }

    function titleCaseSettingKey(key) {
        return String(key || "")
            .replace(/[_-]+/g, " ")
            .replace(/\b\w/g, (letter) => letter.toUpperCase());
    }

    function formatNumber(value) {
        return Number(value || 0).toLocaleString();
    }

    function metadataCoveragePercent(value, source) {
        const denominator = source?.total_assets || source?.png_assets || source?.image_files || source?.total_files || 0;
        if (!denominator) {
            return 0;
        }
        return Math.max(0, Math.min(100, Math.round((Number(value || 0) / denominator) * 100)));
    }

    function buildFolderStatsMetrics(stats) {
        if (!stats) {
            return [];
        }
        return [
            { key: "files", label: "Files", value: formatNumber(stats.total_files || 0), note: "All files" },
            { key: "size", label: "Storage", value: formatBytes(stats.total_bytes || 0), note: "Total size" },
            { key: "images", label: "Images", value: formatNumber(stats.image_files || 0), note: "Previewable files" },
            { key: "other", label: "Other", value: formatNumber(stats.other_files || 0), note: "Everything else" },
        ];
    }

    function buildMetadataStatsMetrics(source) {
        if (!source) {
            return [];
        }
        return [
            { key: "bubba", label: "Bubba", value: source.bubba_metadata || 0 },
            { key: "workflow", label: "Workflow", value: source.workflow || 0 },
            { key: "parameters", label: "Params", value: source.parameters || 0 },
            { key: "missing", label: "Missing", value: source.no_tracked_metadata || 0 },
            { key: "invalid", label: "Invalid", value: source.invalid_bubba_metadata || 0 },
        ].map((item) => ({
            ...item,
            valueLabel: formatNumber(item.value),
            percent: metadataCoveragePercent(item.value, source),
        }));
    }

    function defaultRootStatsState() {
        return {
            folderStats: null,
            metadataHealth: null,
            folderStatsStatus: "Folder stats not loaded.",
            metadataHealthStatus: "Metadata report not loaded.",
            isLoadingFolderStats: false,
            isLoadingMetadataHealth: false,
        };
    }

    function statsStateForRoot(root) {
        const key = root?.key || "";
        if (!key) {
            return defaultRootStatsState();
        }
        if (!rootStatsReports[key]) {
            rootStatsReports[key] = defaultRootStatsState();
        }
        return rootStatsReports[key];
    }

    function settingsInputType(schema) {
        if (Array.isArray(schema.enum)) {
            return "select";
        }
        if (schema.type === "boolean") {
            return "boolean";
        }
        if (schema.type === "array" && schema.items?.type === "string") {
            return "string_list";
        }
        return "text";
    }

    async function fetchSettings() {
        isLoadingSettings.value = true;
        settingsStatus.value = "Loading settings...";
        try {
            const response = await fetch(API.settings);
            if (!response.ok) {
                throw new Error(`Failed to load settings (${response.status})`);
            }
            const payload = await response.json();
            appSettingsSchema.value = payload.schema && typeof payload.schema === "object" ? payload.schema : null;
            applySettings(payload.settings);
            settingsStatus.value = "Settings loaded.";
        } catch (error) {
            console.error(error);
            settingsStatus.value = error?.message || "Settings failed to load.";
        } finally {
            isLoadingSettings.value = false;
        }
    }

    function settingsFieldValue(sectionKey, fieldKey) {
        return appSettings.value?.[sectionKey]?.[fieldKey];
    }

    function settingsListValue(sectionKey, fieldKey) {
        const value = settingsFieldValue(sectionKey, fieldKey);
        return Array.isArray(value) ? value : [];
    }

    function settingsListDraftKey(sectionKey, fieldKey) {
        return `${sectionKey}.${fieldKey}`;
    }

    function settingsListDraftValue(sectionKey, fieldKey) {
        return settingsListDrafts[settingsListDraftKey(sectionKey, fieldKey)] || "";
    }

    function updateSettingsListDraft(sectionKey, fieldKey, value) {
        settingsListDrafts[settingsListDraftKey(sectionKey, fieldKey)] = value;
    }

    async function saveSettings(nextSettings) {
        isSavingSettings.value = true;
        settingsStatus.value = "Saving settings...";
        try {
            const response = await fetch(API.settings, {
                method: "PUT",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(nextSettings),
            });
            if (!response.ok) {
                throw new Error(`Failed to save settings (${response.status})`);
            }
            const payload = await response.json();
            appSettingsSchema.value = payload.schema && typeof payload.schema === "object" ? payload.schema : null;
            applySettings(payload.settings);
            if (Array.isArray(payload.roots)) {
                roots.value = payload.roots;
                if (filters.root && !roots.value.some((root) => root.key === filters.root)) {
                    filters.root = roots.value[0]?.key || "";
                }
            }
            settingsStatus.value = "Settings saved.";
        } catch (error) {
            console.error(error);
            settingsStatus.value = error?.message || "Settings failed to save.";
        } finally {
            isSavingSettings.value = false;
        }
    }

    function cloneSettingsPayload() {
        return JSON.parse(JSON.stringify(appSettings.value || {}));
    }

    function updateSetting(sectionKey, fieldKey, value) {
        const nextSettings = cloneSettingsPayload();
        nextSettings[sectionKey] = nextSettings[sectionKey] && typeof nextSettings[sectionKey] === "object" ? nextSettings[sectionKey] : {};
        nextSettings[sectionKey][fieldKey] = value;
        saveSettings(nextSettings);
    }

    function updateStringListItem(sectionKey, fieldKey, index, value) {
        const nextValue = [...settingsListValue(sectionKey, fieldKey)];
        const cleanedValue = String(value || "").trim();
        if (cleanedValue) {
            nextValue[index] = cleanedValue;
        } else {
            nextValue.splice(index, 1);
        }
        updateSetting(sectionKey, fieldKey, nextValue);
    }

    function addStringListSetting(sectionKey, fieldKey) {
        const draftKey = settingsListDraftKey(sectionKey, fieldKey);
        const nextItem = String(settingsListDrafts[draftKey] || "").trim();
        if (!nextItem) {
            return;
        }
        updateSetting(sectionKey, fieldKey, [...settingsListValue(sectionKey, fieldKey), nextItem]);
        settingsListDrafts[draftKey] = "";
    }

    function removeStringListItem(sectionKey, fieldKey, index) {
        const nextValue = [...settingsListValue(sectionKey, fieldKey)];
        nextValue.splice(index, 1);
        updateSetting(sectionKey, fieldKey, nextValue);
    }

    async function fetchAssets({ append = false, keepSelection = false } = {}) {
        if (!filters.root) {
            assets.value = [];
            return;
        }

        if (append) {
            isLoadingMore.value = true;
        } else {
            isLoading.value = true;
            statusText.value = "Loading media...";
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
                offset: offset.value,
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
                selectedPath.value = "";
                details.value = null;
                replaceSelectedPaths([]);
                lastSelectedIndex.value = -1;
            }

            if (keepSelection && selectedPath.value) {
                const refreshed = assets.value.find((asset) => asset.path === selectedPath.value);
                selectedAsset.value = refreshed || null;
                if (!refreshed) {
                    selectedPath.value = "";
                    details.value = null;
                }
            }

            await nextTick();
            measureAssetList();
        } catch (error) {
            console.error(error);
            statusText.value = error?.message || "Failed to load media.";
        } finally {
            isLoading.value = false;
            isLoadingMore.value = false;
        }
    }

    async function fetchTags({ append = false } = {}) {
        isLoadingTags.value = true;
        tagStatusText.value = append ? "Loading more tags..." : "Loading tags...";

        try {
            const nextOffset = append ? tagOffset.value : 0;
            const response = await fetch(buildQuery(API.tags, {
                q: tagFilters.q,
                category: tagFilters.category,
                limit: tagPageSize,
                offset: nextOffset,
            }));
            if (!response.ok) {
                throw new Error(`Failed to load tags (${response.status})`);
            }

            const payload = await response.json();
            const incoming = Array.isArray(payload.tags) ? payload.tags : [];
            const normalizedIncoming = incoming.map((tag) => ({
                name: String(tag.name || ""),
                category: String(tag.category || ""),
                count: Number(tag.count || 0),
                aliases: String(tag.aliases || ""),
            }));
            tags.value = append ? tags.value.concat(normalizedIncoming) : normalizedIncoming;
            tagOffset.value = tags.value.length;
            tagTotal.value = Number(payload.total || tags.value.length);
            tagCategoriesList.value = Array.isArray(payload.categories) ? payload.categories.map(String) : tagCategoriesList.value;

            hasLoadedTags.value = true;
            tagStatusText.value = `Loaded ${tags.value.length} of ${tagTotal.value} tag(s).`;

            if (selectedTag.value) {
                const refreshed = tags.value.find((tag) => tag.name === selectedTag.value.name);
                selectedTag.value = refreshed || null;
            }
        } catch (error) {
            console.error(error);
            tagStatusText.value = error?.message || "Failed to load tags.";
        } finally {
            isLoadingTags.value = false;
        }
    }

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

    function metadataBadges(asset) {
        return Array.isArray(asset?.metadata_badges) ? asset.metadata_badges : [];
    }

    async function fetchRootMetadataHealth(root, { refresh = true, cacheOnly = false } = {}) {
        if (!root?.key) {
            return;
        }
        const state = statsStateForRoot(root);
        state.isLoadingMetadataHealth = true;
        state.metadataHealthStatus = "Loading metadata report...";
        try {
            const response = await fetch(buildQuery(API.metadataHealth, { root: root.key, refresh, cache_only: cacheOnly }));
            if (!response.ok) {
                throw new Error(`Metadata report failed (${response.status})`);
            }
            const payload = await response.json();
            state.metadataHealth = payload.stats || null;
            if (payload.stats) {
                state.metadataHealthStatus = payload.cached ? "Loaded cached metadata report." : "Metadata report loaded.";
            } else {
                state.metadataHealthStatus = "Metadata report not loaded.";
            }
        } catch (error) {
            console.error(error);
            state.metadataHealth = null;
            state.metadataHealthStatus = error?.message || "Metadata report failed.";
        } finally {
            state.isLoadingMetadataHealth = false;
        }
    }

    async function fetchMetadataHealth(options = {}) {
        const targets = roots.value.length ? roots.value : filters.root ? [{ key: filters.root, label: filters.root }] : [];
        if (!targets.length) {
            metadataHealthStatus.value = "Select a folder before loading metadata report.";
            return;
        }
        isLoadingMetadataHealth.value = true;
        await Promise.all(targets.map((root) => fetchRootMetadataHealth(root, options)));
        metadataHealth.value = statsStateForRoot(targets[0]).metadataHealth;
        metadataHealthStatus.value = "Metadata reports loaded.";
        isLoadingMetadataHealth.value = false;
    }

    async function fetchRootFolderStats(root, { refresh = false } = {}) {
        if (!root?.key) {
            return;
        }
        const state = statsStateForRoot(root);
        state.isLoadingFolderStats = true;
        state.folderStatsStatus = "Loading folder stats...";
        try {
            const response = await fetch(buildQuery(API.stats, { root: root.key, refresh }));
            if (!response.ok) {
                throw new Error(`Folder stats failed (${response.status})`);
            }
            const payload = await response.json();
            state.folderStats = payload.stats || null;
            state.folderStatsStatus = payload.cached ? "Loaded cached folder stats." : "Folder stats loaded.";
        } catch (error) {
            console.error(error);
            state.folderStats = null;
            state.folderStatsStatus = error?.message || "Folder stats failed.";
        } finally {
            state.isLoadingFolderStats = false;
        }
    }

    async function fetchFolderStats(options = {}) {
        const targets = roots.value.length ? roots.value : filters.root ? [{ key: filters.root, label: filters.root }] : [];
        if (!targets.length) {
            folderStatsStatus.value = "Select a folder before loading folder stats.";
            return;
        }
        isLoadingFolderStats.value = true;
        await Promise.all(targets.map((root) => fetchRootFolderStats(root, options)));
        folderStats.value = statsStateForRoot(targets[0]).folderStats;
        folderStatsStatus.value = "Folder stats loaded.";
        isLoadingFolderStats.value = false;
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

    function isTagFavorite(tagName) {
        return favoriteTagNames.value.has(tagName);
    }

    function persistFavorites() {
        saveArrayToStorage(FAVORITES_KEY, Array.from(favoriteTagNames.value));
    }

    function persistRecent() {
        saveArrayToStorage(RECENT_KEY, recentTagNames.value);
    }

    function toggleTagFavorite(tag) {
        if (!tag?.name) {
            return;
        }

        const next = new Set(favoriteTagNames.value);
        if (next.has(tag.name)) {
            next.delete(tag.name);
        } else {
            next.add(tag.name);
        }

        favoriteTagNames.value = next;
        persistFavorites();
    }

    function loadMoreTags() {
        if (!tagHasMore.value || isLoadingTags.value) {
            return;
        }
        fetchTags({ append: true });
    }

    function startDetailsResize(event) {
        if (event.button !== 0) {
            return;
        }

        const startX = event.clientX;
        const startWidth = detailsWidth.value;

        function onMove(moveEvent) {
            const delta = startX - moveEvent.clientX;
            detailsWidth.value = Math.max(320, Math.min(900, startWidth + delta));
        }

        function onUp() {
            document.body.classList.remove("panel-resizing");
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
        }

        document.body.classList.add("panel-resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    }

    function startPreviewResize(event) {
        if (event.button !== 0) {
            return;
        }
        event.preventDefault();

        const startY = event.clientY;
        const startHeight = previewHeight.value;

        function onMove(moveEvent) {
            const delta = moveEvent.clientY - startY;
            previewHeight.value = Math.max(140, Math.min(720, startHeight + delta));
        }

        function onUp() {
            document.body.classList.remove("preview-resizing");
            document.removeEventListener("mousemove", onMove);
            document.removeEventListener("mouseup", onUp);
        }

        document.body.classList.add("preview-resizing");
        document.addEventListener("mousemove", onMove);
        document.addEventListener("mouseup", onUp);
    }

    async function fetchTagExamples(tagName) {
        if (!tagName) {
            return;
        }

        tagExamplesLoading.value = true;
        try {
            const url = buildQuery(API.tagExamples, { tag: tagName });
            const response = await fetch(url);
            if (!response.ok) {
                throw new Error(`Failed to load examples (${response.status})`);
            }
            const payload = await response.json();
            tagExamples.value = {
                ...tagExamples.value,
                [tagName]: payload.examples && typeof payload.examples === "object" ? payload.examples : {},
            };
        } catch (error) {
            console.error(error);
        } finally {
            tagExamplesLoading.value = false;
        }
    }

    async function selectTag(tag) {
        selectedTag.value = tag;
        recentTagNames.value = [tag.name, ...recentTagNames.value.filter((name) => name !== tag.name)].slice(0, 50);
        persistRecent();
        await fetchTagExamples(tag.name);
    }

    function exampleImageUrl(url) {
        return buildQuery(API.tagExampleImage, { url });
    }

    function tagSearchUrl(tagName, site) {
        if (site === "danbooru") {
            return `https://danbooru.donmai.us/posts?tags=${encodeURIComponent(tagName)}`;
        }
        return `https://e621.net/posts?tags=${encodeURIComponent(tagName)}`;
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

    function requestDeleteSelected(event = null) {
        if (!deleteCount.value || isDeleting.value) {
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
        const paths = Array.from(selectedPaths.value.size ? selectedPaths.value : new Set([selectedPath.value])).filter(Boolean);
        if (!paths.length) {
            return;
        }

        const shouldSafeDelete = safeDeleteOverride === null ? safeDelete.value : Boolean(safeDeleteOverride);
        isDeleting.value = true;
        isDeleteConfirmVisible.value = false;
        statusText.value = skipConfirm && !shouldSafeDelete
            ? `Permanently deleting ${paths.length} media item(s)...`
            : `Deleting ${paths.length} media item(s)...`;

        try {
            const response = await fetch(API.delete, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ root: filters.root, paths, safe_delete: shouldSafeDelete }),
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
            const hasNewSelection = selectionAfterDelete.length > 0 || (selectedPath.value && !deletedPathSet.has(selectedPath.value));
            removePathsFromDuplicateGroups(deletedPaths);
            assets.value = assets.value.filter((asset) => !deletedPathSet.has(asset.path));
            if (hasNewSelection) {
                replaceSelectedPaths(selectionAfterDelete);
                if (!selectedPath.value || deletedPathSet.has(selectedPath.value)) {
                    selectedPath.value = selectionAfterDelete[0] || "";
                    selectedAsset.value = findAssetByPath(selectedPath.value);
                }
            } else {
                replaceSelectedPaths([]);
                selectedAsset.value = null;
                selectedPath.value = "";
                details.value = null;
                lastSelectedIndex.value = -1;
                lastSelectedDuplicateIndex.value = -1;
            }
            if (activeTab.value !== "duplicates") {
                await refreshAssets({ keepSelection: hasNewSelection });
            }
            const deleteVerb = shouldSafeDelete ? "Deleted" : "Permanently deleted";
            statusText.value = errors ? `${deleteVerb} ${deleted}; ${errors} failed.` : `${deleteVerb} ${deleted} media item(s).`;
            if (activeTab.value === "duplicates") {
                duplicateStatusText.value = hasNewSelection
                    ? `${selectedPaths.value.size} selected`
                    : errors ? `${deleteVerb} ${deleted}; ${errors} failed.` : `${deleteVerb} ${deleted} duplicate media item(s).`;
            }
        } catch (error) {
            console.error(error);
            statusText.value = error?.message || "Delete failed.";
        } finally {
            isDeleting.value = false;
        }
    }

    async function uploadFiles(files) {
        if (!filters.root) {
            statusText.value = "Select a folder before uploading.";
            return;
        }

        const allowedFiles = Array.from(files || []).filter(isAllowedImageFile);
        if (!allowedFiles.length) {
            statusText.value = "Only image files can be uploaded.";
            return;
        }

        const form = new FormData();
        for (const file of allowedFiles) {
            form.append("files", file, file.name || "upload.png");
        }

        isUploading.value = true;
        statusText.value = `Uploading ${allowedFiles.length} image(s) to ${currentRootLabel.value}...`;

        try {
            const response = await fetch(buildQuery(API.upload, { root: filters.root }), {
                method: "POST",
                body: form,
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
                await selectAsset(refreshed);
            }
            statusText.value = `Uploaded ${uploaded.length} image(s)${skipped ? `; ${skipped} skipped` : ""}.`;
        } catch (error) {
            console.error(error);
            statusText.value = error?.message || "Upload failed.";
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
            return items.some((item) => item?.kind === "file" && (String(item.type || "").toLowerCase().startsWith("image/") || isAllowedImageFile(item.getAsFile?.())));
        }
        return Array.from(dataTransfer.files || []).some(isAllowedImageFile);
    }

    function hideDropOverlay() {
        isDropOverlayVisible.value = false;
        document.body.classList.remove("drag-upload-active");
    }

    function showDropOverlay() {
        isDropOverlayVisible.value = true;
        document.body.classList.add("drag-upload-active");
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
        event.dataTransfer.dropEffect = "copy";
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
        const card = element.querySelectorAll(".asset-card")[index];
        card?.scrollIntoView({ block: "nearest" });
    }

    function openSelectedAssetFull() {
        if (!selectedPath.value) {
            return;
        }
        window.open(fileUrl(selectedPath.value), "_blank", "noopener,noreferrer");
    }

    async function openContainingFolder(asset = selectedAsset.value) {
        if (!asset?.path) {
            return;
        }
        try {
            const response = await fetch(API.openFolder, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: asset.path }),
            });
            if (!response.ok) {
                throw new Error(`Open folder failed (${response.status})`);
            }
            statusText.value = "Opened containing folder.";
        } catch (error) {
            console.error(error);
            statusText.value = error?.message || "Open folder failed.";
        }
    }

    async function repairSelectedMetadata(asset = selectedAsset.value) {
        if (!asset?.path) {
            return;
        }
        statusText.value = "Repairing metadata...";
        try {
            const response = await fetch(API.repairMetadata, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ path: asset.path }),
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
            statusText.value = payload.result?.repaired ? "Bubba Metadata repaired." : (payload.result?.reason || "Bubba Metadata already repaired.");
        } catch (error) {
            console.error(error);
            statusText.value = error?.message || "Metadata repair failed.";
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
        const paths = Array.from(selectedPaths.value.size ? selectedPaths.value : new Set(selectedPath.value ? [selectedPath.value] : []));
        return paths.map((path) => findAssetByPath(path)).filter(Boolean);
    }

    function downloadTextFile(filename, content, type = "application/json") {
        const blob = new Blob([content], { type });
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = filename;
        document.body.appendChild(link);
        link.click();
        link.remove();
        URL.revokeObjectURL(url);
    }

    function csvEscape(value) {
        const text = String(value ?? "");
        return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
    }

    async function copySelectedPaths() {
        const assetsToCopy = selectedExportAssets();
        await copyText(assetsToCopy.map((asset) => asset.path).join("\n"));
        statusText.value = `Copied ${assetsToCopy.length} path(s).`;
        if (activeTab.value === "duplicates") {
            duplicateStatusText.value = `Copied ${assetsToCopy.length} path(s).`;
        }
    }

    function exportSelectedAssets(format = "json") {
        const rows = selectedExportAssets();
        if (!rows.length) {
            return;
        }
        if (format === "csv") {
            const header = ["name", "path", "relative_path", "extension", "size_bytes", "modified_ts"];
            const body = rows.map((asset) => header.map((key) => csvEscape(asset[key])).join(","));
            downloadTextFile("asset-selection.csv", [header.join(","), ...body].join("\n"), "text/csv");
            return;
        }
        downloadTextFile("asset-selection.json", JSON.stringify(rows, null, 2));
    }

    function exportDuplicateGroups(format = "json") {
        if (!duplicateGroups.value.length) {
            return;
        }
        if (format === "csv") {
            const header = ["group_kind", "group_key", "name", "path", "relative_path", "size_bytes", "modified_ts"];
            const rows = duplicateGroups.value.flatMap((group) => {
                return (group.assets || []).map((asset) => [
                    group.kind,
                    group.key,
                    asset.name,
                    asset.path,
                    asset.relative_path,
                    asset.size_bytes,
                    asset.modified_ts,
                ].map(csvEscape).join(","));
            });
            downloadTextFile("duplicate-groups.csv", [header.join(","), ...rows].join("\n"), "text/csv");
            return;
        }
        downloadTextFile("duplicate-groups.json", JSON.stringify({ summary: duplicateSummary.value, groups: duplicateGroups.value }, null, 2));
    }

    function exportMetadataHealth(format = "json", report = metadataHealth.value, rootLabel = "metadata") {
        if (!report) {
            return;
        }
        const safeLabel = String(rootLabel || "metadata").replace(/[^a-z0-9_-]+/gi, "-").replace(/^-+|-+$/g, "") || "metadata";
        if (format === "csv") {
            const rows = Object.entries(report).map(([key, value]) => `${csvEscape(key)},${csvEscape(value)}`);
            downloadTextFile(`${safeLabel}-metadata-health.csv`, ["metric,value", ...rows].join("\n"), "text/csv");
            return;
        }
        downloadTextFile(`${safeLabel}-metadata-health.json`, JSON.stringify(report, null, 2));
    }

    function onDocumentKeydown(event) {
        if (event.defaultPrevented || isTypingTarget(event.target)) {
            return;
        }

        if (event.key === "Escape") {
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

        const key = String(event.key || "").toLowerCase();
        const isCommandKey = Boolean(event.ctrlKey || event.metaKey);

        if (key === "shift" || key === "control" || key === "alt" || key === "meta") {
            return;
        }

        if (isCommandKey && key === "a" && (activeTab.value === "assets" || activeTab.value === "duplicates")) {
            event.preventDefault();
            selectAllCurrentItems();
            return;
        }

        if (isCommandKey && key === "c" && selectedPaths.value.size > 0) {
            event.preventDefault();
            copyText(Array.from(selectedPaths.value).join("\n"));
            return;
        }

        if (isCommandKey && key === "f" && activeTab.value === "assets") {
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

        if (key === "/" && activeTab.value === "assets") {
            event.preventDefault();
            searchInputRef.value?.focus();
            searchInputRef.value?.select();
            return;
        }

        if (activeTab.value !== "assets" && activeTab.value !== "duplicates") {
            return;
        }

        const rowStep = activeTab.value === "assets" ? Math.max(1, virtualColumnCount.value) : 1;
        if (event.key === "ArrowDown") {
            event.preventDefault();
            stepSelectedAsset(rowStep, { extend: event.shiftKey });
            return;
        }
        if (event.key === "ArrowUp") {
            event.preventDefault();
            stepSelectedAsset(-rowStep, { extend: event.shiftKey });
            return;
        }
        if (event.key === "ArrowRight") {
            event.preventDefault();
            stepSelectedAsset(1, { extend: event.shiftKey });
            return;
        }
        if (event.key === "ArrowLeft") {
            event.preventDefault();
            stepSelectedAsset(-1, { extend: event.shiftKey });
            return;
        }
        if (event.key === "Enter" && activeTab.value === "assets") {
            event.preventDefault();
            openSelectedAssetFull();
            return;
        }
        if (event.key === " " && selectedPath.value) {
            event.preventDefault();
            if (selectedPaths.value.has(selectedPath.value) && selectedPaths.value.size === 1) {
                replaceSelectedPaths([]);
            } else {
                replaceSelectedPaths([selectedPath.value]);
            }
            updateSelectionStatus();
            if (activeTab.value === "duplicates") {
                duplicateStatusText.value = selectedPaths.value.size ? `${selectedPaths.value.size} selected` : "Selection cleared.";
            }
            return;
        }
        if ((event.key === "Delete" || event.key === "Backspace") && deleteCount.value > 0) {
            event.preventDefault();
            requestDeleteSelected(event);
        }
    }

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
            duplicateNearThreshold: duplicateNearThreshold.value,
        }),
        (settings) => {
            try {
                window.localStorage.setItem(SETTINGS_KEY, JSON.stringify(settings));
            } catch {
                // ignore settings persistence failures
            }
        },
        { deep: true },
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
            if (tab === "tags" && !hasLoadedTags.value && !isLoadingTags.value) {
                await fetchTags();
            }
            if (tab === "stats" && !isLoadingFolderStats.value) {
                await fetchFolderStats();
            }
            if (tab === "stats" && !isLoadingMetadataHealth.value) {
                await fetchMetadataHealth({ refresh: false, cacheOnly: true });
            }
        }
    );

    watch(
        () => [tagFilters.q, tagFilters.category, tagFilters.view],
        () => {
            if (!hasLoadedTags.value || tagFilters.view !== "all") {
                return;
            }
            if (tagSearchTimer) {
                clearTimeout(tagSearchTimer);
            }
            tagSearchTimer = setTimeout(() => {
                fetchTags({ append: false });
            }, 180);
        }
    );

    watch(
        () => [assets.value.length, filters.density],
        async () => {
            await nextTick();
            measureAssetList();
        }
    );

    onMounted(async () => {
        addWindowListener("dragenter", onWindowDragEnter);
        addWindowListener("dragover", onWindowDragOver);
        addWindowListener("dragleave", onWindowDragLeave);
        addWindowListener("drop", onWindowDrop);
        addWindowListener("dragend", hideDropOverlay);
        addWindowListener("blur", hideDropOverlay);
        addWindowListener("resize", measureAssetList);
        addDocumentListener("keydown", onDocumentKeydown);
        addDocumentListener("visibilitychange", () => {
            if (document.hidden) {
                hideDropOverlay();
            }
        });

        if (window.ResizeObserver) {
            resizeObserver = new ResizeObserver(measureAssetList);
            if (assetListRef.value) {
                resizeObserver.observe(assetListRef.value);
            }
        }

        try {
            await fetchSettings();
            await fetchRoots();
            await fetchAssets({ append: false });
            if (activeTab.value === "stats") {
                await fetchFolderStats();
                await fetchMetadataHealth({ refresh: false, cacheOnly: true });
            }
        } catch (error) {
            console.error(error);
            statusText.value = error?.message || "Initialization failed.";
        }
    });

    onUnmounted(() => {
        if (searchTimer) {
            clearTimeout(searchTimer);
        }
        if (tagSearchTimer) {
            clearTimeout(tagSearchTimer);
        }
        resizeObserver?.disconnect();
        cleanupCallbacks.forEach((cleanup) => cleanup());
        hideDropOverlay();
    });

    return {
        activeTab,
        roots,
        assets,
        filters,
        selectedAsset,
        details,
        selectedPath,
        selectedPaths,
        selectedCount,
        selectedPathSetHas,
        deleteCount,
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
        layoutStyle,
        assetListStyle,
        densityClass,
        assetListRef,
        searchInputRef,
        shouldVirtualize,
        visibleAssets,
        virtualSpacerStyle,
        virtualWindowStyle,
        onAssetListScroll,
        tags,
        tagFilters,
        tagCategories,
        tagStatusText,
        tagCountText,
        isLoadingTags,
        filteredTags,
        visibleTags,
        tagHasMore,
        selectedTag,
        selectedTagAliases,
        selectedTagExamples,
        tagExamplesLoading,
        isTagFavorite,
        fetchTags,
        selectTag,
        toggleTagFavorite,
        loadMoreTags,
        exampleImageUrl,
        tagSearchUrl,
        duplicateGroups,
        duplicateSummary,
        duplicateStatusText,
        duplicateIncludeNear,
        duplicateNearThreshold,
        duplicateCountText,
        duplicateScanProgress,
        duplicateScanPhase,
        duplicateScanProgressText,
        canCompareSelection,
        compareLeft,
        compareRight,
        compareSlider,
        compareStageRef,
        compareClipStyle,
        metadataHealth,
        metadataHealthStatus,
        isLoadingMetadataHealth,
        folderStats,
        folderStatsStatus,
        isLoadingFolderStats,
        folderStatsSummary,
        folderStatsMetrics,
        metadataStatsMetrics,
        statsPrimaryCount,
        statsRootReports,
        isLoadingAnyFolderStats,
        isLoadingAnyMetadataHealth,
        appSettings,
        appSettingsSchema,
        settingsSections,
        settingsStatus,
        isLoadingSettings,
        isSavingSettings,
        settingsFieldValue,
        settingsListValue,
        settingsListDraftValue,
        updateSettingsListDraft,
        updateSetting,
        updateStringListItem,
        addStringListSetting,
        removeStringListItem,
        metadataFilterList,
        fetchMetadataHealth,
        fetchFolderStats,
        fetchRootMetadataHealth,
        fetchRootFolderStats,
        isScanningDuplicates,
        duplicateKindLabel,
        duplicateGroupSubtitle,
        markDuplicateThumbFailed,
        metadataBadges,
        scanDuplicates,
        selectDuplicateAsset,
        selectDuplicateGroupPaths,
        selectDuplicateGroupExcept,
        selectAllDuplicateGroupsExcept,
        openCompareSelection,
        startCompareDrag,
        dragCompareDivider,
        stopCompareDrag,
        nudgeCompareDivider,
        closeCompare,
        thumbUrl,
        fileUrl,
        startDetailsResize,
        startPreviewResize,
        selectAsset,
        refreshAssets,
        loadMore,
        toggleBlurThumbnails,
        copySelectedPaths,
        exportSelectedAssets,
        exportDuplicateGroups,
        exportMetadataHealth,
        openContainingFolder,
        repairSelectedMetadata,
        clearSelection,
        requestDeleteSelected,
        requestDeleteAsset,
        hideDeleteConfirm,
        confirmDelete,
    };
}
