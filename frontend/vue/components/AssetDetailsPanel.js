import { computed, inject, ref, watch } from '/vendor/vue.esm-browser.prod.js';
import { formatBytes, formatDate } from '/vue/formatters.js';
import { API, buildQuery, fileUrl } from '/vue/api.js';
import { showToast } from '/vue/components/ToastHost.js';

/** Clipboard write with a textarea fallback for contexts that refuse navigator.clipboard. */
async function writeClipboard(text) {
  try {
    await navigator.clipboard.writeText(text);
    return;
  } catch (error) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.appendChild(area);
    area.select();
    const copied = document.execCommand('copy');
    area.remove();
    if (!copied) throw error;
  }
}
import { buildMetadataSummary } from '/vue/metadataFields.js';
import { LIBRARY_KEY, searchToken } from '/vue/composables/useLibraryExtras.js';
import { NsfwOverlay } from '/vue/components/NsfwOverlay.js';

export const AssetDetailsPanel = {
  name: 'AssetDetailsPanel',
  components: { NsfwOverlay },
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
  emits: [
    'delete-asset',
    'open-folder',
    'repair-metadata',
    'resize-preview',
    'toggle-favorite',
    'filter-by',
    'open-sweep',
    'send-to'
  ],
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

    const generationSource = computed(() => {
      const embedded = (props.assetDetails || props.selectedAsset)?.metadata?.metadata || {};
      return embedded.bubba_metadata || embedded.generation || null;
    });
    const hasLoras = computed(() => {
      const loras = generationSource.value?.loras;
      return Array.isArray(loras) ? loras.length > 0 : Boolean(String(loras || '').trim());
    });
    const canCopyParameters = computed(() => {
      const badges = props.assetDetails?.metadata_badges || props.selectedAsset?.metadata_badges || [];
      return Boolean(generationSource.value) || badges.some((badge) => badge?.key === 'parameters');
    });
    const COPY_LABELS = {
      workflow: 'ComfyUI workflow (paste it into the canvas)',
      parameters: 'A1111 parameters',
      lora_stack: 'LoRA stack'
    };
    const copyFormat = async (kind) => {
      const asset = props.selectedAsset;
      if (!asset?.path) return;
      try {
        const response = await fetch(buildQuery(API.copyFormats, { path: asset.path }));
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || payload.description || 'Could not read this image.');
        const value = payload[kind];
        if (!value) {
          showToast({ message: `This image has no ${COPY_LABELS[kind]}.`, tone: 'warn' });
          return;
        }
        await writeClipboard(value);
        showToast({ message: `Copied ${COPY_LABELS[kind]}.`, tone: 'success' });
      } catch (error) {
        showToast({ message: error?.message || 'Copy failed.', tone: 'error' });
      }
    };

    const revealed = ref(false);
    watch(
      () => props.selectedAsset?.path,
      () => {
        revealed.value = false;
      }
    );
    const previewBlur = computed(() => {
      if (!library || revealed.value) return null;
      const asset = props.assetDetails?.path === props.selectedAsset?.path ? props.assetDetails : props.selectedAsset;
      return library.blurFor(asset);
    });
    const nsfwVerdict = computed(() => (props.assetDetails || props.selectedAsset)?.nsfw || null);

    const isFavorite = computed(() => Boolean(props.assetDetails?.favorite ?? props.selectedAsset?.favorite));

    return {
      library,
      chipQuery,
      copyFormat,
      revealed,
      previewBlur,
      nsfwVerdict,
      hasLoras,
      canCopyParameters,
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
                    <img v-if="selectedAsset && isPreviewableAsset" :key="selectedAsset.path" :src="fileUrl(selectedAsset.path)" :alt="selectedAsset.name" :class="{ 'review-blurred': previewBlur && previewBlur.mode === 'image' }" />
                    <NsfwOverlay v-if="selectedAsset && isPreviewableAsset && previewBlur && previewBlur.mode === 'regions'" :key="'nsfw-' + selectedAsset.path" fit="contain" :regions="previewBlur.regions" />
                    <button v-if="selectedAsset && isPreviewableAsset && (previewBlur || revealed)" type="button" class="nsfw-reveal" :aria-pressed="revealed" @click="revealed = !revealed">{{ revealed ? 'Hide' : 'Reveal' }}</button>
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
                    <button v-if="metadataSummary.isSweep" type="button" class="preview-action" title="Show every cell of this XY sweep as a labelled grid" @click="$emit('open-sweep', selectedAsset)">▦ Sweep grid</button>
                    <button
                        v-if="library"
                        type="button"
                        class="preview-action preview-action-comfy"
                        :disabled="!hasWorkflow || library.comfyBusy"
                        :title="hasWorkflow ? 'Queue the embedded workflow in ComfyUI again (same seed)' : 'No embedded ComfyUI workflow in this image'"
                        @click="library.queueInComfy(selectedAsset)"
                    >{{ library.comfyBusy ? 'Queuing…' : '↻ Re-queue in ComfyUI' }}</button>
                    <button type="button" class="preview-action" title="Send to Discord or Immich" @click="$emit('send-to', selectedAsset)">Send to…</button>
                    <button type="button" class="preview-action" @click="openFull">Open full size</button>
                    <button type="button" class="preview-action" @click="$emit('open-folder', selectedAsset)">Open folder</button>
                    <button type="button" class="preview-action" @click="copyText(selectedAsset.path)">Copy path</button>
                    <details class="action-menu"><summary>Metadata actions</summary><div class="action-menu-panel">
                    <button type="button" class="preview-action" :disabled="!metadataSummary.copyPromptValue" @click="copyText(metadataSummary.copyPromptValue)">Copy prompt</button>
                    <button type="button" class="preview-action" :disabled="!metadataSummary.copySeedValue" @click="copyText(metadataSummary.copySeedValue)">Copy seed</button>
                    <button type="button" class="preview-action" :disabled="!hasWorkflow" title="Copy the ComfyUI workflow JSON; paste it onto the ComfyUI canvas to load the graph" @click="copyFormat('workflow')">Copy for ComfyUI</button>
                    <button type="button" class="preview-action" :disabled="!canCopyParameters" title="Copy an A1111-style parameters block" @click="copyFormat('parameters')">Copy for A1111</button>
                    <button type="button" class="preview-action" :disabled="!hasLoras" title="Copy the LoRAs as lora tags with their strengths" @click="copyFormat('lora_stack')">Copy LoRA stack</button>
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
                    <div v-if="nsfwVerdict" class="kv">
                        <div class="kv-key">content</div>
                        <div class="kv-value"><span class="nsfw-pill" :class="'nsfw-pill--' + nsfwVerdict.rating">{{ nsfwVerdict.rating }}</span> {{ Math.round(nsfwVerdict.score * 100) }}% · {{ nsfwVerdict.source === 'metadata' ? 'rated at save time' : 'viewer scan' }}</div>
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
