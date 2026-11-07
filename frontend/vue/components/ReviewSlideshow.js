import { fileUrl } from '/vue/api.js';

export const ReviewSlideshow = {
  props: {
    assets: { type: Array, required: true },
    selectedPath: { type: String, default: '' },
    blur: { type: Boolean, default: false }
  },
  data() {
    return { items: [], index: 0, playing: false, seconds: 5, timer: null, failed: false, returnFocus: null };
  },
  computed: {
    current() {
      return this.items[this.index];
    },
    isVideo() {
      return String(this.current?.extension).toLowerCase() === '.mp4';
    }
  },
  watch: {
    seconds() {
      this.schedule();
    }
  },
  beforeUnmount() {
    clearTimeout(this.timer);
  },
  methods: {
    fileUrl,
    open() {
      this.items = this.assets.slice();
      if (!this.items.length) return;
      this.index = Math.max(
        0,
        this.items.findIndex((item) => item.path === this.selectedPath)
      );
      this.failed = false;
      this.returnFocus = document.activeElement;
      this.$refs.dialog.showModal();
      this.$refs.close.focus();
    },
    close() {
      this.$refs.dialog.close();
    },
    onClose() {
      this.playing = false;
      clearTimeout(this.timer);
      this.items = [];
      this.returnFocus?.focus();
    },
    step(direction) {
      this.index = (this.index + direction + this.items.length) % this.items.length;
      this.failed = false;
      this.schedule();
    },
    toggle() {
      this.playing = !this.playing;
      this.schedule();
    },
    schedule() {
      clearTimeout(this.timer);
      if (this.playing && this.items.length > 1) {
        this.timer = setTimeout(() => this.step(1), Number(this.seconds) * 1000);
      }
    },
    keydown(event) {
      event.stopPropagation();
      if (['INPUT', 'SELECT', 'VIDEO'].includes(event.target.tagName)) return;
      if (event.key === 'ArrowRight' || event.key === 'ArrowLeft') {
        event.preventDefault();
        this.step(event.key === 'ArrowRight' ? 1 : -1);
      } else if (event.code === 'Space' && event.target.tagName !== 'BUTTON') {
        event.preventDefault();
        this.toggle();
      }
    }
  },
  template: `
    <button class="button button--compact" type="button" title="Review currently loaded items" :disabled="!assets.length" @click="open">Slideshow</button>
    <Teleport to="body">
      <dialog ref="dialog" class="review-slideshow" aria-label="Media slideshow" @close="onClose" @keydown="keydown">
        <header class="review-toolbar">
          <div><strong>Review mode</strong><small>{{ index + 1 }} / {{ items.length }} loaded items · ← → to browse · Esc to close</small></div>
          <button ref="close" class="button" type="button" @click="close">Close slideshow</button>
        </header>
        <div class="review-stage" v-if="current">
          <p v-if="failed" role="status">This media could not be displayed. You can continue to the next item.</p>
          <video v-else-if="isVideo" :key="current.path" :src="fileUrl(current.path)" :class="{ 'review-blurred': blur }" controls @error="failed = true"></video>
          <img v-else :key="current.path" :src="fileUrl(current.path)" :alt="current.name || current.path" :class="{ 'review-blurred': blur }" @error="failed = true" />
        </div>
        <footer class="review-footer">
          <div class="review-caption">{{ current?.name || current?.path }}</div>
          <div class="review-controls">
            <button class="button" type="button" :disabled="items.length < 2" @click="step(-1)">Previous</button>
            <button class="button" type="button" :disabled="items.length < 2" @click="toggle">{{ playing ? 'Pause' : 'Play' }}</button>
            <button class="button" type="button" :disabled="items.length < 2" @click="step(1)">Next</button>
            <label>Interval <select v-model="seconds" class="select"><option :value="3">3 seconds</option><option :value="5">5 seconds</option><option :value="10">10 seconds</option></select></label>
          </div>
        </footer>
      </dialog>
    </Teleport>`
};
