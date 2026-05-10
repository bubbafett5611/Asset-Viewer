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
  emits: ['delete-asset', 'open-folder', 'repair-metadata', 'resize-preview'],
  setup(props) {
    const previewableExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff']);
    const isPreviewableAsset = computed(() =>
      previewableExtensions.has(String(props.selectedAsset?.extension || '').toLowerCase())
    );
    const canRepairMetadata = computed(() => String(props.selectedAsset?.extension || '').toLowerCase() === '.png');

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
        addGenerationFieldFromKeys('loras', ['loras']);
        addGenerationFieldFromKeys('sampler_info', ['sampler_info']);
        addGenerationFieldFromKeys('positive_prompt', ['positive_prompt', 'prompt']);
        addGenerationFieldFromKeys('negative_prompt', ['negative_prompt', 'negative']);
        addGenerationFieldFromKeys('prompt_sections', ['prompt_sections']);
        addGenerationFieldFromKeys('filepath', ['filepath', 'file', 'path']);
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

    return {
      fileUrl,
      formatBytes,
      formatDate,
      isPreviewableAsset,
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
                    <h2>Media Details</h2>
                    <span v-if="selectedAsset" :class="metadataSummary.metadataBadgeClass">{{ metadataSummary.metadataBadgeText }}</span>
                </div>
                <p class="details-subtitle">{{ selectedAsset ? selectedAsset.name : 'Select an item to inspect file info and embedded metadata.' }}</p>
            </div>

            <div class="preview">
                <div class="preview-frame">
                    <img v-if="selectedAsset && isPreviewableAsset" :src="fileUrl(selectedAsset.path)" :alt="selectedAsset.name" />
                    <div v-else-if="selectedAsset" class="preview-empty">No image preview</div>
                    <div v-else class="preview-empty">No media selected</div>
                </div>
                <div v-if="selectedAsset" class="preview-actions">
                    <button type="button" class="preview-action" @click="openFull">Open Full</button>
                    <button type="button" class="preview-action" @click="$emit('open-folder', selectedAsset)">Open Folder</button>
                    <button type="button" class="preview-action" @click="copyText(selectedAsset.path)">Copy Path</button>
                    <button type="button" class="preview-action" :disabled="!metadataSummary.copyPromptValue" @click="copyText(metadataSummary.copyPromptValue)">Copy Prompt</button>
                    <button type="button" class="preview-action" :disabled="!metadataSummary.copySeedValue" @click="copyText(metadataSummary.copySeedValue)">Copy Seed</button>
                    <button type="button" class="preview-action" :disabled="!canRepairMetadata" @click="$emit('repair-metadata', selectedAsset)">Repair Metadata</button>
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
                @mousedown="$emit('resize-preview', $event)"
            ></div>

            <div class="details-scroll">
                <div v-if="selectedAsset" class="details-grid">
                    <div class="details-section-title">File</div>
                    <div class="kv" v-for="pair in metadataSummary.filePairs" :key="'file-' + pair[0]">
                        <div class="kv-key">{{ pair[0] }}</div>
                        <div class="kv-value">{{ pair[1] }}</div>
                    </div>

                    <template v-if="metadataSummary.generationPairs.length > 0">
                        <div class="details-section-title">Generation</div>
                        <div class="kv" v-for="pair in metadataSummary.generationPairs" :key="'gen-' + pair[0]">
                            <div class="kv-key">{{ pair[0] }}</div>
                            <div class="kv-value">{{ pair[1] }}</div>
                        </div>
                    </template>

                    <template v-if="metadataSummary.extraBubbaPairs.length > 0">
                        <div class="details-section-title">Bubba Extra</div>
                        <div class="kv" v-for="pair in metadataSummary.extraBubbaPairs" :key="'bubba-' + pair[0]">
                            <div class="kv-key">{{ pair[0] }}</div>
                            <div class="kv-value">{{ pair[1] }}</div>
                        </div>
                    </template>

                    <template v-if="metadataSummary.metadataPairs.length > 0">
                        <div class="details-section-title">Embedded Metadata</div>
                        <div class="kv" v-for="pair in metadataSummary.metadataPairs" :key="'meta-' + pair[0]">
                            <div class="kv-key">{{ pair[0] }}</div>
                            <div class="kv-value">{{ pair[1] }}</div>
                        </div>
                    </template>

                    <div v-if="metadataSummary.generationPairs.length === 0 && metadataSummary.metadataPairs.length === 0" class="empty-inline">
                        No metadata detected.
                    </div>
                </div>
                <div v-else class="empty">Select media to inspect fields.</div>
            </div>
        </aside>
    `
};
