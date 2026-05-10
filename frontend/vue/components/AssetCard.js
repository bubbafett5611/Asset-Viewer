import { formatBytes, formatDate } from "/vue/formatters.js";
import { thumbUrl } from "/vue/api.js";

export const AssetCard = {
    name: "AssetCard",
    props: {
        asset: {
            type: Object,
            required: true,
        },
        active: {
            type: Boolean,
            default: false,
        },
        selected: {
            type: Boolean,
            default: false,
        },
        blurEnabled: {
            type: Boolean,
            default: false,
        },
    },
    emits: ["select"],
    setup() {
        const previewableExtensions = new Set([".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".tif", ".tiff"]);
        const isPreviewable = (asset) => previewableExtensions.has(String(asset?.extension || "").toLowerCase());
        const metadataBadges = (asset) => Array.isArray(asset?.metadata_badges) ? asset.metadata_badges : [];
        const markThumbFailed = (event) => {
            const thumb = event?.target?.closest?.(".asset-thumb");
            if (thumb) {
                thumb.classList.add("thumb-failed");
            }
        };

        return {
            thumbUrl,
            formatBytes,
            formatDate,
            isPreviewable,
            metadataBadges,
            markThumbFailed,
        };
    },
    template: `
        <button
            class="asset-card"
            :class="{ active, 'is-selected': selected, 'is-blurred': blurEnabled }"
            type="button"
            @click="$emit('select', asset, $event)"
        >
            <div class="asset-thumb">
                <img
                    v-if="isPreviewable(asset)"
                    :src="thumbUrl(asset)"
                    :alt="asset.name"
                    loading="lazy"
                    @error="markThumbFailed"
                />
                <div class="asset-thumb-fallback">
                    <span>{{ isPreviewable(asset) ? 'Preview unavailable' : 'No image preview' }}</span>
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
    `,
};
