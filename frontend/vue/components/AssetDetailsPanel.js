import { computed } from '/vendor/vue.esm-browser.prod.js';
import { formatBytes, formatDate } from '/vue/formatters.js';
import { fileUrl } from '/vue/api.js';

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

    const hasValue = (value) => {
      if (value === null || value === undefined) {
        return false;
      }
      if (typeof value === 'string') {
        return value.trim().length > 0;
      }
      if (Array.isArray(value)) {
        return value.length > 0;
      }
      return true;
    };

    const metadataSummary = computed(() => {
      if (!props.selectedAsset) {
        return {
          filePairs: [],
          generationPairs: [],
          extraBubbaPairs: [],
          metadataPairs: [],
          metadataBadgeClass: 'metadata-status metadata-status-none',
          metadataBadgeText: 'No metadata detected',
          copyPromptValue: '',
          copySeedValue: ''
        };
      }

      const details =
        props.assetDetails && typeof props.assetDetails === 'object' ? props.assetDetails : props.selectedAsset;
      const metadata = details.metadata && typeof details.metadata === 'object' ? details.metadata : {};
      const embedded = metadata.metadata && typeof metadata.metadata === 'object' ? metadata.metadata : {};
      const bubbaMetadata =
        embedded.bubba_metadata && typeof embedded.bubba_metadata === 'object' ? embedded.bubba_metadata : null;
      const extractedGeneration =
        embedded.generation && typeof embedded.generation === 'object' ? embedded.generation : null;
      const generationSource = bubbaMetadata || extractedGeneration;

      const filePairs = [
        ['name', details.name],
        ['path', details.path],
        ['relative', details.relative_path],
        ['extension', details.extension || '(none)'],
        ['size', formatBytes(details.size_bytes)],
        ['modified', formatDate(details.modified_ts)]
      ];

      const generationPairs = [];
      if (generationSource) {
        const addGenerationField = (label, key) => {
          if (Object.prototype.hasOwnProperty.call(generationSource, key) && hasValue(generationSource[key])) {
            const value = generationSource[key];
            generationPairs.push([
              label,
              Array.isArray(value)
                ? value.join(', ')
                : typeof value === 'string'
                  ? value
                  : JSON.stringify(value, null, 2)
            ]);
          }
        };

        const addGenerationFieldFromKeys = (label, keys) => {
          for (const key of keys) {
            if (Object.prototype.hasOwnProperty.call(generationSource, key) && hasValue(generationSource[key])) {
              addGenerationField(label, key);
              return;
            }
          }
        };

        addGenerationFieldFromKeys('model', [
          'model_name',
          'model',
          'ckpt_name',
          'checkpoint',
          'checkpoint_name',
          'sd_model_name',
          'base_model'
        ]);
        addGenerationFieldFromKeys('seed', ['seed', 'seeds']);
        addGenerationFieldFromKeys('steps', ['steps', 'num_steps']);
        addGenerationFieldFromKeys('clip_skip', ['clip_skip']);
        addGenerationFieldFromKeys('cfg', ['cfg', 'cfg_scale']);
        addGenerationFieldFromKeys('sampler', ['sampler_name', 'sampler']);
        addGenerationFieldFromKeys('scheduler', ['scheduler']);
        addGenerationFieldFromKeys('denoise', ['denoise', 'denoise_strength']);
        addGenerationFieldFromKeys('time_seconds', ['sampler_time_seconds', 'time_seconds']);
        const loraNames = Array.isArray(generationSource.loras) ? generationSource.loras : [];
        const loraStrengths = Array.isArray(generationSource.lora_strengths) ? generationSource.lora_strengths : [];
        if (loraNames.length && loraStrengths.length) {
          const loraChips = loraNames.map((name, index) => {
            const [modelStrength, clipStrength] = loraStrengths[index] || [1, 1];
            return {
              label: `${name} (${modelStrength === clipStrength ? modelStrength : `${modelStrength}/${clipStrength}`})`,
              value: String(name)
            };
          });
          generationPairs.push(['loras', loraChips.map((chip) => chip.label).join(', '), loraChips]);
        } else {
          addGenerationFieldFromKeys('loras', ['loras']);
        }
        addGenerationFieldFromKeys('vae', ['vae_name']);
        addGenerationFieldFromKeys('clip', ['clip_name']);
        if (generationSource.width > 0 && generationSource.height > 0) {
          generationPairs.push(['size', `${generationSource.width}x${generationSource.height}`]);
        }
        addGenerationFieldFromKeys('sampler_info', ['sampler_info']);
        addGenerationFieldFromKeys('positive_prompt', ['positive_prompt', 'prompt']);
        addGenerationFieldFromKeys('negative_prompt', ['negative_prompt', 'negative']);
        addGenerationFieldFromKeys('prompt_sections', ['prompt_sections']);
        const xySweep = /^XY sweep (.+)$/.exec(String(generationSource.notes || '').trim());
        if (xySweep) {
          const [xAxis, yAxis] = xySweep[1].split(' | ');
          generationPairs.push(['xy_sweep_x', xAxis]);
          if (yAxis) {
            generationPairs.push(['xy_sweep_y', yAxis]);
          }
        } else {
          addGenerationFieldFromKeys('notes', ['notes']);
        }
        addGenerationFieldFromKeys('save_prefix', ['save_prefix']);
        addGenerationFieldFromKeys('filepath', ['filepath', 'file', 'path']);
      }

      // Values that make useful "find all media like this" searches become clickable chips.
      const filterableLabels = new Set(['model', 'seed', 'sampler', 'scheduler', 'vae', 'clip']);
      for (const pair of generationPairs) {
        if (pair[2] || !filterableLabels.has(pair[0])) {
          continue;
        }
        const value = String(pair[1] || '').trim();
        if (value && value.length <= 200 && !value.includes('\n')) {
          pair[2] = [{ label: value, value }];
        }
      }

      const extraBubbaPairs = [];
      if (bubbaMetadata) {
        const known = new Set([
          'model_name',
          'clip_skip',
          'seed',
          'steps',
          'cfg',
          'sampler_name',
          'scheduler',
          'denoise',
          'sampler_time_seconds',
          'sampler_info',
          'positive_prompt',
          'negative_prompt',
          'loras',
          'lora_strengths',
          'vae_name',
          'clip_name',
          'width',
          'height',
          'notes',
          'save_prefix',
          'prompt_sections',
          'filepath'
        ]);

        for (const [key, value] of Object.entries(bubbaMetadata)) {
          if (known.has(key) || !hasValue(value)) {
            continue;
          }
          extraBubbaPairs.push([`bubba.${key}`, typeof value === 'string' ? value : JSON.stringify(value, null, 2)]);
        }
      }

      const metadataPairs = [];
      if (metadata.format) {
        metadataPairs.push(['format', metadata.format]);
      }
      if (Array.isArray(metadata.keys)) {
        metadataPairs.push(['keys', metadata.keys.join(', ') || '(none)']);
      }
      if (embedded && typeof embedded === 'object') {
        for (const [key, value] of Object.entries(embedded)) {
          if (key === 'bubba_metadata') {
            continue;
          }
          metadataPairs.push([key, typeof value === 'string' ? value : JSON.stringify(value, null, 2)]);
        }
      }

      const hasGenerationData = generationPairs.length > 0;
      const hasAnyMetadata = hasGenerationData || metadataPairs.length > 0;

      const metadataBadgeClass = hasGenerationData
        ? 'metadata-status metadata-status-ok'
        : hasAnyMetadata
          ? 'metadata-status metadata-status-warn'
          : 'metadata-status metadata-status-none';
      const metadataBadgeText = hasGenerationData
        ? 'Generation data detected'
        : hasAnyMetadata
          ? 'Metadata found (no generation)'
          : 'No metadata detected';

      const copyPromptValue =
        generationSource && hasValue(generationSource.positive_prompt) ? String(generationSource.positive_prompt) : '';
      const copySeedValue = generationSource && hasValue(generationSource.seed) ? String(generationSource.seed) : '';

      return {
        filePairs,
        generationPairs,
        extraBubbaPairs,
        metadataPairs,
        metadataBadgeClass,
        metadataBadgeText,
        copyPromptValue,
        copySeedValue
      };
    });

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

    const isFavorite = computed(() => Boolean(props.assetDetails?.favorite ?? props.selectedAsset?.favorite));

    return {
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
                                    @click="$emit('filter-by', chip.value)"
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
