import { LIBRARY_KEY, searchToken } from '/vue/composables/useLibraryExtras.js';

const SECTIONS = [
  { key: 'models', title: 'Checkpoints', field: 'model' },
  { key: 'loras', title: 'LoRAs', field: 'lora' },
  { key: 'samplers', title: 'Samplers', field: 'sampler' },
  { key: 'schedulers', title: 'Schedulers', field: 'scheduler' },
  { key: 'prompt_tags', title: 'Prompt tags', field: 'prompt' }
];

/** Most-used generation settings in the current root; every row opens a filtered Media view. */
export const LibraryInsights = {
  name: 'LibraryInsights',
  inject: { library: { from: LIBRARY_KEY, default: null } },
  props: {
    rootLabel: { type: String, default: '' }
  },
  data() {
    return { expanded: {} };
  },
  computed: {
    facets() {
      return this.library?.facets || null;
    },
    sections() {
      if (!this.facets) return [];
      return SECTIONS.map((section) => {
        const items = this.facets[section.key] || [];
        const max = items.reduce((highest, item) => Math.max(highest, item.count), 0) || 1;
        const limit = this.expanded[section.key] ? items.length : 8;
        return { ...section, items: items.slice(0, limit), total: items.length, max };
      }).filter((section) => section.total);
    },
    coverage() {
      if (!this.facets?.total) return 0;
      return Math.round((100 * this.facets.with_generation) / this.facets.total);
    }
  },
  methods: {
    open(section, value) {
      this.library.applySearch(searchToken(section.field, value, { exact: section.field !== 'prompt' }));
    }
  },
  template: `
    <section class="library-insights" aria-label="Library insights">
      <header class="library-insights-header">
        <div>
          <h3>Library insights{{ rootLabel ? ' · ' + rootLabel : '' }}</h3>
          <p v-if="facets">{{ facets.with_generation.toLocaleString() }} of {{ facets.total.toLocaleString() }} files have generation data ({{ coverage }}%). Click any row to see those images.</p>
          <p v-else>Insights appear once the library index is built.</p>
        </div>
        <button class="button button--compact" type="button" @click="library && library.fetchFacets()">Refresh</button>
      </header>
      <div v-if="sections.length" class="library-insights-grid">
        <div v-for="section in sections" :key="section.key" class="insight-card">
          <h4>{{ section.title }} <span>{{ section.total }}</span></h4>
          <ol>
            <li v-for="item in section.items" :key="item.value">
              <button type="button" class="insight-row" :title="'Show images using ' + item.value" @click="open(section, item.value)">
                <span class="insight-bar" :style="{ width: (100 * item.count / section.max) + '%' }" aria-hidden="true"></span>
                <span class="insight-label">{{ item.value }}</span>
                <span class="insight-count">{{ item.count.toLocaleString() }}</span>
              </button>
            </li>
          </ol>
          <button v-if="section.total > 8" type="button" class="insight-more" @click="expanded[section.key] = !expanded[section.key]">
            {{ expanded[section.key] ? 'Show less' : 'Show all ' + section.total }}
          </button>
        </div>
      </div>
    </section>
  `
};
