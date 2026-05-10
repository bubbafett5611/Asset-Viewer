import { createApp } from "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js";
import { AssetCard } from "/vue/components/AssetCard.js";
import { AssetDetailsPanel } from "/vue/components/AssetDetailsPanel.js";
import { TagRow } from "/vue/components/TagRow.js";
import { TagDetailsPanel } from "/vue/components/TagDetailsPanel.js";
import { useAssetViewerState } from "/vue/useAssetViewer.js";

createApp({
    components: {
        AssetCard,
        AssetDetailsPanel,
        TagRow,
        TagDetailsPanel,
    },
    setup() {
        return useAssetViewerState();
    },
    template: `
        <div class="page">
            <div v-if="isDropOverlayVisible" class="drop-overlay">
                <div class="drop-overlay-card">
                    <div class="drop-overlay-title">{{ isUploading ? 'Uploading images' : 'Drop images to upload' }}</div>
                    <div class="drop-overlay-subtitle">Uploading to {{ currentRootLabel }}</div>
                </div>
            </div>

            <div v-if="isDeleteConfirmVisible" class="delete-confirm-modal">
                <div class="delete-confirm-card">
                    <div class="delete-confirm-title">Delete <span class="delete-count">{{ deleteCount }}</span> media item(s)?</div>
                    <div class="delete-confirm-message">
                        {{ safeDelete ? 'Files will be moved to .asset_viewer_trash.' : 'This action cannot be undone.' }}
                    </div>
                    <label class="delete-safety-toggle">
                        <input v-model="safeDelete" type="checkbox" />
                        <span>Move to viewer trash instead of permanent delete</span>
                    </label>
                    <div class="delete-confirm-buttons">
                        <button class="btn btn-secondary" type="button" :disabled="isDeleting" @click="hideDeleteConfirm">Cancel</button>
                        <button class="btn btn-danger" type="button" :disabled="isDeleting" @click="confirmDelete">
                            {{ isDeleting ? 'Deleting...' : 'Delete' }}
                        </button>
                    </div>
                </div>
            </div>

            <div v-if="compareLeft && compareRight" class="compare-modal">
                <div class="compare-card">
                    <div class="compare-header">
                        <div>
                            <h2>Compare Images</h2>
                            <p>{{ compareLeft.name }} / {{ compareRight.name }}</p>
                        </div>
                        <button class="button button--compact button--ghost" type="button" @click="closeCompare">Close</button>
                    </div>
                    <div ref="compareStageRef" class="compare-stage">
                        <img class="compare-image compare-image-base" :src="fileUrl(compareRight.path)" :alt="compareRight.name" />
                        <img class="compare-image compare-image-overlay" :src="fileUrl(compareLeft.path)" :alt="compareLeft.name" :style="compareClipStyle" />
                        <button
                            class="compare-divider"
                            type="button"
                            role="slider"
                            aria-label="Image compare position"
                            aria-valuemin="0"
                            aria-valuemax="100"
                            :aria-valuenow="Math.round(compareSlider)"
                            :style="{ left: compareSlider + '%' }"
                            @pointerdown="startCompareDrag"
                            @pointermove="dragCompareDivider"
                            @pointerup="stopCompareDrag"
                            @pointercancel="stopCompareDrag"
                            @keydown="nudgeCompareDivider"
                        ></button>
                    </div>
                </div>
            </div>

            <header class="header">
                <div class="header-copy">
                    <h1 class="title">Bubba Media Viewer</h1>
                </div>
                <nav class="tab-nav" aria-label="Viewer sections">
                    <button
                        class="tab-button"
                        :class="{ 'is-active': activeTab === 'assets' }"
                        type="button"
                        :aria-pressed="activeTab === 'assets'"
                        @click="activeTab = 'assets'"
                    >
                        Media
                    </button>
                    <button
                        class="tab-button"
                        :class="{ 'is-active': activeTab === 'tags' }"
                        type="button"
                        :aria-pressed="activeTab === 'tags'"
                        @click="activeTab = 'tags'"
                    >
                        Tag Browser
                    </button>
                    <button
                        class="tab-button"
                        :class="{ 'is-active': activeTab === 'duplicates' }"
                        type="button"
                        :aria-pressed="activeTab === 'duplicates'"
                        @click="activeTab = 'duplicates'"
                    >
                        Duplicates
                    </button>
                    <button
                        class="tab-button"
                        :class="{ 'is-active': activeTab === 'stats' }"
                        type="button"
                        :aria-pressed="activeTab === 'stats'"
                        @click="activeTab = 'stats'"
                    >
                        Stats
                    </button>
                    <button
                        class="tab-button"
                        :class="{ 'is-active': activeTab === 'settings' }"
                        type="button"
                        :aria-pressed="activeTab === 'settings'"
                        @click="activeTab = 'settings'"
                    >
                        Settings
                    </button>
                </nav>
            </header>

            <div v-if="activeTab === 'assets'" class="layout tab-panel" :style="layoutStyle">
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
                                <input id="searchInput" ref="searchInputRef" v-model="filters.q" class="input" type="search" placeholder="Filename or subpath" />
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
                                    v-if="canCompareSelection"
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
                            ref="assetListRef"
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
                                v-for="asset in visibleAssets"
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

            <div v-else-if="activeTab === 'tags'" class="layout tab-panel" :style="layoutStyle">
                <section class="panel">
                    <div class="controls tag-controls">
                        <div class="field tag-search-field">
                            <label for="tagSearchInput">Tag Search</label>
                            <input id="tagSearchInput" v-model="tagFilters.q" class="input" type="search" placeholder="Tag or alias" />
                        </div>

                        <div class="field">
                            <label for="tagCategorySelect">Category</label>
                            <select id="tagCategorySelect" v-model="tagFilters.category" class="select">
                                <option value="">All categories</option>
                                <option v-for="category in tagCategories" :key="category" :value="category">{{ category }}</option>
                            </select>
                        </div>

                        <div class="field">
                            <label for="tagViewSelect">View</label>
                            <select id="tagViewSelect" v-model="tagFilters.view" class="select">
                                <option value="all">All tags</option>
                                <option value="favorites">Favorites only</option>
                                <option value="recent">Recent only</option>
                            </select>
                        </div>

                        <div class="field tag-reload-field">
                            <div class="field-label">Controls</div>
                            <button id="tagReloadButton" class="button" type="button" :disabled="isLoadingTags" @click="fetchTags">
                                {{ isLoadingTags ? 'Reloading...' : 'Reload Tags' }}
                            </button>
                        </div>
                    </div>

                    <div class="results">
                        <div class="meta-row">
                            <div class="meta-group">
                                <span class="status-dot" aria-hidden="true"></span>
                                <span>{{ tagStatusText }}</span>
                            </div>
                            <div class="count-badge">{{ tagCountText }}</div>
                        </div>
                        <div class="tag-list" aria-live="polite">
                            <TagRow
                                v-for="tag in visibleTags"
                                :key="tag.name"
                                :tag="tag"
                                :active="selectedTag && selectedTag.name === tag.name"
                                :favorite="isTagFavorite(tag.name)"
                                @select="selectTag"
                                @toggle-favorite="toggleTagFavorite"
                            />
                        </div>
                        <button v-if="tagHasMore" class="button" type="button" @click="loadMoreTags">
                            Load More Tags
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
                <TagDetailsPanel
                    :selected-tag="selectedTag"
                    :favorite="selectedTag ? isTagFavorite(selectedTag.name) : false"
                    :aliases="selectedTagAliases"
                    :examples="selectedTagExamples"
                    :examples-loading="tagExamplesLoading"
                    :example-image-url="exampleImageUrl"
                    :tag-search-url="tagSearchUrl"
                    @toggle-favorite="toggleTagFavorite"
                />
            </div>

            <div v-else-if="activeTab === 'settings'" class="layout layout--single layout--utility tab-panel" :style="layoutStyle">
                <section class="panel settings-panel">
                    <div class="settings-header">
                        <div>
                            <h2>Settings</h2>
                        </div>
                    </div>

                    <div class="settings-content">
                        <section v-for="section in settingsSections" :key="section.key" class="settings-list">
                            <h3>{{ section.label }}</h3>
                            <div
                                v-for="field in section.fields"
                                :key="section.key + '.' + field.key"
                                class="settings-row"
                                :class="{ 'settings-row--list': field.type === 'string_list' }"
                            >
                                <label :for="'setting-' + section.key + '-' + field.key">{{ field.label }}</label>
                                <select
                                    v-if="field.type === 'select'"
                                    :id="'setting-' + section.key + '-' + field.key"
                                    class="select settings-control"
                                    :value="settingsFieldValue(section.key, field.key)"
                                    :disabled="isSavingSettings"
                                    @change="updateSetting(section.key, field.key, $event.target.value)"
                                >
                                    <option v-for="option in field.options" :key="option.value" :value="option.value">{{ option.label }}</option>
                                </select>
                                <button
                                    v-else-if="field.type === 'boolean'"
                                    :id="'setting-' + section.key + '-' + field.key"
                                    class="toggle-switch settings-switch"
                                    :class="{ 'is-active': settingsFieldValue(section.key, field.key) }"
                                    type="button"
                                    :aria-pressed="Boolean(settingsFieldValue(section.key, field.key))"
                                    :disabled="isSavingSettings"
                                    @click="updateSetting(section.key, field.key, !settingsFieldValue(section.key, field.key))"
                                >
                                    <span class="toggle-switch-track" aria-hidden="true">
                                        <span class="toggle-switch-thumb"></span>
                                    </span>
                                    <span>{{ settingsFieldValue(section.key, field.key) ? 'On' : 'Off' }}</span>
                                </button>
                                <div
                                    v-else-if="field.type === 'string_list'"
                                    class="settings-list-control"
                                >
                                    <div class="settings-list-items">
                                        <div
                                            v-for="(item, index) in settingsListValue(section.key, field.key)"
                                            :key="section.key + '.' + field.key + '.' + index"
                                            class="settings-list-item"
                                        >
                                            <input
                                                :id="'setting-' + section.key + '-' + field.key + '-' + index"
                                                class="input settings-list-input"
                                                :value="item"
                                                :disabled="isSavingSettings"
                                                @change="updateStringListItem(section.key, field.key, index, $event.target.value)"
                                            />
                                            <button
                                                class="button button--icon settings-icon-button"
                                                type="button"
                                                :aria-label="'Remove ' + field.label"
                                                :disabled="isSavingSettings"
                                                @click="removeStringListItem(section.key, field.key, index)"
                                            >-</button>
                                        </div>
                                        <div class="settings-list-item settings-list-add">
                                            <input
                                                :id="'setting-' + section.key + '-' + field.key"
                                                class="input settings-list-input"
                                                :placeholder="'Add ' + field.label"
                                                :value="settingsListDraftValue(section.key, field.key)"
                                                :disabled="isSavingSettings"
                                                @input="updateSettingsListDraft(section.key, field.key, $event.target.value)"
                                                @keydown.enter.prevent="addStringListSetting(section.key, field.key)"
                                            />
                                            <button
                                                class="button button--icon settings-icon-button"
                                                type="button"
                                                :aria-label="'Add ' + field.label"
                                                :disabled="isSavingSettings || !settingsListDraftValue(section.key, field.key).trim()"
                                                @click="addStringListSetting(section.key, field.key)"
                                            >+</button>
                                        </div>
                                    </div>
                                </div>
                                <input
                                    v-else
                                    :id="'setting-' + section.key + '-' + field.key"
                                    class="input settings-control"
                                    :value="settingsFieldValue(section.key, field.key)"
                                    :disabled="isSavingSettings"
                                    @change="updateSetting(section.key, field.key, $event.target.value)"
                                />
                            </div>
                        </section>
                        <div class="settings-empty">{{ settingsStatus }}</div>
                    </div>
                </section>
            </div>

            <div v-else-if="activeTab === 'stats'" class="layout layout--single layout--utility tab-panel" :style="layoutStyle">
                <section class="panel stats-panel">
                    <div class="settings-header stats-header">
                        <div>
                            <h2>Stats</h2>
                            <p>{{ statsRootReports.length }} root{{ statsRootReports.length === 1 ? '' : 's' }}</p>
                        </div>
                        <div class="stats-header-actions">
                            <button class="button button--compact" type="button" :disabled="isLoadingAnyFolderStats" @click="fetchFolderStats({ refresh: true })">
                                {{ isLoadingAnyFolderStats ? 'Refreshing...' : 'Refresh all stats' }}
                            </button>
                            <button class="button button--compact" type="button" :disabled="isLoadingAnyMetadataHealth" @click="fetchMetadataHealth({ refresh: true })">
                                {{ isLoadingAnyMetadataHealth ? 'Scanning...' : 'Scan all metadata' }}
                            </button>
                        </div>
                    </div>

                    <div class="stats-content">
                        <div v-if="!statsRootReports.length" class="stats-empty">No roots configured.</div>
                        <article v-for="report in statsRootReports" :key="report.key" class="stats-root">
                            <div class="stats-root-header">
                                <div>
                                    <h3>{{ report.label }}</h3>
                                    <p>{{ report.key }}</p>
                                </div>
                                <div class="stats-header-actions">
                                    <button class="button button--compact" type="button" :disabled="report.isLoadingFolderStats" @click="fetchRootFolderStats(report, { refresh: true })">
                                        {{ report.isLoadingFolderStats ? 'Refreshing...' : 'Refresh stats' }}
                                    </button>
                                    <button class="button button--compact" type="button" :disabled="report.isLoadingMetadataHealth" @click="fetchRootMetadataHealth(report, { refresh: true })">
                                        {{ report.isLoadingMetadataHealth ? 'Scanning...' : 'Scan metadata' }}
                                    </button>
                                </div>
                            </div>

                            <section class="stats-block">
                                <div class="stats-block-header">
                                    <div>
                                        <h4>Folder Overview</h4>
                                        <p>Current folder snapshot</p>
                                    </div>
                                </div>
                                <div v-if="report.folderStats" class="stats-metric-grid">
                                    <div v-for="metric in report.folderMetrics" :key="metric.key" class="stats-metric">
                                        <span>{{ metric.label }}</span>
                                        <strong>{{ metric.value }}</strong>
                                        <small>{{ metric.note }}</small>
                                    </div>
                                </div>
                                <div v-else class="stats-empty">{{ report.folderStatsStatus }}</div>
                            </section>

                            <section class="stats-block">
                                <div class="stats-block-header">
                                    <div>
                                        <h4>Metadata Coverage</h4>
                                        <p v-if="report.metadataHealth">Scanned {{ report.metadataHealth.total_assets }} media item(s), including {{ report.metadataHealth.png_assets }} PNG files.</p>
                                        <p v-else>Scan PNG metadata coverage for this root.</p>
                                    </div>
                                    <div v-if="report.metadataHealth" class="stats-export-actions">
                                        <button class="inline-export" type="button" @click="exportMetadataHealth('json', report.metadataHealth, report.label)">JSON</button>
                                        <button class="inline-export" type="button" @click="exportMetadataHealth('csv', report.metadataHealth, report.label)">CSV</button>
                                    </div>
                                </div>
                                <div v-if="report.metadataMetrics.length" class="stats-coverage-list">
                                    <div v-for="metric in report.metadataMetrics" :key="metric.key" class="stats-coverage-row">
                                        <div class="stats-coverage-label">
                                            <span>{{ metric.label }}</span>
                                            <strong>{{ metric.valueLabel }}</strong>
                                        </div>
                                        <div class="stats-coverage-track" aria-hidden="true">
                                            <span :style="{ width: metric.percent + '%' }"></span>
                                        </div>
                                        <small>{{ metric.percent }}%</small>
                                    </div>
                                </div>
                                <div v-else class="stats-empty">{{ report.metadataHealthStatus }}</div>
                            </section>
                        </article>
                    </div>
                </section>
            </div>

            <div v-else-if="activeTab === 'duplicates'" class="layout layout--single tab-panel" :style="layoutStyle">
                <section class="panel">
                    <div class="controls duplicate-controls">
                        <div class="field field--narrow">
                            <label for="duplicateRootSelect">Select Folder</label>
                            <select id="duplicateRootSelect" v-model="filters.root" class="select">
                                <option v-for="root in roots" :key="root.key" :value="root.key">{{ root.label || root.key }}</option>
                            </select>
                        </div>

                        <button
                            class="toggle-switch duplicate-near-toggle"
                            :class="{ 'is-active': duplicateIncludeNear }"
                            type="button"
                            :aria-pressed="duplicateIncludeNear"
                            @click="duplicateIncludeNear = !duplicateIncludeNear"
                        >
                            <span class="toggle-switch-track" aria-hidden="true">
                                <span class="toggle-switch-thumb"></span>
                            </span>
                            <span>Near Duplicates</span>
                        </button>

                        <div v-if="duplicateIncludeNear" class="field field--small">
                            <label for="nearThresholdInput">Threshold</label>
                            <input
                                id="nearThresholdInput"
                                v-model.number="duplicateNearThreshold"
                                class="input"
                                type="number"
                                min="0"
                                max="16"
                            />
                        </div>

                        <button class="button duplicate-scan-button" type="button" :disabled="isScanningDuplicates" @click="scanDuplicates">
                            {{ isScanningDuplicates ? 'Scanning...' : 'Scan' }}
                        </button>
                    </div>

                    <div class="results duplicate-results">
                        <div class="meta-row">
                            <div class="meta-group">
                                <span class="status-dot" aria-hidden="true"></span>
                                <span>{{ duplicateStatusText }}</span>
                            </div>
                            <div class="meta-actions">
                                <div class="count-badge">
                                    {{ duplicateCountText }}<span v-if="selectedCount"> / {{ selectedCount }} selected</span>
                                </div>
                                <button
                                    v-if="canCompareSelection"
                                    class="button button--compact"
                                    type="button"
                                    @click="openCompareSelection"
                                >
                                    Compare
                                </button>
                                <button
                                    v-if="duplicateGroups.length"
                                    class="button button--compact"
                                    type="button"
                                    @click="selectAllDuplicateGroupsExcept('newest', $event)"
                                >
                                    All but newest
                                </button>
                                <button
                                    v-if="duplicateGroups.length"
                                    class="button button--compact"
                                    type="button"
                                    @click="selectAllDuplicateGroupsExcept('largest', $event)"
                                >
                                    All but largest
                                </button>
                                <button
                                    v-if="selectedCount > 0"
                                    class="button button--compact button--danger"
                                    type="button"
                                    title="Delete selected media. Hold Shift while clicking to permanently delete without confirmation."
                                    :disabled="isDeleting"
                                    @click="requestDeleteSelected"
                                >
                                    {{ selectedCount > 1 ? 'Delete ' + selectedCount : 'Delete' }}
                                </button>
                                <details v-if="selectedCount > 0 || duplicateGroups.length" class="action-menu">
                                    <summary>Tools</summary>
                                    <div class="action-menu-panel">
                                        <button v-if="selectedCount > 0" type="button" @click="copySelectedPaths">Copy Paths</button>
                                        <button v-if="duplicateGroups.length" type="button" @click="exportDuplicateGroups('json')">Export JSON</button>
                                        <button v-if="duplicateGroups.length" type="button" @click="exportDuplicateGroups('csv')">Export CSV</button>
                                    </div>
                                </details>
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

                        <div v-if="isScanningDuplicates || duplicateScanProgress > 0" class="duplicate-progress" role="progressbar" :aria-valuenow="duplicateScanProgress" aria-valuemin="0" aria-valuemax="100">
                            <div class="duplicate-progress-track">
                                <div class="duplicate-progress-fill" :style="{ width: duplicateScanProgress + '%' }"></div>
                            </div>
                            <div class="duplicate-progress-meta">
                                <span>{{ duplicateScanPhase || 'scan' }}</span>
                                <span>{{ duplicateScanProgressText }}</span>
                            </div>
                        </div>

                        <div class="duplicate-list" aria-live="polite">
                            <div v-if="!duplicateGroups.length" class="empty">Duplicate groups will appear here after a scan.</div>
                            <article v-for="group in duplicateGroups" :key="group.kind + ':' + group.key" class="duplicate-group">
                                <div class="duplicate-group-header">
                                    <div>
                                        <h2 class="duplicate-title">{{ duplicateKindLabel(group.kind) }}</h2>
                                        <div class="duplicate-subtitle">{{ duplicateGroupSubtitle(group) }}</div>
                                    </div>
                                    <div class="duplicate-group-actions">
                                        <button type="button" class="duplicate-action" @click="selectDuplicateGroupPaths(group, $event)">Select all</button>
                                        <button type="button" class="duplicate-action" @click="selectDuplicateGroupExcept(group, 'newest', $event)">All but newest</button>
                                        <button type="button" class="duplicate-action" @click="selectDuplicateGroupExcept(group, 'largest', $event)">All but largest</button>
                                        <span class="duplicate-kind" :class="'duplicate-kind--' + group.kind">{{ group.kind }}</span>
                                    </div>
                                </div>

                                <div class="duplicate-assets">
                                    <button
                                        v-for="asset in group.assets"
                                        :key="asset.path"
                                        class="duplicate-asset"
                                        :class="{ 'is-selected': selectedPathSetHas(asset.path) }"
                                        type="button"
                                        @click="selectDuplicateAsset(asset, $event)"
                                    >
                                        <span class="duplicate-thumb">
                                            <img :src="thumbUrl(asset)" :alt="asset.name" loading="lazy" @error="markDuplicateThumbFailed" />
                                            <span class="duplicate-thumb-fallback">{{ asset.extension || 'file' }}</span>
                                            <span v-if="metadataBadges(asset).length" class="asset-metadata-badges">
                                                <span
                                                    v-for="badge in metadataBadges(asset)"
                                                    :key="badge.key"
                                                    class="asset-metadata-badge"
                                                    :class="'asset-metadata-badge--' + badge.key"
                                                >
                                                    {{ badge.label }}
                                                </span>
                                            </span>
                                        </span>
                                        <span class="duplicate-asset-name">{{ asset.name }}</span>
                                        <span class="duplicate-asset-path">{{ asset.relative_path }}</span>
                                    </button>
                                </div>
                            </article>
                        </div>
                    </div>
                </section>
            </div>
        </div>
    `,
}).mount("#app");
