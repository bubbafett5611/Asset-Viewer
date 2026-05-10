import { TagRow } from '/vue/components/TagRow.js';
import { TagDetailsPanel } from '/vue/components/TagDetailsPanel.js';

export const TagsView = {
  name: 'TagsView',
  components: {
    TagRow,
    TagDetailsPanel
  },
  props: {
    layoutStyle: {
      type: Object,
      required: true
    },
    tagFilters: {
      type: Object,
      required: true
    },
    tagCategories: {
      type: Array,
      required: true
    },
    tagStatusText: {
      type: String,
      required: true
    },
    tagCopyStatus: {
      type: String,
      default: ''
    },
    tagCountText: {
      type: String,
      required: true
    },
    visibleTags: {
      type: Array,
      required: true
    },
    selectedTag: {
      type: Object,
      default: null
    },
    selectedTagAliases: {
      type: Array,
      required: true
    },
    selectedTagExamples: {
      type: Array,
      required: true
    },
    tagExamplesLoading: {
      type: Boolean,
      default: false
    },
    isLoadingTags: {
      type: Boolean,
      default: false
    },
    tagHasMore: {
      type: Boolean,
      default: false
    },
    isTagFavorite: {
      type: Function,
      required: true
    },
    fetchTags: {
      type: Function,
      required: true
    },
    selectTag: {
      type: Function,
      required: true
    },
    toggleTagFavorite: {
      type: Function,
      required: true
    },
    loadMoreTags: {
      type: Function,
      required: true
    },
    exampleImageUrl: {
      type: Function,
      required: true
    },
    tagSearchUrl: {
      type: Function,
      required: true
    },
    copySelectedTagName: {
      type: Function,
      required: true
    },
    startDetailsResize: {
      type: Function,
      required: true
    }
  },
  watch: {
    'selectedTag.name'() {
      this.scrollSelectedTagIntoView();
    }
  },
  mounted() {
    this.scrollSelectedTagIntoView();
  },
  methods: {
    scrollSelectedTagIntoView() {
      this.$nextTick(() => {
        this.$refs.tagList?.querySelector('.tag-row.active')?.scrollIntoView({ block: 'nearest' });
      });
    }
  },
  template: `
        <div class="layout tags-layout tab-panel" :style="layoutStyle">
            <section class="panel tags-panel">
                <div class="controls tag-controls">
                    <div class="field tag-search-field">
                        <label for="tagSearchInput">Tag Search</label>
                        <input id="tagSearchInput" v-model="tagFilters.q" class="input" type="search" placeholder="Tag or alias" />
                    </div>

                    <div class="field">
                        <label for="tagCategorySelect">Category</label>
                        <select id="tagCategorySelect" v-model="tagFilters.category" class="select">
                            <option value="">All categories</option>
                            <option v-for="category in tagCategories" :key="category" :value="category">{{ category }}</option>
                        </select>
                    </div>

                    <div class="field">
                        <label for="tagViewSelect">View</label>
                        <select id="tagViewSelect" v-model="tagFilters.view" class="select">
                            <option value="all">All tags</option>
                            <option value="favorites">Favorites only</option>
                            <option value="recent">Recent only</option>
                        </select>
                    </div>

                    <div class="field tag-reload-field">
                        <div class="field-label">Controls</div>
                        <button id="tagReloadButton" class="button" type="button" :disabled="isLoadingTags" @click="fetchTags">
                            {{ isLoadingTags ? 'Reloading...' : 'Reload Tags' }}
                        </button>
                    </div>
                </div>

                <div class="results tags-results">
                    <div class="meta-row tags-meta-row">
                        <div class="meta-group">
                            <span class="status-dot" aria-hidden="true"></span>
                            <span>{{ tagStatusText }}</span>
                        </div>
                        <div class="count-badge">{{ tagCountText }}</div>
                    </div>
                    <div ref="tagList" class="tag-list" aria-live="polite">
                        <TagRow
                            v-for="tag in visibleTags"
                            :key="tag.name"
                            :tag="tag"
                            :active="selectedTag && selectedTag.name === tag.name"
                            :favorite="isTagFavorite(tag.name)"
                            @select="selectTag"
                            @toggle-favorite="toggleTagFavorite"
                        />
                    </div>
                    <button v-if="tagHasMore" class="button" type="button" @click="loadMoreTags">
                        Load More Tags
                    </button>
                </div>
            </section>
            <div
                class="panel-resizer"
                role="separator"
                aria-orientation="vertical"
                aria-label="Resize details panel width"
                title="Drag to resize details panel width"
                @mousedown="startDetailsResize"
            ></div>
            <TagDetailsPanel
                :selected-tag="selectedTag"
                :favorite="selectedTag ? isTagFavorite(selectedTag.name) : false"
                :aliases="selectedTagAliases"
                :examples="selectedTagExamples"
                :examples-loading="tagExamplesLoading"
                :copy-status="tagCopyStatus"
                :example-image-url="exampleImageUrl"
                :tag-search-url="tagSearchUrl"
                @copy-tag="copySelectedTagName"
                @toggle-favorite="toggleTagFavorite"
            />
        </div>
    `
};
