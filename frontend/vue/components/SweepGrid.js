import { API, buildQuery, thumbUrl } from '/vue/api.js';

/** Labelled X×Y grid for one XY sweep; clicking a cell selects it in the inspector. */
export const SweepGrid = {
  name: 'SweepGrid',
  props: {
    blur: { type: Function, default: () => false }
  },
  emits: ['select'],
  data() {
    return { sweep: null, loading: false, error: '', currentPath: '' };
  },
  computed: {
    grid() {
      if (!this.sweep) return [];
      const rows = [];
      for (let row = 0; row < this.sweep.rows; row += 1) {
        const cells = [];
        for (let column = 0; column < this.sweep.columns; column += 1) {
          cells.push(this.sweep.cells.find((cell) => cell.row === row && cell.column === column) || null);
        }
        rows.push({ label: this.sweep.y_labels[row] || '', cells });
      }
      return rows;
    },
    title() {
      if (!this.sweep) return 'XY sweep';
      const axes = [this.sweep.x_axis, this.sweep.y_axis].filter(Boolean).join(' × ');
      return `XY sweep${axes ? ` · ${axes}` : ''}`;
    },
    missingCount() {
      if (!this.sweep) return 0;
      return Math.max(0, this.sweep.columns * this.sweep.rows - this.sweep.cells.length);
    }
  },
  methods: {
    thumbUrl,
    async open(path) {
      this.currentPath = path;
      this.sweep = null;
      this.error = '';
      this.loading = true;
      this.$refs.dialog.showModal();
      try {
        const response = await fetch(buildQuery(API.sweep, { path }));
        const payload = await response.json().catch(() => ({}));
        if (!response.ok) throw new Error(payload.error || payload.description || 'Could not load this sweep.');
        this.sweep = payload.sweep;
      } catch (error) {
        this.error = error.message;
      } finally {
        this.loading = false;
      }
    },
    close() {
      this.$refs.dialog.close();
    },
    pick(entry) {
      if (!entry) return;
      this.$emit('select', { path: entry.path, name: entry.name, extension: '.png' });
      this.close();
    },
    cellLabel(cell, rowLabel) {
      return [cell.x, rowLabel].filter(Boolean).join(' · ');
    }
  },
  template: `
    <Teleport to="body">
      <dialog ref="dialog" class="sweep-dialog" :aria-label="title">
        <header class="sweep-header">
          <div>
            <strong>{{ title }}</strong>
            <small v-if="sweep">{{ sweep.columns }} × {{ sweep.rows }} · {{ sweep.cells.length }} cells{{ missingCount ? ' · ' + missingCount + ' not found' : '' }}{{ sweep.source === 'notes' ? ' · grouped by notes and save time' : '' }}</small>
          </div>
          <div class="sweep-header-actions">
            <button v-if="sweep && sweep.sheet" class="button button--compact" type="button" @click="pick(sweep.sheet)">Open sheet</button>
            <button class="button button--compact" type="button" @click="close">Close</button>
          </div>
        </header>
        <p v-if="loading" class="sweep-status" role="status">Loading sweep…</p>
        <p v-else-if="error" class="sweep-status is-error" role="alert">{{ error }}</p>
        <div v-else-if="sweep" class="sweep-scroll">
          <table class="sweep-table">
            <thead>
              <tr>
                <th scope="col" class="sweep-corner">{{ sweep.y_axis ? sweep.y_axis + ' ↓ · ' + sweep.x_axis + ' →' : sweep.x_axis + ' →' }}</th>
                <th v-for="label in sweep.x_labels" :key="label" scope="col">{{ label }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(row, rowIndex) in grid" :key="rowIndex">
                <th scope="row">{{ row.label }}</th>
                <td v-for="(cell, columnIndex) in row.cells" :key="columnIndex">
                  <button
                    v-if="cell"
                    type="button"
                    class="sweep-cell"
                    :class="{ 'is-current': cell.path === currentPath, 'is-blurred': blur(cell) }"
                    :title="cell.name"
                    :aria-label="'Open ' + cellLabel(cell, row.label) + ' in the inspector'"
                    @click="pick(cell)"
                  >
                    <img :src="thumbUrl(cell)" :alt="cellLabel(cell, row.label)" loading="lazy" />
                  </button>
                  <div v-else class="sweep-cell sweep-cell--missing">not saved</div>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </dialog>
    </Teleport>`
};
