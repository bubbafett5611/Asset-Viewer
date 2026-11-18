import { computed, inject } from '/vendor/vue.esm-browser.prod.js';
import { formatBytes, formatDate } from '/vue/formatters.js';
import { fileUrl } from '/vue/api.js';
import { buildMetadataSummary } from '/vue/metadataFields.js';
import { LIBRARY_KEY, searchToken } from '/vue/composables/useLibraryExtras.js';

export const AssetDetailsPanel = {
  name: 'AssetDetailsPanel',
  props: {
    selectedAsset: {
      type: Object,
      default: null
    },
    assetDetails: {
      type: Object,
      default: null
    }
  },
  emits: ['delete-asset', 'open-folder', 'repair-metadata', 'resize-preview', 'toggle-favorite', 'filter-by'],
  setup(props) {
    const previewableExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff']);
    const videoExtensions = new Set(['.mp4']);
    const isPreviewableAsset = computed(() =>
      previewableExtensions.has(String(props.selectedAsset?.extension || '').toLowerCase())
    );
    const canRepairMetadata = computed(() => String(props.selectedAsset?.extension || '').toLowerCase() === '.png');
    const isVideoAsset = computed(() =>
      videoExtensions.has(String(props.selectedAsset?.extension || '').toLowerCase())
    );

    const metadataSummary = computed(() => buildMetadataSummary(props.selectedAsset, props.assetDetails));

    const openFull = () => {
      if (!props.selectedAsset) {
        return;
      }
      window.open(fileUrl(props.selectedAsset.path), '_blank', 'noopener,noreferrer');
    };

    const copyText = async (value) => {
      if (!value) {
        return;
      }
      try {
        await navigator.clipboard.writeText(String(value));
      } catch {
        // no-op
      }
    };

    const library = inject(LIBRARY_KEY, null);
    const CHIP_FIELDS = { model: 'model', seed: 'seed', sampler: 'sampler', scheduler: 'scheduler', loras: 'lora' };
    const chipQuery = (label, value) => {
      if (!CHIP_FIELDS[label]) return String(value);
      const clean =
        label === 'loras'
          ? String(value)
              .split(/[\\/]/)
              .pop()
              .replace(/\.(safetensors|ckpt|pt|pth)$/i, '')
          : value;
      return searchToken(CHIP_FIELDS[label], clean, { exact: label !== 'seed' });
    };
    const hasWorkflow = computed(() => {
      const badges = props.assetDetails?.metadata_badges || props.selectedAsset?.metadata_badges || [];
      return (
        String(props.selectedAsset?.extension || '').toLowerCase() === '.png' &&
        badges.some((badge) => badge?.key === 'workflow')
      );
    });

    const isFavorite = computed(() => Boolean(props.assetDetails?.favorite ?? props.selectedAsset?.favorite));

    return {
      library,
      chipQuery,
      hasWorkflow,
      isFavorite,
      fileUrl,
      formatBytes,
      formatDate,
      isPreviewableAsset,
      isVideoAsset,
      canRepairMetadata,
      metadataSummary,
      openFull,
      copyText
    };
  },
  template: `
        <aside class="panel asset-details-panel details">
            <div class="details-header">
                <div class="details-title-row">
                    <h2>Inspector</h2>
                    <span v-if="selectedAsset" :class="metadataSummary.metadataBadgeClass">{{ metadataSummary.metadataBadgeText }}</span>
                </div>
                <p class="details-subtitle">{{ selectedAsset ? selectedAsset.name : 'Select an item to inspect file info and embedded metadata.' }}</p>
            </div>

            <div class="preview">
                <div class="preview-frame">
                    <img v-if="selectedAsset && isPreviewableAsset" :src="fileUrl(selectedAsset.path)" :alt="selectedAsset.name" />
                    <video
                        v-else-if="selectedAsset && isVideoAsset"
                        :src="fileUrl(selectedAsset.path)"
                        :aria-label="selectedAsset.name"
                        controls
                        playsinline
                        preload="metadata"
                    ></video>
                    <div v-else-if="selectedAsset" class="preview-empty">No media preview</div>
                    <div v-else class="preview-empty">No media selected</div>
                </div>
                <div v-if="selectedAsset" class="preview-actions">
                    <button
                        type="button"
                        class="preview-action preview-action-favorite"
                        :class="{ 'is-active': isFavorite }"
                        :aria-pressed="isFavorite"
                        title="Toggle favorite (F)"
                        @click="$emit('toggle-favorite', selectedAsset)"
                    >{{ isFavorite ? '★ Favorited' : '☆ Favorite' }}</button>
                    <button v-if="library && isPreviewableAsset" type="button" class="preview-action" title="Show visually similar images from this library" @click="library.findSimilar(selectedAsset)">≈ Find similar</button>
                    <button
                        v-if="library"
                        type="button"
                        class="preview-action preview-action-comfy"
                        :disabled="!hasWorkflow || library.comfyBusy"
                        :title="hasWorkflow ? 'Queue the embedded workflow in ComfyUI again (same seed)' : 'No embedded ComfyUI workflow in this image'"
                        @click="library.queueInComfy(selectedAsset)"
                    >{{ library.comfyBusy ? 'Queuing…' : '↻ Re-queue in ComfyUI' }}</button>
                    <button type="button" class="preview-action" @click="openFull">Open full size</button>
                    <button type="button" class="preview-action" @click="$emit('open-folder', selectedAsset)">Open folder</button>
                    <button type="button" class="preview-action" @click="copyText(selectedAsset.path)">Copy path</button>
                    <details class="action-menu"><summary>Metadata actions</summary><div class="action-menu-panel">
                    <button type="button" class="preview-action" :disabled="!metadataSummary.copyPromptValue" @click="copyText(metadataSummary.copyPromptValue)">Copy prompt</button>
                    <button type="button" class="preview-action" :disabled="!metadataSummary.copySeedValue" @click="copyText(metadataSummary.copySeedValue)">Copy seed</button>
                    <button type="button" class="preview-action" :disabled="!canRepairMetadata" @click="$emit('repair-metadata', selectedAsset)">Repair metadata</button>
                    </div></details>
                    <button
                        type="button"
                        class="preview-action preview-action-danger"
                        title="Delete this media item. Hold Shift while clicking to permanently delete without confirmation."
                        @click="$emit('delete-asset', selectedAsset, $event)"
                    >Delete</button>
                </div>
            </div>
            <div
                class="preview-resizer"
                role="separator"
                aria-orientation="horizontal"
                aria-label="Resize preview height"
                title="Drag to resize preview height"
                tabindex="0"
                @keydown.stop="$emit('resize-preview', $event)"
                @mousedown="$emit('resize-preview', $event)"
            ></div>

            <div class="details-scroll">
                <div v-if="selectedAsset" class="details-grid">
                    <details open><summary>File</summary>
                    <div class="kv" v-for="pair in metadataSummary.filePairs" :key="'file-' + pair[0]">
                        <div class="kv-key">{{ pair[0] }}</div>
                        <div class="kv-value">{{ pair[1] }}</div>
                    </div>

                    </details>
                    <details open v-if="metadataSummary.generationPairs.length > 0">
                        <summary>Generation</summary>
                        <div class="kv" v-for="pair in metadataSummary.generationPairs" :key="'gen-' + pair[0]">
                            <div class="kv-key">{{ pair[0] }}</div>
                            <div v-if="pair[2] && pair[2].length" class="kv-value kv-value--chips">
                                <button
                                    v-for="chip in pair[2]"
                                    :key="chip.label"
                                    type="button"
                                    class="kv-filter-chip"
                                    :title="'Show all media matching ' + chip.value"
                                    @click="$emit('filter-by', chipQuery(pair[0], chip.value))"
                                >
                                    <span>{{ chip.label }}</span>
                                    <svg viewBox="0 0 16 16" aria-hidden="true"><circle cx="7" cy="7" r="4.2" fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10.2 10.2 13.5 13.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"/></svg>
                                </button>
                            </div>
                            <div v-else class="kv-value">{{ pair[1] }}</div>
                        </div>
                    </details>

                    <details v-if="metadataSummary.extraBubbaPairs.length > 0">
                        <summary>Bubba extra</summary>
                        <div class="kv" v-for="pair in metadataSummary.extraBubbaPairs" :key="'bubba-' + pair[0]">
                            <div class="kv-key">{{ pair[0] }}</div>
                            <div class="kv-value">{{ pair[1] }}</div>
                        </div>
                    </details>

                    <details v-if="metadataSummary.metadataPairs.length > 0">
                        <summary>Embedded metadata</summary>
                        <div class="kv" v-for="pair in metadataSummary.metadataPairs" :key="'meta-' + pair[0]">
                            <div class="kv-key">{{ pair[0] }}</div>
                            <div class="kv-value">{{ pair[1] }}</div>
                        </div>
                    </details>

                    <div v-if="metadataSummary.generationPairs.length === 0 && metadataSummary.metadataPairs.length === 0" class="empty-inline">
                        No metadata detected.
                    </div>
                </div>
                <div v-else class="empty">Select media to inspect fields.</div>
            </div>
        </aside>
    `
};
