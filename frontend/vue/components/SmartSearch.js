import { LIBRARY_KEY, searchToken } from '/vue/composables/useLibraryExtras.js';

const FACET_FIELDS = {
  model: 'models',
  lora: 'loras',
  sampler: 'samplers',
  scheduler: 'schedulers',
  prompt: 'prompt_tags'
};
const KEY_SUGGESTIONS = [
  { insert: 'model:', hint: 'checkpoint name' },
  { insert: 'lora:', hint: 'LoRA used' },
  { insert: 'sampler:', hint: 'e.g. euler_ancestral' },
  { insert: 'scheduler:', hint: 'e.g. karras' },
  { insert: 'seed:', hint: 'exact seed' },
  { insert: 'steps:', hint: 'exact steps' },
  { insert: 'cfg:', hint: 'exact CFG' },
  { insert: 'prompt:', hint: 'positive prompt text' },
  { insert: 'neg:', hint: 'negative prompt text' },
  { insert: 'on:', hint: 'YYYY-MM-DD, today, yesterday' },
  { insert: 'after:', hint: 'YYYY-MM-DD' },
  { insert: 'before:', hint: 'YYYY-MM-DD' },
  { insert: 'size>', hint: 'e.g. size>2mb' },
  { insert: 'size<', hint: 'e.g. size<500kb' },
  { insert: 'folder:', hint: 'folder path contains' },
  { insert: 'name:', hint: 'filename contains' },
  { insert: 'ext:', hint: 'png, jpg, mp4…' },
  { insert: 'is:fav ', hint: 'favorites only' }
];

export const SmartSearch = {
  name: 'SmartSearch',
  inject: { library: { from: LIBRARY_KEY, default: null } },
  props: {
    modelValue: { type: String, default: '' },
    inputRef: { type: Function, default: null }
  },
  emits: ['update:modelValue'],
  data() {
    return { focused: false, activeIndex: -1, helpOpen: false };
  },
  computed: {
    lastToken() {
      const value = this.modelValue || '';
      if (/\s$/.test(value)) return '';
      // A token with an opening quote may contain spaces: model:"my model
      const quoted = /(-?[a-z]+:=?"[^"]*)$/i.exec(value);
      if (quoted) return quoted[1];
      return value.split(/\s+/).pop() || '';
    },
    suggestions() {
      const token = this.lastToken;
      if (!token) return [];
      const fieldMatch = /^(-?)([a-z]+):=?"?(.*)$/i.exec(token);
      if (fieldMatch) {
        const [, negate, field, partial] = fieldMatch;
        const facetKey = FACET_FIELDS[field.toLowerCase()];
        const values = this.library?.facets?.[facetKey] || [];
        const needle = partial.toLowerCase();
        return values
          .filter((item) => String(item.value).toLowerCase().includes(needle))
          .slice(0, 8)
          .map((item) => ({
            label: String(item.value),
            hint: `${item.count.toLocaleString()} images`,
            insert: `${negate}${searchToken(field.toLowerCase(), item.value, { exact: field.toLowerCase() !== 'prompt' })} `
          }));
      }
      const needle = token.replace(/^-/, '').toLowerCase();
      if (!needle) return [];
      return KEY_SUGGESTIONS.filter((item) => item.insert.startsWith(needle) && item.insert !== needle)
        .slice(0, 6)
        .map((item) => ({ label: item.insert.trim(), hint: item.hint, insert: item.insert }));
    },
    open() {
      return this.focused && this.suggestions.length > 0;
    }
  },
  watch: {
    suggestions() {
      this.activeIndex = -1;
    }
  },
  methods: {
    setInput(element) {
      this.input = element;
      this.inputRef?.(element);
    },
    accept(suggestion) {
      const value = this.modelValue || '';
      const token = this.lastToken;
      const base = token ? value.slice(0, value.length - token.length) : value;
      this.$emit('update:modelValue', base + suggestion.insert);
      this.$nextTick(() => this.input?.focus());
    },
    onKeydown(event) {
      if (!this.open) return;
      if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
        event.preventDefault();
        event.stopPropagation();
        const step = event.key === 'ArrowDown' ? 1 : -1;
        const count = this.suggestions.length;
        this.activeIndex = (this.activeIndex + step + count + 1) % (count + 1);
        if (this.activeIndex === count) this.activeIndex = -1;
      } else if ((event.key === 'Enter' || event.key === 'Tab') && (this.activeIndex >= 0 || event.key === 'Tab')) {
        event.preventDefault();
        event.stopPropagation();
        this.accept(this.suggestions[Math.max(0, this.activeIndex)]);
      } else if (event.key === 'Escape') {
        event.stopPropagation();
        this.focused = false;
      }
    },
    onBlur() {
      // Let a click on a suggestion land before closing.
      setTimeout(() => {
        this.focused = false;
      }, 120);
    }
  },
  template: `
    <div class="smart-search">
      <input
        id="searchInput"
        :ref="setInput"
        :value="modelValue"
        class="input search-field"
        type="search"
        aria-label="Search"
        placeholder="Search…  try model:  lora:  seed:  on:today  size>2mb"
        autocomplete="off"
        aria-autocomplete="list"
        :aria-controls="open ? 'smart-search-list' : undefined"
        :aria-activedescendant="activeIndex >= 0 ? 'smart-search-option-' + activeIndex : undefined"
        @input="$emit('update:modelValue', $event.target.value)"
        @focus="focused = true"
        @blur="onBlur"
        @keydown="onKeydown"
      />
      <button class="smart-search-help-button" type="button" :aria-expanded="helpOpen" aria-label="Search syntax help" title="Search syntax" @click="helpOpen = !helpOpen">?</button>
      <ul v-if="open" id="smart-search-list" class="smart-search-list" role="listbox">
        <li
          v-for="(suggestion, index) in suggestions"
          :id="'smart-search-option-' + index"
          :key="suggestion.insert"
          role="option"
          :aria-selected="index === activeIndex"
          :class="{ active: index === activeIndex }"
          @mousedown.prevent="accept(suggestion)"
        >
          <span class="smart-search-label">{{ suggestion.label }}</span>
          <span class="smart-search-hint">{{ suggestion.hint }}</span>
        </li>
      </ul>
      <div v-if="helpOpen" class="smart-search-help" role="note">
        <strong>Search syntax</strong>
        <dl>
          <div><dt>red hair</dt><dd>every word must match (name, path or metadata)</dd></div>
          <div><dt>"exact phrase"</dt><dd>match the phrase as written</dd></div>
          <div><dt>model:anima lora:detail</dt><dd>checkpoint / LoRA contains</dd></div>
          <div><dt>model:=exact_name</dt><dd>whole name only</dd></div>
          <div><dt>sampler: scheduler: prompt: neg:</dt><dd>generation fields</dd></div>
          <div><dt>seed:123 steps:30 cfg:7</dt><dd>exact values</dd></div>
          <div><dt>on:today after:2026-11-01 before:…</dt><dd>dates (on:2026-11 = month)</dd></div>
          <div><dt>size>2mb size<500kb</dt><dd>file size</dd></div>
          <div><dt>-word -lora:foo</dt><dd>exclude</dd></div>
          <div><dt>is:fav folder: name: ext:png</dt><dd>favorites, location, type</dd></div>
        </dl>
      </div>
    </div>
  `
};
