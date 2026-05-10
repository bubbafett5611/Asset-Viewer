import { createApp } from '/vendor/vue.esm-browser.prod.js';
import { AssetsView } from '/vue/components/AssetsView.js';
import { TagsView } from '/vue/components/TagsView.js';
import { DuplicatesView } from '/vue/components/DuplicatesView.js';
import { StatsView } from '/vue/components/StatsView.js';
import { SettingsView } from '/vue/components/SettingsView.js';
import { useAssetViewerState } from '/vue/useAssetViewer.js';

createApp({
  components: {
    AssetsView,
    TagsView,
    DuplicatesView,
    StatsView,
    SettingsView
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
                        <button class="button button--compact button--ghost" type="button" :disabled="isDeleting" @click="hideDeleteConfirm">Cancel</button>
                        <button class="button button--compact button--danger" type="button" :disabled="isDeleting" @click="confirmDelete">
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
                v-bind="assetsViewProps"
            />

            <TagsView
                v-else-if="activeTab === 'tags'"
                v-bind="tagsViewProps"
            />

            <DuplicatesView
                v-else-if="activeTab === 'duplicates'"
                v-bind="duplicatesViewProps"
            />

            <StatsView
                v-else-if="activeTab === 'stats'"
                v-bind="statsViewProps"
            />

            <SettingsView
                v-else-if="activeTab === 'settings'"
                v-bind="settingsViewProps"
            />
        </div>
    `
}).mount('#app');
