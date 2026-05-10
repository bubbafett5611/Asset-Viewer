export const TagDetailsPanel = {
  name: 'TagDetailsPanel',
  props: {
    selectedTag: {
      type: Object,
      default: null
    },
    favorite: {
      type: Boolean,
      default: false
    },
    aliases: {
      type: Array,
      default: () => []
    },
    examples: {
      type: Array,
      default: () => []
    },
    examplesLoading: {
      type: Boolean,
      default: false
    },
    copyStatus: {
      type: String,
      default: ''
    },
    exampleImageUrl: {
      type: Function,
      required: true
    },
    tagSearchUrl: {
      type: Function,
      required: true
    }
  },
  emits: ['copy-tag', 'toggle-favorite'],
  template: `
        <aside class="panel tag-details-panel details">
            <div class="details-header">
                <h2>Tag Details</h2>
                <p class="details-subtitle">Select a tag to inspect category, count, aliases, and examples.</p>
            </div>

            <div class="details-scroll">
                <div v-if="selectedTag" class="details-grid">
                    <div class="kv">
                        <div class="kv-key">Name</div>
                        <button
                            class="kv-value copyable-kv-value tag-name-copy-button"
                            type="button"
                            title="Copy tag name"
                            :aria-label="'Copy tag name ' + selectedTag.name"
                            @click="$emit('copy-tag', selectedTag.name)"
                        >
                            <span>{{ selectedTag.name }}</span>
                            <span v-if="copyStatus" class="copy-confirmation">{{ copyStatus }}</span>
                            <svg class="copy-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
                                <rect x="9" y="9" width="11" height="11" rx="2"></rect>
                                <path d="M5 15V5a2 2 0 0 1 2-2h10"></path>
                            </svg>
                        </button>
                    </div>
                    <div class="kv"><div class="kv-key">Category</div><div class="kv-value">{{ selectedTag.category || 'unknown' }}</div></div>
                    <div class="kv"><div class="kv-key">Count</div><div class="kv-value">{{ selectedTag.count }}</div></div>

                    <div class="tag-action-row">
                        <button class="tag-action-button" type="button" @click="$emit('toggle-favorite', selectedTag)">
                            {{ favorite ? 'Unfavorite' : 'Favorite' }}
                        </button>
                        <a class="tag-search-link" :href="tagSearchUrl(selectedTag.name, 'danbooru')" target="_blank" rel="noopener noreferrer">Search Danbooru</a>
                    </div>

                    <div class="details-section-title">Aliases</div>
                    <div class="tag-chip-list" v-if="aliases.length > 0">
                        <button v-for="alias in aliases" :key="alias" class="tag-pill-button" type="button">{{ alias }}</button>
                    </div>
                    <div v-else class="empty-inline">No aliases.</div>

                    <div class="details-section-title">Examples</div>
                    <div v-if="examplesLoading" class="empty-inline">Loading examples...</div>
                    <div v-else-if="examples.length === 0" class="empty-inline">No examples found.</div>
                    <div v-else class="tag-example-grid">
                        <article class="tag-example-card" v-for="example in examples" :key="example.site">
                            <div class="tag-example-header">
                                <div class="tag-example-site">{{ example.site }}</div>
                                <div class="tag-example-score" v-if="example.score !== null">Score {{ example.score }}</div>
                            </div>
                            <a class="tag-example-thumb-link" :href="example.page_url || '#'" target="_blank" rel="noopener noreferrer">
                                <img
                                    v-if="example.image_url"
                                    class="tag-example-thumb"
                                    :src="exampleImageUrl(example.image_url)"
                                    :alt="selectedTag.name"
                                    loading="lazy"
                                />
                                <div v-else class="tag-example-image-missing empty-inline">Image unavailable</div>
                            </a>
                            <a class="tag-example-open" :href="example.page_url || '#'" target="_blank" rel="noopener noreferrer">Open Post</a>
                        </article>
                    </div>
                </div>
                <div v-else class="empty">No tag selected.</div>
            </div>
        </aside>
    `
};
