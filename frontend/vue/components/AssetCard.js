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
    },
    dayLabel: {
      type: String,
      default: ''
    }
  },
  emits: ['select', 'open', 'favorite', 'drag-start', 'drag-end'],
  setup() {
    const previewableExtensions = new Set(['.png', '.jpg', '.jpeg', '.webp', '.bmp', '.gif', '.tif', '.tiff']);
    const videoExtensions = new Set(['.mp4']);
    const isPreviewable = (asset) => previewableExtensions.has(String(asset?.extension || '').toLowerCase());
    const isVideo = (asset) => videoExtensions.has(String(asset?.extension || '').toLowerCase());
    const previewUrl = (asset) =>
      String(asset?.extension || '').toLowerCase() === '.gif' ? fileUrl(asset.path) : thumbUrl(asset);
    const metadataBadges = (asset) => (Array.isArray(asset?.metadata_badges) ? asset.metadata_badges : []);
    // Generated filenames usually share a long prefix (Seed_123456789…) and differ only in
    // the trailing counter, so keep the tail visible and let the head ellipsize instead.
    const titleParts = (asset) => {
      const name = String(asset?.name || '');
      const extension = String(asset?.extension || '');
      const stem =
        extension && name.toLowerCase().endsWith(extension.toLowerCase())
          ? name.slice(0, name.length - extension.length)
          : name;
      const separatorIndex = Math.max(stem.lastIndexOf('_'), stem.lastIndexOf('-'), stem.lastIndexOf(' '));
      let tailStart = separatorIndex > 0 && stem.length - separatorIndex <= 14 ? separatorIndex : stem.length - 8;
      if (tailStart < 4) {
        return { head: stem, tail: '' };
      }
      return { head: stem.slice(0, tailStart), tail: stem.slice(tailStart) };
    };
    const markThumbLoaded = (event) => {
      event?.target?.closest?.('.asset-thumb')?.classList.add('thumb-loaded');
    };
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
      titleParts,
      markThumbLoaded,
      markThumbFailed
    };
  },
  template: `
        <div class="asset-card-shell" :class="{ 'is-favorite': asset.favorite }" :data-modified="asset.modified_ts">
        <button
            class="asset-card"
            draggable="true"
            @dragstart="$emit('drag-start', asset, $event)"
            @dragend="$emit('drag-end', asset, $event)"
            :class="{ active, 'is-selected': selected, 'is-blurred': blurEnabled }"
            :aria-pressed="selected || (active && !multiSelecting)"
            type="button"
            :title="asset.name"
            @click="$emit('select', asset, $event)"
            @dblclick="$emit('open', asset)"
        >
            <div class="asset-thumb">
                <span v-if="selected || (active && !multiSelecting)" class="selection-check" aria-label="Selected">✓</span>
                <img
                    v-if="isPreviewable(asset)"
                    :src="previewUrl(asset)"
                    :alt="asset.name"
                    loading="lazy"
                    decoding="async"
                    @load="markThumbLoaded"
                    @error="markThumbFailed"
                />
                <video
                    v-else-if="isVideo(asset)"
                    :src="fileUrl(asset.path)"
                    :aria-label="asset.name"
                    muted
                    playsinline
                    preload="metadata"
                    @loadeddata="markThumbLoaded"
                    @error="markThumbFailed"
                ></video>
                <span v-if="isVideo(asset)" class="asset-video-indicator" aria-hidden="true">&#9654;</span>
                <span v-if="asset.similarity !== undefined" class="asset-top-marker asset-top-marker--similar" :title="asset.similarity + '% visually similar'">≈ {{ asset.similarity }}%</span>
                <span v-else-if="dayLabel" class="asset-top-marker">{{ dayLabel }}</span>
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
                <h3 class="asset-title" :aria-label="asset.name"><span class="asset-title-head">{{ titleParts(asset).head }}</span><span v-if="titleParts(asset).tail" class="asset-title-tail">{{ titleParts(asset).tail }}</span></h3>
                <span class="asset-chip">{{ asset.extension || 'file' }}</span>
            </div>
            <div class="asset-path">{{ asset.relative_path }}</div>
            <div class="asset-extra">
                <span>{{ formatBytes(asset.size_bytes) }}</span>
                <span>{{ formatDate(asset.modified_ts) }}</span>
            </div>
        </button>
        <button
            class="asset-favorite-toggle"
            type="button"
            :aria-pressed="Boolean(asset.favorite)"
            :aria-label="asset.favorite ? 'Remove from favorites' : 'Add to favorites'"
            :title="asset.favorite ? 'Remove from favorites (F)' : 'Add to favorites (F)'"
            @click.stop="$emit('favorite', asset)"
        >
            <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 3.6l2.6 5.3 5.8.8-4.2 4.1 1 5.8L12 16.9l-5.2 2.7 1-5.8-4.2-4.1 5.8-.8z" /></svg>
        </button>
        </div>
    `
};
