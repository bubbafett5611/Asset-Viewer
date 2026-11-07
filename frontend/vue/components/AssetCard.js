import { formatBytes, formatDate } from '/vue/formatters.js';
import { fileUrl, thumbUrl } from '/vue/api.js';

export const AssetCard = {
  name: 'AssetCard',
  props: {
    multiSelecting: Boolean,
    asset: {
      type: Object,
      required: true
    },
    active: {
      type: Boolean,
      default: false
    },
    selected: {
      type: Boolean,
      default: false
    },
    blurEnabled: {
      type: Boolean,
      default: false
    }
  },
  emits: ['select'],
  setup() {
    const previewableExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff']);
    const videoExtensions = new Set(['.mp4']);
    const isPreviewable = (asset) => previewableExtensions.has(String(asset?.extension || '').toLowerCase());
    const isVideo = (asset) => videoExtensions.has(String(asset?.extension || '').toLowerCase());
    const previewUrl = (asset) =>
      String(asset?.extension || '').toLowerCase() === '.gif' ? fileUrl(asset.path) : thumbUrl(asset);
    const metadataBadges = (asset) => (Array.isArray(asset?.metadata_badges) ? asset.metadata_badges : []);
    const markThumbFailed = (event) => {
      const thumb = event?.target?.closest?.('.asset-thumb');
      if (thumb) {
        thumb.classList.add('thumb-failed');
      }
    };

    return {
      thumbUrl,
      fileUrl,
      formatBytes,
      formatDate,
      isPreviewable,
      isVideo,
      previewUrl,
      metadataBadges,
      markThumbFailed
    };
  },
  template: `
        <button
            class="asset-card"
            :class="{ active, 'is-selected': selected, 'is-blurred': blurEnabled }"
            :aria-pressed="selected || (active && !multiSelecting)"
            type="button"
            @click="$emit('select', asset, $event)"
        >
            <div class="asset-thumb">
                <span v-if="selected || (active && !multiSelecting)" class="selection-check" aria-label="Selected">✓</span>
                <img
                    v-if="isPreviewable(asset)"
                    :src="previewUrl(asset)"
                    :alt="asset.name"
                    loading="lazy"
                    @error="markThumbFailed"
                />
                <video
                    v-else-if="isVideo(asset)"
                    :src="fileUrl(asset.path)"
                    :aria-label="asset.name"
                    muted
                    playsinline
                    preload="metadata"
                    @error="markThumbFailed"
                ></video>
                <span v-if="isVideo(asset)" class="asset-video-indicator" aria-hidden="true">&#9654;</span>
                <div class="asset-thumb-fallback">
                    <span>{{ isPreviewable(asset) || isVideo(asset) ? 'Preview unavailable' : 'No media preview' }}</span>
                </div>
                <div v-if="metadataBadges(asset).length" class="asset-metadata-badges">
                    <span
                        v-for="badge in metadataBadges(asset)"
                        :key="badge.key"
                        class="asset-metadata-badge"
                        :class="'asset-metadata-badge--' + badge.key"
                    >
                        {{ badge.label }}
                    </span>
                </div>
            </div>
            <div class="asset-top">
                <h3 class="asset-title">{{ asset.name }}</h3>
                <span class="asset-chip">{{ asset.extension || 'file' }}</span>
            </div>
            <div class="asset-path">{{ asset.relative_path }}</div>
            <div class="asset-extra">
                <span>{{ formatBytes(asset.size_bytes) }}</span>
                <span>{{ formatDate(asset.modified_ts) }}</span>
            </div>
        </button>
    `
};
