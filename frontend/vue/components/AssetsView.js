import { AssetCard } from '/vue/components/AssetCard.js';
import { AssetDetailsPanel } from '/vue/components/AssetDetailsPanel.js';
import { SavedViews } from '/vue/components/SavedViews.js';
import { ReviewSlideshow } from '/vue/components/ReviewSlideshow.js';

export const AssetsView = {
  name: 'AssetsView',
  components: {
    SavedViews,
    ReviewSlideshow,
    AssetCard,
    AssetDetailsPanel
  },
  data() {
    return { moveDestination: '', filtersOpen: false, dragPaths: [], dropTarget: null };
  },
  mounted() {
    this.onOpenReviewRequest = (event) => this.openReview({ path: event.detail?.path });
    window.addEventListener('asset-viewer:open-review', this.onOpenReviewRequest);
  },
  beforeUnmount() {
    window.removeEventListener('asset-viewer:open-review', this.onOpenReviewRequest);
  },
  methods: {
    onCardDragStart(asset, event) {
      // Dragging a selected card carries the whole selection; otherwise just that card.
      const paths =
        this.selectedPathSetHas(asset.path) && this.selectedCount > 1
          ? this.assets.filter((item) => this.selectedPathSetHas(item.path)).map((item) => item.path)
          : [asset.path];
      this.dragPaths = paths;
      event.dataTransfer.effectAllowed = 'move';
      event.dataTransfer.setData('application/x-bubba-asset-paths', JSON.stringify(paths));
      event.dataTransfer.setData('text/plain', paths.join('\n'));
      const badge = document.createElement('div');
      badge.className = 'asset-drag-badge';
      badge.textContent = paths.length === 1 ? '1 file' : `${paths.length} files`;
      document.body.appendChild(badge);
      event.dataTransfer.setDragImage(badge, 12, 12);
      setTimeout(() => badge.remove(), 0);
    },
    onCardDragEnd() {
      this.dragPaths = [];
      this.dropTarget = null;
    },
    canDropOn(folder) {
      // Allow the drop when at least one dragged file lives somewhere other than the target folder.
      if (!this.dragPaths.length) return false;
      const normalize = (value) => String(value || '').replace(/\\/g, '/');
      const target = normalize(folder.path);
      return this.dragPaths.some((path) => {
        const rel = normalize(this.assets.find((item) => item.path === path)?.relative_path);
        const parent = rel.includes('/') ? rel.slice(0, rel.lastIndexOf('/')) : '';
        return parent !== target;
      });
    },
    onFolderDragOver(folder, event) {
      if (!this.canDropOn(folder)) return;
      event.preventDefault();
      event.dataTransfer.dropEffect = 'move';
      this.dropTarget = folder.path;
    },
    onFolderDragLeave(folder, event) {
      if (this.dropTarget === folder.path && !event.currentTarget.contains(event.relatedTarget)) {
        this.dropTarget = null;
      }
    },
    async onFolderDrop(folder, event) {
      const paths = this.dragPaths.slice();
      this.dropTarget = null;
      this.dragPaths = [];
      if (!paths.length) return;
      event.preventDefault();
      await this.moveSelectedAssets(folder.path, paths);
    },
    formatCount(value) {
      return value >= 10000 ? `${Math.round(value / 1000)}k` : value.toLocaleString();
    },
    openReview(asset) {
      if (asset?.path) {
        this.$refs.slideshow?.open(asset.path);
      }
    }
  },
  props: {
    inspectorVisible: Boolean,
    canCompareSelection: Boolean,
    rootsLoading: Boolean,
    rootsError: String,
    assetError: String,
    toggleInspector: Function,
    retryRoots: Function,
    retryAssets: Function,
    clearMediaFilters: Function,
    openSettings: Function,
    toggleBlurThumbnails: Function,
    layoutStyle: {
      type: Object,
      required: true
    },
    filters: {
      type: Object,
      required: true
    },
    roots: {
      type: Array,
      required: true
    },
    folderTree: {
      type: Array,
      required: true
    },
    isFolderTreeCollapsed: {
      type: Boolean,
      default: false
    },
    metadataFilterList: {
      type: Array,
      required: true
    },
    assets: {
      type: Array,
      required: true
    },
    selectedAsset: {
      type: Object,
      default: null
    },
    details: {
      type: Object,
      default: null
    },
    selectedPath: {
      type: String,
      required: true
    },
    selectedPathSetHas: {
      type: Function,
      required: true
    },
    blurThumbnails: {
      type: Boolean,
      default: false
    },
    statusText: {
      type: String,
      required: true
    },
    selectedCount: {
      type: Number,
      required: true
    },
    deleteCount: {
      type: Number,
      required: true
    },
    isLoading: {
      type: Boolean,
      default: false
    },
    isLoadingMore: {
      type: Boolean,
      default: false
    },
    isDeleting: {
      type: Boolean,
      default: false
    },
    hasMore: {
      type: Boolean,
      default: false
    },
    currentRootLabel: {
      type: String,
      required: true
    },
    densityClass: {
      type: String,
      required: true
    },
    assetListStyle: {
      type: Object,
      required: true
    },
    shouldVirtualize: {
      type: Boolean,
      default: false
    },
    visibleAssets: {
      type: Array,
      required: true
    },
    virtualSpacerStyle: {
      type: Object,
      required: true
    },
    virtualWindowStyle: {
      type: Object,
      required: true
    },
    assetListRef: {
      type: Function,
      required: true
    },
    searchInputRef: {
      type: Function,
      required: true
    },
    onAssetListScroll: {
      type: Function,
      required: true
    },
    refreshAssets: {
      type: Function,
      required: true
    },
    selectRoot: {
      type: Function,
      required: true
    },
    selectFolder: {
      type: Function,
      required: true
    },
    toggleFolderExpanded: {
      type: Function,
      required: true
    },
    toggleFolderTree: {
      type: Function,
      required: true
    },
    createFolder: {
      type: Function,
      required: true
    },
    moveSelectedAssets: {
      type: Function,
      required: true
    },
    loadMore: {
      type: Function,
      required: true
    },
    selectAsset: {
      type: Function,
      required: true
    },
    clearSelection: {
      type: Function,
      required: true
    },
    copySelectedPaths: {
      type: Function,
      required: true
    },
    exportSelectedAssets: {
      type: Function,
      required: true
    },
    openCompareSelection: {
      type: Function,
      required: true
    },
    requestDeleteSelected: {
      type: Function,
      required: true
    },
    requestDeleteAsset: {
      type: Function,
      required: true
    },
    hideDeleteConfirm: {
      type: Function,
      required: true
    },
    confirmDelete: {
      type: Function,
      required: true
    },
    safeDelete: {
      type: Boolean,
      default: true
    },
    startDetailsResize: {
      type: Function,
      required: true
    },
    startPreviewResize: {
      type: Function,
      required: true
    },
    openContainingFolder: {
      type: Function,
      required: true
    },
    repairSelectedMetadata: {
      type: Function,
      required: true
    },
    toggleFavorite: {
      type: Function,
      required: true
    }
  },
  template: `
        <div class="layout assets-layout tab-panel" :class="{ 'inspector-hidden': !inspectorVisible }" :style="layoutStyle">
            <section class="panel assets-panel">
                <div class="assets-browser-shell" :class="{ 'folder-tree-collapsed': isFolderTreeCollapsed }">
                    <Teleport defer to="#library-content"><aside class="folder-tree-panel" aria-label="Media folders">
                        <div class="folder-tree-content">
                            <div class="folder-tree-section">
                                <div class="folder-tree-heading">Roots</div>
                                <button
                                    v-for="root in roots"
                                    :key="root.key"
                                    class="folder-tree-item root-item"
                                    :class="{ active: filters.root === root.key }"
                                    type="button"
                                    @click="selectRoot(root.key)"
                                >
                                    {{ root.label || root.key }}
                                </button>
                            </div>
                            <div class="folder-tree-section">
                                <div class="folder-tree-heading folder-tree-heading--actions">
                                    <span>Folders</span>
                                    <button class="button button--compact button--ghost" type="button" @click="createFolder">+ New</button>
                                </div>
                                <div
                                    v-for="folder in folderTree"
                                    :key="folder.path || '__root__'"
                                    class="folder-tree-row"
                                    :class="{ active: filters.folder === folder.path, 'is-drop-target': dropTarget === folder.path }"
                                    @dragover="onFolderDragOver(folder, $event)"
                                    @dragleave="onFolderDragLeave(folder, $event)"
                                    @drop="onFolderDrop(folder, $event)"
                                    :style="{ '--folder-depth': folder.depth || 0 }"
                                >
                                    <button
                                        class="folder-expand-button"
                                        type="button"
                                        :disabled="!folder.hasChildren || !folder.path"
                                        :aria-label="folder.isExpanded ? 'Collapse folder' : 'Expand folder'"
                                        :aria-expanded="folder.hasChildren && folder.path ? folder.isExpanded : undefined"
                                        @click="toggleFolderExpanded(folder.path)"
                                    >
                                        <svg v-if="folder.hasChildren && folder.path" class="folder-chevron" :class="{ 'is-expanded': folder.isExpanded }" viewBox="0 0 16 16" aria-hidden="true"><path d="M6 3.5 10.5 8 6 12.5" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>
                                    </button>
                                    <button
                                        class="folder-tree-item"
                                        type="button"
                                        :title="folder.path || 'All folders'"
                                        @click="selectFolder(folder.path)"
                                    >
                                        <span class="folder-tree-label">{{ folder.path ? folder.label : 'All folders' }}</span>
                                        <span v-if="Number.isFinite(folder.file_count)" class="folder-tree-count">{{ formatCount(folder.file_count) }}</span>
                                    </button>
                                </div>
                            </div>
                        </div>
                        <SavedViews ref="savedViews" :filters="filters" />
                    </aside></Teleport>

                    <div class="assets-browser-main">
                        <div class="media-breadcrumb" aria-label="Current folder"><strong>{{ currentRootLabel }}</strong><span v-if="filters.folder"> / {{ filters.folder }}</span><span v-else> / All folders</span></div>
                        <div class="media-toolbar">
                            <input id="searchInput" :ref="searchInputRef" v-model="filters.q" class="input search-field" type="search" aria-label="Search" placeholder="Search filenames or paths" />
                            <button class="button button--compact" type="button" :aria-expanded="filtersOpen" aria-controls="media-filters" @click="filtersOpen = !filtersOpen">Filters</button>
                            <button class="button button--compact favorites-filter-button" type="button" :aria-pressed="filters.favorites === '1'" title="Show only favorites" @click="filters.favorites = filters.favorites ? '' : '1'">★ Favorites</button>
                            <button class="button button--compact" type="button" :disabled="!filters.root" @click="$refs.savedViews.openSave($event)">Saved views</button>
                            <ReviewSlideshow ref="slideshow" :assets="assets" :selected-path="selectedPath" :blur="blurThumbnails" />
                            <button class="button button--compact" type="button" :disabled="isLoading || rootsLoading" @click="refreshAssets({ refreshIndex: true, keepSelection: true })">Refresh</button>
                            <button class="button button--compact" type="button" :aria-pressed="inspectorVisible" @click="toggleInspector">Inspector</button>
                        </div>
                        <div v-if="filtersOpen" id="media-filters" class="filter-controls">
                            <label>Extension <select id="extSelect" v-model="filters.ext" class="select"><option value="">All extensions</option><option v-for="ext in ['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff', '.mp4']" :key="ext">{{ ext }}</option></select></label>
                            <label class="filter-favorites"><input type="checkbox" :checked="filters.favorites === '1'" @change="filters.favorites = $event.target.checked ? '1' : ''" /> Favorites only</label>
                            <label>Metadata <select id="metadataFilterSelect" v-model="filters.metadataBadge" class="select"><option value="">Any metadata</option><option v-for="filter in metadataFilterList" :key="filter.key" :value="filter.key">{{ filter.label }}</option></select></label>
                        </div>
                        <div v-if="filters.q || filters.ext || filters.metadataBadge || filters.favorites" class="active-filters" aria-label="Active filters">
                            <button v-if="filters.favorites" type="button" class="filter-chip" aria-label="Remove favorites filter" @click="filters.favorites = ''">★ Favorites ×</button>
                            <button v-if="filters.q" type="button" class="filter-chip" aria-label="Remove search filter" @click="filters.q = ''">Search: {{ filters.q }} ×</button>
                            <button v-if="filters.ext" type="button" class="filter-chip" aria-label="Remove extension filter" @click="filters.ext = ''">{{ filters.ext }} ×</button>
                            <button v-if="filters.metadataBadge" type="button" class="filter-chip" aria-label="Remove metadata filter" @click="filters.metadataBadge = ''">{{ metadataFilterList.find(item => item.key === filters.metadataBadge)?.label }} ×</button>
                        </div>
                        <div class="view-controls">
                            <label>Sort <select id="sortBySelect" v-model="filters.sortBy" class="select"><option value="name">Name</option><option value="extension">Extension</option><option value="modified">Modified time</option><option value="size">Size</option><option value="metadata">Metadata</option></select></label>
                            <label>Order <select id="sortDirSelect" v-model="filters.sortDir" class="select"><option value="asc">Ascending</option><option value="desc">Descending</option></select></label>
                            <label>Density <select v-model="filters.density" class="select"><option value="compact">Compact</option><option value="comfortable">Comfortable</option><option value="large">Large</option></select></label>
                            <label><input type="checkbox" :checked="blurThumbnails" @change="toggleBlurThumbnails" /> Blur</label>
                        </div>
                        <div v-if="deleteCount" class="selection-bar" aria-label="Selection actions">
                            <strong>{{ deleteCount }} selected</strong>
                            <button v-if="selectedCount > 1" class="button button--compact" type="button" :disabled="!canCompareSelection" title="Select exactly two previewable images" @click="openCompareSelection">Compare</button>
                            <details class="action-menu"><summary>Move</summary><div class="action-menu-panel"><label for="moveDestination">Destination folder</label><select id="moveDestination" v-model="moveDestination" class="select"><option v-for="folder in folderTree" :key="folder.path" :value="folder.path">{{ folder.path || 'root' }}</option></select><button type="button" @click="moveSelectedAssets(moveDestination)">Move selected</button></div></details>
                            <button class="button button--compact" type="button" @click="toggleFavorite()">★ Favorite</button>
                            <button class="button button--compact" type="button" @click="copySelectedPaths">Copy paths</button>
                            <details class="action-menu"><summary>Export</summary><div class="action-menu-panel"><button type="button" @click="exportSelectedAssets('json')">Export JSON</button><button type="button" @click="exportSelectedAssets('csv')">Export CSV</button></div></details>
                            <button class="button button--compact button--danger" type="button" :disabled="isDeleting" title="Move selected media to trash. Shift-click permanently deletes without confirmation." @click="requestDeleteSelected">Delete</button>
                            <button class="button button--compact button--ghost" type="button" :disabled="isDeleting" @click="clearSelection">Clear</button>
                        </div>
                <div class="results assets-results">
                    <div class="media-feedback" :class="{ 'is-error': assetError }" role="status">
                        <span v-if="isLoading || isLoadingMore || rootsLoading" class="loading-indicator" aria-hidden="true"></span>
                        <span>{{ rootsLoading ? 'Loading libraries…' : rootsError || assetError || statusText }}</span>
                        <button v-if="assetError && assets.length" class="button button--compact" type="button" @click="retryAssets">Retry</button>
                    </div>
                    <div
                        :ref="assetListRef"
                        class="asset-list"
                        :class="[densityClass, { virtualized: shouldVirtualize }]"
                        :style="assetListStyle"
                        aria-live="polite"
                        @scroll="onAssetListScroll"
                    >
                        <div v-if="!assets.length" class="media-empty">
                            <template v-if="rootsLoading || isLoading"><h2>Loading media…</h2><p>Your library will appear here.</p></template>
                            <template v-else-if="rootsError"><h2>Could not load libraries</h2><p>{{ rootsError }}</p><button class="button button--compact" type="button" @click="retryRoots">Retry</button></template>
                            <template v-else-if="!roots.length"><h2>Add your first library</h2><p>Choose a folder in Settings to start browsing.</p><button class="button button--compact" type="button" @click="openSettings">Open settings</button></template>
                            <template v-else-if="assetError"><h2>Could not load media</h2><p>{{ assetError }}</p><button class="button button--compact" type="button" @click="retryAssets">Retry</button></template>
                            <template v-else-if="filters.favorites && !filters.q && !filters.ext && !filters.metadataBadge"><h2>No favorites here yet</h2><p>Star media with the ☆ on a card, the inspector, or the F key.</p><button class="button button--compact" type="button" @click="filters.favorites = ''">Show all media</button></template>
                            <template v-else-if="filters.q || filters.ext || filters.metadataBadge"><h2>No matching media</h2><p>Try a different search or clear the active filters.</p><button class="button button--compact" type="button" @click="clearMediaFilters">Clear filters</button></template>
                            <template v-else><h2>This folder has no media</h2><p>Choose another folder or drop supported images and videos here.</p></template>
                        </div>
                        <template v-if="shouldVirtualize">
                            <div class="asset-virtual-spacer" :style="virtualSpacerStyle"></div>
                            <div class="asset-virtual-window" :style="virtualWindowStyle">
                                <AssetCard
                                    v-for="asset in visibleAssets"
                                    :key="asset.path"
                                    :asset="asset"
                                    :active="selectedPath === asset.path"
                                    :multi-selecting="selectedCount > 0"
                                    :selected="selectedPathSetHas(asset.path)"
                                    :blur-enabled="blurThumbnails"
                                    @select="selectAsset"
                                    @open="openReview"
                                    @favorite="toggleFavorite"
                                    @drag-start="onCardDragStart"
                                    @drag-end="onCardDragEnd"
                                />
                            </div>
                        </template>
                        <AssetCard
                            v-else
                            v-for="asset in assets"
                            :key="asset.path"
                            :asset="asset"
                            :active="selectedPath === asset.path"
                            :multi-selecting="selectedCount > 0"
                                    :selected="selectedPathSetHas(asset.path)"
                            :blur-enabled="blurThumbnails"
                            @select="selectAsset"
                            @open="openReview"
                                    @favorite="toggleFavorite"
                                    @drag-start="onCardDragStart"
                                    @drag-end="onCardDragEnd"
                        />
                    </div>

                    <button v-if="hasMore && !assetError" class="button assets-load-more-button" type="button" :disabled="isLoadingMore" @click="loadMore">
                        {{ isLoadingMore ? 'Loading...' : 'Load More' }}
                    </button>
                </div>
                    </div>
                </div>
            </section>

            <div
                v-if="inspectorVisible"
                class="panel-resizer"
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize details panel width"
                title="Drag to resize details panel width"
                tabindex="0"
                @keydown.stop="startDetailsResize"
                @mousedown="startDetailsResize"
            ></div>

            <AssetDetailsPanel v-if="inspectorVisible"
                :selected-asset="selectedAsset"
                :asset-details="details"
                @delete-asset="requestDeleteAsset"
                @open-folder="openContainingFolder"
                @repair-metadata="repairSelectedMetadata"
                @toggle-favorite="toggleFavorite"
                @filter-by="(value) => { filters.q = value; }"
                @resize-preview="startPreviewResize"
            />
        </div>
    `
};
