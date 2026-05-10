import { AssetCard } from "/vue/components/AssetCard.js";
import { AssetDetailsPanel } from "/vue/components/AssetDetailsPanel.js";

export const AssetsView = {
    name: "AssetsView",
    components: {
        AssetCard,
        AssetDetailsPanel,
    },
    props: {
        layoutStyle: {
            type: Object,
            required: true,
        },
        filters: {
            type: Object,
            required: true,
        },
        roots: {
            type: Array,
            required: true,
        },
        metadataFilterList: {
            type: Array,
            required: true,
        },
        assets: {
            type: Array,
            required: true,
        },
        selectedAsset: {
            type: Object,
            default: null,
        },
        details: {
            type: Object,
            default: null,
        },
        selectedPath: {
            type: String,
            required: true,
        },
        selectedPathSetHas: {
            type: Function,
            required: true,
        },
        blurThumbnails: {
            type: Boolean,
            default: false,
        },
        statusText: {
            type: String,
            required: true,
        },
        selectedCount: {
            type: Number,
            required: true,
        },
        deleteCount: {
            type: Number,
            required: true,
        },
        isLoading: {
            type: Boolean,
            default: false,
        },
        isLoadingMore: {
            type: Boolean,
            default: false,
        },
        isDeleting: {
            type: Boolean,
            default: false,
        },
        hasMore: {
            type: Boolean,
            default: false,
        },
        currentRootLabel: {
            type: String,
            required: true,
        },
        densityClass: {
            type: String,
            required: true,
        },
        assetListStyle: {
            type: Object,
            required: true,
        },
        shouldVirtualize: {
            type: Boolean,
            default: false,
        },
        visibleAssets: {
            type: Array,
            required: true,
        },
        virtualSpacerStyle: {
            type: Object,
            required: true,
        },
        virtualWindowStyle: {
            type: Object,
            required: true,
        },
        assetListRef: {
            type: Function,
            required: true,
        },
        searchInputRef: {
            type: Function,
            required: true,
        },
        onAssetListScroll: {
            type: Function,
            required: true,
        },
        refreshAssets: {
            type: Function,
            required: true,
        },
        loadMore: {
            type: Function,
            required: true,
        },
        selectAsset: {
            type: Function,
            required: true,
        },
        clearSelection: {
            type: Function,
            required: true,
        },
        copySelectedPaths: {
            type: Function,
            required: true,
        },
        exportSelectedAssets: {
            type: Function,
            required: true,
        },
        openCompareSelection: {
            type: Function,
            required: true,
        },
        requestDeleteSelected: {
            type: Function,
            required: true,
        },
        requestDeleteAsset: {
            type: Function,
            required: true,
        },
        hideDeleteConfirm: {
            type: Function,
            required: true,
        },
        confirmDelete: {
            type: Function,
            required: true,
        },
        safeDelete: {
            type: Boolean,
            default: true,
        },
        startDetailsResize: {
            type: Function,
            required: true,
        },
        startPreviewResize: {
            type: Function,
            required: true,
        },
        openContainingFolder: {
            type: Function,
            required: true,
        },
        repairSelectedMetadata: {
            type: Function,
            required: true,
        },
    },
    template: `
        <div class="layout tab-panel" :style="layoutStyle">
            <section class="panel">
                <div class="controls assets-controls">
                    <div class="assets-main-row">
                        <div class="field field--narrow">
                            <label for="rootSelect">Select Folder</label>
                            <select id="rootSelect" v-model="filters.root" class="select">
                                <option v-for="root in roots" :key="root.key" :value="root.key">{{ root.label || root.key }}</option>
                            </select>
                        </div>

                        <div class="field field--grow">
                            <label for="searchInput">Search</label>
                            <input id="searchInput" :ref="searchInputRef" v-model="filters.q" class="input" type="search" placeholder="Filename or subpath" />
                        </div>

                        <div class="field">
                            <label for="extSelect">Extension</label>
                            <select id="extSelect" v-model="filters.ext" class="select">
                                <option value="">All extensions</option>
                                <option value=".png">.png</option>
                                <option value=".jpg">.jpg</option>
                                <option value=".jpeg">.jpeg</option>
                                <option value=".webp">.webp</option>
                                <option value=".bmp">.bmp</option>
                            </select>
                        </div>

                        <div class="field">
                            <label for="metadataFilterSelect">Metadata</label>
                            <select id="metadataFilterSelect" v-model="filters.metadataBadge" class="select">
                                <option value="">Any metadata</option>
                                <option v-for="filter in metadataFilterList" :key="filter.key" :value="filter.key">{{ filter.label }}</option>
                            </select>
                        </div>

                        <div class="field">
                            <label for="sortBySelect">Sort By</label>
                            <select id="sortBySelect" v-model="filters.sortBy" class="select">
                                <option value="name">Name</option>
                                <option value="modified">Modified time</option>
                                <option value="size">Size</option>
                                <option value="metadata">Metadata presence</option>
                            </select>
                        </div>

                        <div class="field">
                            <label for="sortDirSelect">Order</label>
                            <select id="sortDirSelect" v-model="filters.sortDir" class="select">
                                <option value="asc">Ascending</option>
                                <option value="desc">Descending</option>
                            </select>
                        </div>
                    </div>
                </div>

                <div class="results">
                    <div class="meta-row">
                        <div class="meta-group">
                            <span class="status-dot" aria-hidden="true"></span>
                            <span>{{ statusText }}</span>
                        </div>
                        <div class="meta-actions">
                            <div class="count-badge">
                                {{ assets.length }} loaded<span v-if="selectedCount"> / {{ selectedCount }} selected</span>
                            </div>
                            <button
                                v-if="selectedCount > 1"
                                class="button button--compact"
                                type="button"
                                @click="openCompareSelection"
                            >
                                Compare
                            </button>
                            <details v-if="deleteCount > 0" class="action-menu">
                                <summary>Selection</summary>
                                <div class="action-menu-panel">
                                    <button type="button" @click="copySelectedPaths">Copy Paths</button>
                                    <button type="button" @click="exportSelectedAssets('json')">Export JSON</button>
                                    <button type="button" @click="exportSelectedAssets('csv')">Export CSV</button>
                                </div>
                            </details>
                            <button class="button button--compact" type="button" :disabled="isLoading" @click="refreshAssets">Refresh</button>
                            <button
                                v-if="deleteCount > 0"
                                class="button button--compact button--danger"
                                type="button"
                                title="Delete selected media. Hold Shift while clicking to permanently delete without confirmation."
                                :disabled="isDeleting"
                                @click="requestDeleteSelected"
                            >
                                {{ deleteCount > 1 ? 'Delete ' + deleteCount : 'Delete' }}
                            </button>
                            <button
                                v-if="selectedCount > 0"
                                class="button button--compact button--ghost"
                                type="button"
                                :disabled="isDeleting"
                                @click="clearSelection"
                            >
                                Clear
                            </button>
                        </div>
                    </div>

                    <div
                        :ref="assetListRef"
                        class="asset-list"
                        :class="[densityClass, { virtualized: shouldVirtualize }]"
                        :style="assetListStyle"
                        aria-live="polite"
                        @scroll="onAssetListScroll"
                    >
                        <div v-if="!assets.length" class="empty">No media matched your filters.</div>
                        <template v-if="shouldVirtualize">
                            <div class="asset-virtual-spacer" :style="virtualSpacerStyle"></div>
                            <div class="asset-virtual-window" :style="virtualWindowStyle">
                                <AssetCard
                                    v-for="asset in visibleAssets"
                                    :key="asset.path"
                                    :asset="asset"
                                    :active="selectedPath === asset.path"
                                    :selected="selectedPathSetHas(asset.path)"
                                    :blur-enabled="blurThumbnails"
                                    @select="selectAsset"
                                />
                            </div>
                        </template>
                        <AssetCard
                            v-else
                            v-for="asset in assets"
                            :key="asset.path"
                            :asset="asset"
                            :active="selectedPath === asset.path"
                            :selected="selectedPathSetHas(asset.path)"
                            :blur-enabled="blurThumbnails"
                            @select="selectAsset"
                        />
                    </div>

                    <button v-if="hasMore" class="button" type="button" :disabled="isLoadingMore" @click="loadMore">
                        {{ isLoadingMore ? 'Loading...' : 'Load More' }}
                    </button>
                </div>
            </section>

            <div
                class="panel-resizer"
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize details panel width"
                title="Drag to resize details panel width"
                @mousedown="startDetailsResize"
            ></div>

            <AssetDetailsPanel
                :selected-asset="selectedAsset"
                :asset-details="details"
                @delete-asset="requestDeleteAsset"
                @open-folder="openContainingFolder"
                @repair-metadata="repairSelectedMetadata"
                @resize-preview="startPreviewResize"
            />
        </div>
    `,
};