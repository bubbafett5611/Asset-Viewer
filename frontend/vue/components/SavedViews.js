const STORAGE_KEY = 'bubba_media_saved_views_v1';
const FILTER_KEYS = ['folder', 'q', 'ext', 'metadataBadge', 'sortBy', 'sortDir'];

export const SavedViews = {
  props: { filters: { type: Object, required: true } },
  data() {
    let views = [];
    try {
      const stored = JSON.parse(localStorage.getItem(STORAGE_KEY) || '[]');
      if (Array.isArray(stored))
        views = stored.filter(
          (view) =>
            view &&
            typeof view.name === 'string' &&
            typeof view.root === 'string' &&
            view.filters &&
            FILTER_KEYS.every((key) => typeof view.filters[key] === 'string')
        );
    } catch {
      /* A damaged or unavailable store starts empty. */
    }
    return { views, name: '', message: '', editing: false, returnFocus: null };
  },
  computed: {
    rootViews() {
      return this.views.filter((view) => view.root === this.filters.root);
    }
  },
  methods: {
    openSave(event) {
      this.returnFocus = event?.currentTarget;
      this.editing = true;
      this.$nextTick(() => this.$refs.nameInput?.focus());
    },
    closeSave() {
      this.editing = false;
      this.returnFocus?.focus();
    },
    persist(next) {
      try {
        localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
        this.views = next;
        return true;
      } catch {
        this.message = 'Could not save views. Browser storage may be full or disabled.';
        return false;
      }
    },
    save() {
      const name = this.name.trim();
      if (!name || !this.filters.root) return;
      const filters = Object.fromEntries(FILTER_KEYS.map((key) => [key, String(this.filters[key] || '')]));
      const next = this.views.filter((view) => view.root !== this.filters.root || view.name !== name);
      if (this.persist([...next, { name, root: this.filters.root, filters }])) {
        this.name = '';
        this.message = `Saved “${name}”.`;
        this.closeSave();
      }
    },
    apply(view) {
      for (const key of FILTER_KEYS) this.filters[key] = view.filters[key];
      this.message = `Opened “${view.name}”.`;
    },
    remove(view) {
      if (this.persist(this.views.filter((item) => item !== view))) this.message = `Removed “${view.name}”.`;
    }
  },
  template: `
    <section class="saved-views" aria-label="Saved views">
      <h2 class="folder-tree-heading">Saved views <span v-if="rootViews.length">({{ rootViews.length }})</span></h2>
      <div class="saved-views-content">
        <p v-if="!rootViews.length && !editing">Save a search from the toolbar to find it here.</p>
        <form v-if="editing" class="saved-view-form" @submit.prevent="save" @keydown.esc.stop.prevent="closeSave">
          <input ref="nameInput" v-model="name" class="input" aria-label="Saved view name" placeholder="e.g. Recent PNG renders" maxlength="60" required />
          <button class="button button--compact" :disabled="!name.trim() || !filters.root">Save view</button>
          <button class="button button--compact button--ghost" type="button" @click="closeSave">Cancel</button>
        </form>
        <small v-if="editing">Stored in this browser. An existing name replaces that view.</small>
        <div class="saved-view-chips">
          <span v-for="view in rootViews" :key="view.name" class="saved-view-chip">
            <button class="button button--compact" type="button" @click="apply(view)">{{ view.name }}</button>
            <button class="button button--compact button--ghost" type="button" :aria-label="'Remove saved view ' + view.name" @click="remove(view)">×</button>
          </span>
        </div>
        <span role="status">{{ message }}</span>
      </div>
    </section>`
};
