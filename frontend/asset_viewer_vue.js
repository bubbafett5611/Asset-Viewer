import { createApp } from "https://unpkg.com/vue@3/dist/vue.esm-browser.prod.js";
import { AssetsView } from "/vue/components/AssetsView.js";
import { TagsView } from "/vue/components/TagsView.js";
import { DuplicatesView } from "/vue/components/DuplicatesView.js";
import { StatsView } from "/vue/components/StatsView.js";
import { SettingsView } from "/vue/components/SettingsView.js";
import { useAssetViewerState } from "/vue/useAssetViewer.js";

createApp({
    components: {
        AssetsView,
        TagsView,
        DuplicatesView,
        StatsView,
        SettingsView,
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
                    <button class="tab-button" :class="{ 'is-active': activeTab === 'assets' }" type="button" :aria-pressed="activeTab === 'assets'" @click="activeTab = 'assets'">Media</button>
                    <button class="tab-button" :class="{ 'is-active': activeTab === 'tags' }" type="button" :aria-pressed="activeTab === 'tags'" @click="activeTab = 'tags'">Tag Browser</button>
                    <button class="tab-button" :class="{ 'is-active': activeTab === 'duplicates' }" type="button" :aria-pressed="activeTab === 'duplicates'" @click="activeTab = 'duplicates'">Duplicates</button>
                    <button class="tab-button" :class="{ 'is-active': activeTab === 'stats' }" type="button" :aria-pressed="activeTab === 'stats'" @click="activeTab = 'stats'">Stats</button>
                    <button class="tab-button" :class="{ 'is-active': activeTab === 'settings' }" type="button" :aria-pressed="activeTab === 'settings'" @click="activeTab = 'settings'">Settings</button>
                </nav>
            </header>

            <AssetsView
                v-if="activeTab === 'assets'"
                :layout-style="layoutStyle"
                :filters="filters"
                :roots="roots"
                :metadata-filter-list="metadataFilterList"
                :assets="assets"
                :selected-asset="selectedAsset"
                :details="details"
                :selected-path="selectedPath"
                :selected-path-set-has="selectedPathSetHas"
                :blur-thumbnails="blurThumbnails"
                :status-text="statusText"
                :selected-count="selectedCount"
                :delete-count="deleteCount"
                :is-loading="isLoading"
                :is-loading-more="isLoadingMore"
                :is-deleting="isDeleting"
                :has-more="hasMore"
                :current-root-label="currentRootLabel"
                :density-class="densityClass"
                :asset-list-style="assetListStyle"
                :should-virtualize="shouldVirtualize"
                :visible-assets="visibleAssets"
                :virtual-spacer-style="virtualSpacerStyle"
                :virtual-window-style="virtualWindowStyle"
                :asset-list-ref="setAssetListRef"
                :search-input-ref="setSearchInputRef"
                :on-asset-list-scroll="onAssetListScroll"
                :refresh-assets="refreshAssets"
                :load-more="loadMore"
                :select-asset="selectAsset"
                :clear-selection="clearSelection"
                :copy-selected-paths="copySelectedPaths"
                :export-selected-assets="exportSelectedAssets"
                :open-compare-selection="openCompareSelection"
                :request-delete-selected="requestDeleteSelected"
                :request-delete-asset="requestDeleteAsset"
                :hide-delete-confirm="hideDeleteConfirm"
                :confirm-delete="confirmDelete"
                :safe-delete="safeDelete"
                :start-details-resize="startDetailsResize"
                :start-preview-resize="startPreviewResize"
                :open-containing-folder="openContainingFolder"
                :repair-selected-metadata="repairSelectedMetadata"
            />

            <TagsView
                v-else-if="activeTab === 'tags'"
                :layout-style="layoutStyle"
                :tag-filters="tagFilters"
                :tag-categories="tagCategories"
                :tag-status-text="tagStatusText"
                :tag-count-text="tagCountText"
                :visible-tags="visibleTags"
                :selected-tag="selectedTag"
                :selected-tag-aliases="selectedTagAliases"
                :selected-tag-examples="selectedTagExamples"
                :tag-examples-loading="tagExamplesLoading"
                :is-loading-tags="isLoadingTags"
                :tag-has-more="tagHasMore"
                :is-tag-favorite="isTagFavorite"
                :fetch-tags="fetchTags"
                :select-tag="selectTag"
                :toggle-tag-favorite="toggleTagFavorite"
                :load-more-tags="loadMoreTags"
                :example-image-url="exampleImageUrl"
                :tag-search-url="tagSearchUrl"
                :start-details-resize="startDetailsResize"
            />

            <DuplicatesView
                v-else-if="activeTab === 'duplicates'"
                :layout-style="layoutStyle"
                :roots="roots"
                :filters="filters"
                :duplicate-settings="duplicateSettings"
                :is-scanning-duplicates="isScanningDuplicates"
                :duplicate-status-text="duplicateStatusText"
                :duplicate-count-text="duplicateCountText"
                :duplicate-scan-progress="duplicateScanProgress"
                :duplicate-scan-phase="duplicateScanPhase"
                :duplicate-scan-progress-text="duplicateScanProgressText"
                :duplicate-groups="duplicateGroups"
                :can-compare-selection="canCompareSelection"
                :selected-count="selectedCount"
                :delete-count="deleteCount"
                :is-deleting="isDeleting"
                :selected-path-set-has="selectedPathSetHas"
                :scan-duplicates="scanDuplicates"
                :open-compare-selection="openCompareSelection"
                :select-all-duplicate-groups-except="selectAllDuplicateGroupsExcept"
                :copy-selected-paths="copySelectedPaths"
                :export-duplicate-groups="exportDuplicateGroups"
                :request-delete-selected="requestDeleteSelected"
                :clear-selection="clearSelection"
                :select-duplicate-asset="selectDuplicateAsset"
                :select-duplicate-group-paths="selectDuplicateGroupPaths"
                :select-duplicate-group-except="selectDuplicateGroupExcept"
                :duplicate-kind-label="duplicateKindLabel"
                :duplicate-group-subtitle="duplicateGroupSubtitle"
                :mark-duplicate-thumb-failed="markDuplicateThumbFailed"
                :start-details-resize="startDetailsResize"
            />

            <StatsView
                v-else-if="activeTab === 'stats'"
                :layout-style="layoutStyle"
                :stats-root-reports="statsRootReports"
                :is-loading-any-folder-stats="isLoadingAnyFolderStats"
                :is-loading-any-metadata-health="isLoadingAnyMetadataHealth"
                :fetch-folder-stats="fetchFolderStats"
                :fetch-metadata-health="fetchMetadataHealth"
                :fetch-root-folder-stats="fetchRootFolderStats"
                :fetch-root-metadata-health="fetchRootMetadataHealth"
                :export-metadata-health="exportMetadataHealth"
            />

            <SettingsView
                v-else-if="activeTab === 'settings'"
                :layout-style="layoutStyle"
                :settings-sections="settingsSections"
                :settings-status="settingsStatus"
                :is-saving-settings="isSavingSettings"
                :settings-field-value="settingsFieldValue"
                :settings-list-value="settingsListValue"
                :settings-list-draft-value="settingsListDraftValue"
                :update-settings-list-draft="updateSettingsListDraft"
                :update-setting="updateSetting"
                :update-string-list-item="updateStringListItem"
                :add-string-list-setting="addStringListSetting"
                :remove-string-list-item="removeStringListItem"
            />
        </div>
    `,
}).mount("#app");
