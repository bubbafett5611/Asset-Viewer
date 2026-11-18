import { API, buildQuery } from '/vue/api.js';
import { buildMetadataSummary } from '/vue/metadataFields.js';

const LONG_FIELDS = new Set(['positive_prompt', 'negative_prompt', 'prompt_sections', 'sampler_info', 'notes']);

/** Side-by-side generation settings for two images, with differences highlighted. */
export const MetadataDiff = {
  name: 'MetadataDiff',
  props: {
    left: { type: Object, required: true },
    right: { type: Object, required: true }
  },
  data() {
    return { leftDetails: null, rightDetails: null, loading: false, onlyDifferences: true };
  },
  computed: {
    rows() {
      if (!this.leftDetails || !this.rightDetails) return [];
      const leftPairs = buildMetadataSummary(this.left, this.leftDetails).generationPairs;
      const rightPairs = buildMetadataSummary(this.right, this.rightDetails).generationPairs;
      const leftMap = new Map(leftPairs.map((pair) => [pair[0], String(pair[1] ?? '')]));
      const rightMap = new Map(rightPairs.map((pair) => [pair[0], String(pair[1] ?? '')]));
      const labels = [...new Set([...leftMap.keys(), ...rightMap.keys()])].filter(
        (label) => label !== 'filepath' && label !== 'time_seconds'
      );
      return labels.map((label) => {
        const leftValue = leftMap.get(label) ?? '';
        const rightValue = rightMap.get(label) ?? '';
        return { label, leftValue, rightValue, differs: leftValue !== rightValue, long: LONG_FIELDS.has(label) };
      });
    },
    differenceCount() {
      return this.rows.filter((row) => row.differs).length;
    },
    visibleRows() {
      return this.onlyDifferences ? this.rows.filter((row) => row.differs) : this.rows;
    }
  },
  watch: {
    left: { handler: 'load', immediate: true },
    right: 'load'
  },
  methods: {
    async fetchDetails(asset) {
      const response = await fetch(buildQuery(API.details, { path: asset.path }));
      if (!response.ok) throw new Error(`Failed to load details (${response.status})`);
      return (await response.json()).asset || null;
    },
    async load() {
      this.loading = true;
      try {
        const [leftDetails, rightDetails] = await Promise.all([
          this.fetchDetails(this.left),
          this.fetchDetails(this.right)
        ]);
        this.leftDetails = leftDetails;
        this.rightDetails = rightDetails;
      } catch (error) {
        console.error(error);
      } finally {
        this.loading = false;
      }
    },
    // Highlight the words that differ inside long prompt fields.
    wordDiff(text, other) {
      const otherWords = new Set(
        String(other)
          .toLowerCase()
          .split(/[\s,]+/)
          .filter(Boolean)
      );
      return String(text)
        .split(/(\s+|,)/)
        .map((part) => ({ part, changed: /\w/.test(part) && !otherWords.has(part.toLowerCase()) }));
    }
  },
  template: `
    <section class="metadata-diff" aria-label="Generation settings comparison">
      <header class="metadata-diff-header">
        <h3>Generation settings</h3>
        <span v-if="loading" class="metadata-diff-status">Loading…</span>
        <span v-else-if="rows.length" class="metadata-diff-status">{{ differenceCount ? differenceCount + ' different' : 'Identical settings' }}</span>
        <label v-if="rows.length" class="metadata-diff-toggle"><input v-model="onlyDifferences" type="checkbox" /> Only differences</label>
      </header>
      <p v-if="!loading && !rows.length" class="metadata-diff-empty">Neither image has generation metadata to compare.</p>
      <div v-else-if="visibleRows.length" class="metadata-diff-grid" role="table">
        <div class="metadata-diff-row metadata-diff-row--head" role="row">
          <span role="columnheader">Field</span><span role="columnheader">Left (slider side)</span><span role="columnheader">Right</span>
        </div>
        <div v-for="row in visibleRows" :key="row.label" class="metadata-diff-row" :class="{ 'is-different': row.differs }" role="row">
          <span class="metadata-diff-label" role="cell">{{ row.label }}</span>
          <span class="metadata-diff-value" role="cell">
            <template v-if="row.long && row.differs"><span v-for="(token, index) in wordDiff(row.leftValue, row.rightValue)" :key="index" :class="{ 'diff-word': token.changed }">{{ token.part }}</span></template>
            <template v-else>{{ row.leftValue || '—' }}</template>
          </span>
          <span class="metadata-diff-value" role="cell">
            <template v-if="row.long && row.differs"><span v-for="(token, index) in wordDiff(row.rightValue, row.leftValue)" :key="index" :class="{ 'diff-word': token.changed }">{{ token.part }}</span></template>
            <template v-else>{{ row.rightValue || '—' }}</template>
          </span>
        </div>
      </div>
      <p v-else-if="!loading" class="metadata-diff-empty">All {{ rows.length }} generation settings match.</p>
    </section>
  `
};
