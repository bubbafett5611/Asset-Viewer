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

            <div v-if="isShortcutsModalVisible" class="shortcuts-modal" @click.self="hideShortcutsModal">
                <div class="shortcuts-card" role="dialog" aria-modal="true" aria-labelledby="shortcutsTitle">
                    <div class="shortcuts-header">
                        <div>
                            <h2 id="shortcutsTitle">Keyboard Shortcuts</h2>
                            <p>Shortcuts apply when you are not typing in a field.</p>
                        </div>
                        <button class="button button--compact button--ghost" type="button" @click="hideShortcutsModal">Close</button>
                    </div>
                    <div class="shortcuts-grid">
                        <div class="shortcuts-section">
                            <h3>Navigation</h3>
                            <div><kbd>M</kbd><span>Media tab</span></div>
                            <div><kbd>T</kbd><span>Tag Browser tab</span></div>
                            <div><kbd>D</kbd><span>Duplicates tab</span></div>
                            <div><kbd>S</kbd><span>Stats tab</span></div>
                            <div><kbd>?</kbd><span>Open this shortcut reference</span></div>
                            <div><kbd>Esc</kbd><span>Close modal or clear selection</span></div>
                        </div>
                        <div class="shortcuts-section">
                            <h3>Media</h3>
                            <div><kbd>Arrows</kbd><span>Move media selection</span></div>
                            <div><kbd>Shift+Arrows</kbd><span>Extend media selection while moving</span></div>
                            <div><kbd>Space</kbd><span>Toggle selected media into multi-selection</span></div>
                            <div><kbd>Enter</kbd><span>Open selected media full-size</span></div>
                            <div><kbd>Ctrl+C</kbd><span>Copy selected image to clipboard</span></div>
                            <div><kbd>Ctrl+Shift+C</kbd><span>Copy selected file path(s)</span></div>
                            <div><kbd>Ctrl+O</kbd><span>Open selected media full-size</span></div>
                            <div><kbd>Ctrl+Shift+O</kbd><span>Open containing folder</span></div>
                            <div><kbd>B</kbd><span>Toggle thumbnail blur</span></div>
                            <div><kbd>Delete</kbd><span>Delete selected media</span></div>
                            <div><kbd>Shift+Delete</kbd><span>Permanently delete selected media</span></div>
                        </div>
                        <div class="shortcuts-section">
                            <h3>Duplicates</h3>
                            <div><kbd>Arrows</kbd><span>Move duplicate media selection</span></div>
                            <div><kbd>Shift+Arrows</kbd><span>Extend duplicate selection while moving</span></div>
                            <div><kbd>Space</kbd><span>Toggle selected duplicate media</span></div>
                            <div><kbd>Ctrl+C</kbd><span>Copy selected duplicate path(s)</span></div>
                            <div><kbd>Ctrl+Shift+C</kbd><span>Copy selected duplicate path(s)</span></div>
                            <div><kbd>Ctrl+A</kbd><span>Select all duplicate media</span></div>
                            <div><kbd>Ctrl+E</kbd><span>Export duplicate groups</span></div>
                            <div><kbd>Ctrl+Shift+D</kbd><span>Run duplicate scan for current root</span></div>
                            <div><kbd>Delete</kbd><span>Delete selected duplicate media</span></div>
                            <div><kbd>Shift+Delete</kbd><span>Permanently delete selected duplicate media</span></div>
                        </div>
                        <div class="shortcuts-section">
                            <h3>Tags</h3>
                            <div><kbd>Up / Down</kbd><span>Move through tag list</span></div>
                            <div><kbd>Enter</kbd><span>Select focused tag row</span></div>
                            <div><kbd>Space</kbd><span>Select focused tag row</span></div>
                            <div><kbd>Ctrl+C</kbd><span>Copy selected tag</span></div>
                            <div><kbd>Ctrl+Shift+F</kbd><span>Favorite or unfavorite selected tag</span></div>
                            <div><kbd>Ctrl+L</kbd><span>Copy selected tag name</span></div>
                            <div><kbd>/</kbd><span>Focus tag search</span></div>
                        </div>
                        <div class="shortcuts-section">
                            <h3>Compare</h3>
                            <div><kbd>Left / Right</kbd><span>Move compare divider</span></div>
                            <div><kbd>Shift+Left / Right</kbd><span>Move compare divider faster</span></div>
                            <div><kbd>Home</kbd><span>Move divider fully left</span></div>
                            <div><kbd>End</kbd><span>Move divider fully right</span></div>
                            <div><kbd>Esc</kbd><span>Close compare modal</span></div>
                        </div>
                        <div class="shortcuts-section">
                            <h3>General</h3>
                            <div><kbd>Ctrl+F</kbd><span>Focus search in Media or Tags</span></div>
                            <div><kbd>Ctrl+A</kbd><span>Select all visible media or duplicate media</span></div>
                            <div><kbd>Ctrl+E</kbd><span>Export media selection or duplicate groups</span></div>
                            <div><kbd>Ctrl+L</kbd><span>Copy selected media or tag name</span></div>
                            <div><kbd>R</kbd><span>Refresh Media, Tags, Stats, or Settings</span></div>
                            <div><kbd>Enter</kbd><span>Add current Settings list item</span></div>
                        </div>
                    </div>
                </div>
            </div>

            <header class="header">
                <div class="header-copy">
                    <h1 class="title">Bubba Media Viewer</h1>
                </div>
                <div class="header-actions">
                    <nav class="tab-nav" aria-label="Viewer sections">
                        <button class="tab-button" :class="{ 'is-active': activeTab === 'assets' }" type="button" :aria-pressed="activeTab === 'assets'" @click="activeTab = 'assets'">Media</button>
                        <button class="tab-button" :class="{ 'is-active': activeTab === 'tags' }" type="button" :aria-pressed="activeTab === 'tags'" @click="activeTab = 'tags'">Tag Browser</button>
                        <button class="tab-button" :class="{ 'is-active': activeTab === 'duplicates' }" type="button" :aria-pressed="activeTab === 'duplicates'" @click="activeTab = 'duplicates'">Duplicates</button>
                        <button class="tab-button" :class="{ 'is-active': activeTab === 'stats' }" type="button" :aria-pressed="activeTab === 'stats'" @click="activeTab = 'stats'">Stats</button>
                        <button class="tab-button" :class="{ 'is-active': activeTab === 'settings' }" type="button" :aria-pressed="activeTab === 'settings'" @click="activeTab = 'settings'">Settings</button>
                    </nav>
                    <button class="shortcut-help-button" type="button" aria-label="Show keyboard shortcuts" title="Keyboard shortcuts (?)" @click="showShortcutsModal">?</button>
                </div>
            </header>

            <div v-if="updateNotice" class="update-banner" role="status" aria-live="polite">
                <div class="update-banner-copy">
                    <strong>Update available:</strong>
                    <span>{{ updateNotice.latestVersion }}</span>
                    <span class="update-banner-current">(current: {{ updateNotice.currentVersion }})</span>
                </div>
                <div class="update-banner-actions">
                    <button class="button button--compact" type="button" @click="openUpdateRelease">View Release</button>
                    <button class="button button--compact button--ghost" type="button" @click="snoozeUpdateNotice">Remind me later</button>
                    <button class="button button--compact button--ghost" type="button" @click="skipUpdateVersion">Skip this version</button>
                </div>
            </div>

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
