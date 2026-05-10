import { thumbUrl } from '/vue/api.js';

function metadataBadges(asset) {
  return Array.isArray(asset?.metadata_badges) ? asset.metadata_badges : [];
}

export const DuplicatesView = {
  name: 'DuplicatesView',
  props: {
    layoutStyle: {
      type: Object,
      required: true
    },
    roots: {
      type: Array,
      required: true
    },
    filters: {
      type: Object,
      required: true
    },
    duplicateSettings: {
      type: Object,
      required: true
    },
    isScanningDuplicates: {
      type: Boolean,
      default: false
    },
    isCancellingDuplicateScan: {
      type: Boolean,
      default: false
    },
    duplicateStatusText: {
      type: String,
      required: true
    },
    duplicateTaskId: {
      type: String,
      default: ''
    },
    duplicateTaskStatusText: {
      type: String,
      default: ''
    },
    duplicateCountText: {
      type: String,
      required: true
    },
    duplicateScanProgress: {
      type: Number,
      required: true
    },
    duplicateScanPhase: {
      type: String,
      required: true
    },
    duplicateScanProgressText: {
      type: String,
      required: true
    },
    duplicateGroups: {
      type: Array,
      required: true
    },
    canCompareSelection: {
      type: Boolean,
      default: false
    },
    selectedCount: {
      type: Number,
      required: true
    },
    deleteCount: {
      type: Number,
      required: true
    },
    isDeleting: {
      type: Boolean,
      default: false
    },
    selectedPathSetHas: {
      type: Function,
      required: true
    },
    scanDuplicates: {
      type: Function,
      required: true
    },
    cancelDuplicateScan: {
      type: Function,
      required: true
    },
    openCompareSelection: {
      type: Function,
      required: true
    },
    selectAllDuplicateGroupsExcept: {
      type: Function,
      required: true
    },
    copySelectedPaths: {
      type: Function,
      required: true
    },
    exportDuplicateGroups: {
      type: Function,
      required: true
    },
    requestDeleteSelected: {
      type: Function,
      required: true
    },
    clearSelection: {
      type: Function,
      required: true
    },
    selectDuplicateAsset: {
      type: Function,
      required: true
    },
    selectDuplicateGroupPaths: {
      type: Function,
      required: true
    },
    selectDuplicateGroupExcept: {
      type: Function,
      required: true
    },
    duplicateKindLabel: {
      type: Function,
      required: true
    },
    duplicateGroupSubtitle: {
      type: Function,
      required: true
    },
    markDuplicateThumbFailed: {
      type: Function,
      required: true
    },
    startDetailsResize: {
      type: Function,
      required: true
    }
  },
  setup() {
    return {
      thumbUrl,
      metadataBadges
    };
  },
  template: `
        <div class="layout layout--single duplicates-layout tab-panel" :style="layoutStyle">
            <section class="panel duplicates-panel">
                <div class="controls duplicate-controls duplicates-controls">
                    <div class="field field--narrow">
                        <label for="duplicateRootSelect">Select Folder</label>
                        <select id="duplicateRootSelect" v-model="filters.root" class="select">
                            <option v-for="root in roots" :key="root.key" :value="root.key">{{ root.label || root.key }}</option>
                        </select>
                    </div>

                    <button
                        class="toggle-switch duplicate-near-toggle"
                        :class="{ 'is-active': duplicateSettings.includeNear }"
                        type="button"
                        :aria-pressed="duplicateSettings.includeNear"
                        @click="duplicateSettings.includeNear = !duplicateSettings.includeNear"
                    >
                        <span class="toggle-switch-track" aria-hidden="true">
                            <span class="toggle-switch-thumb"></span>
                        </span>
                        <span>Near Duplicates</span>
                    </button>

                    <div v-if="duplicateSettings.includeNear" class="field field--small">
                        <label for="nearThresholdInput">Threshold</label>
                        <input
                            id="nearThresholdInput"
                            v-model.number="duplicateSettings.nearThreshold"
                            class="input"
                            type="number"
                            min="0"
                            max="16"
                        />
                    </div>

                    <button class="button duplicate-scan-button" type="button" :disabled="isScanningDuplicates" @click="scanDuplicates">
                        {{ isScanningDuplicates ? 'Scanning...' : 'Scan' }}
                    </button>
                    <button class="button duplicate-scan-button button--ghost" type="button" :disabled="!isScanningDuplicates || isCancellingDuplicateScan || !duplicateTaskId" @click="cancelDuplicateScan">
                        {{ isCancellingDuplicateScan ? 'Cancelling...' : 'Cancel' }}
                    </button>
                </div>

                <div class="results duplicate-results duplicates-results">
                    <div class="meta-row duplicates-meta-row">
                        <div class="meta-group">
                            <span class="status-dot" aria-hidden="true"></span>
                            <span>{{ duplicateStatusText }}</span>
                        </div>
                        <div v-if="duplicateTaskId" class="meta-group meta-group--subtle">
                            <span>Task {{ duplicateTaskId.slice(0, 8) }}</span>
                            <span v-if="duplicateTaskStatusText">{{ duplicateTaskStatusText }}</span>
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
                            <details v-if="selectedCount > 0 || duplicateGroups.length" class="action-menu duplicates-action-menu">
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
    `
};
