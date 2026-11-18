import { fileUrl } from '/vue/api.js';

export const ReviewSlideshow = {
  props: {
    assets: { type: Array, required: true },
    selectedPath: { type: String, default: '' },
    blur: { type: Boolean, default: false }
  },
  // Library features (cull ratings) come from useLibraryExtras via provide/inject ('bubba-library').
  inject: { library: { from: 'bubba-library', default: null } },
  data() {
    return {
      items: [],
      index: 0,
      playing: false,
      seconds: 5,
      timer: null,
      failed: false,
      returnFocus: null,
      zoom: 1,
      panX: 0,
      panY: 0,
      drag: null,
      revealed: false
    };
  },
  computed: {
    current() {
      return this.items[this.index];
    },
    isVideo() {
      return String(this.current?.extension).toLowerCase() === '.mp4';
    },
    imageStyle() {
      return {
        transform: `translate(${this.panX}px, ${this.panY}px) scale(${this.zoom})`,
        cursor: this.zoom > 1 ? (this.drag ? 'grabbing' : 'grab') : 'zoom-in',
        transition: this.drag ? 'none' : 'transform 120ms ease-out'
      };
    },
    blurState() {
      if (this.revealed) return null;
      if (this.library?.blurFor) return this.library.blurFor(this.current);
      return this.blur ? { mode: 'image' } : null;
    },
    overlayStyle() {
      return { transform: this.imageStyle.transform, transition: this.imageStyle.transition };
    },
    zoomLabel() {
      return `${Math.round(this.zoom * 100)}%`;
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
    open(startPath) {
      this.items = this.assets.slice();
      if (!this.items.length) return;
      const target = typeof startPath === 'string' && startPath ? startPath : this.selectedPath;
      this.index = Math.max(
        0,
        this.items.findIndex((item) => item.path === target)
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
      this.resetZoom();
      this.playing = false;
      clearTimeout(this.timer);
      this.items = [];
      this.returnFocus?.focus();
    },
    resetZoom() {
      this.zoom = 1;
      this.panX = 0;
      this.panY = 0;
      this.drag = null;
    },
    // Zoom so the image point under (clientX, clientY) stays put. Zoom 1 = fit to the stage.
    zoomTo(nextZoom, clientX, clientY) {
      const image = this.$refs.image;
      const clamped = Math.min(8, Math.max(1, nextZoom));
      if (!image || clamped === this.zoom) return;
      if (clamped === 1) {
        this.resetZoom();
        return;
      }
      const rect = image.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2 - this.panX;
      const centerY = rect.top + rect.height / 2 - this.panY;
      const pointX = clientX ?? centerX + this.panX;
      const pointY = clientY ?? centerY + this.panY;
      const ratio = clamped / this.zoom;
      this.panX = pointX - centerX - ratio * (pointX - centerX - this.panX);
      this.panY = pointY - centerY - ratio * (pointY - centerY - this.panY);
      this.zoom = clamped;
    },
    onWheel(event) {
      if (this.isVideo || this.failed) return;
      event.preventDefault();
      this.zoomTo(this.zoom * Math.exp(-event.deltaY * 0.0015), event.clientX, event.clientY);
    },
    onImageDoubleClick(event) {
      const image = this.$refs.image;
      if (this.zoom > 1) {
        this.resetZoom();
        return;
      }
      // Jump to actual pixel size when the image is downscaled to fit; otherwise a 2.5x close-up.
      const actual = image && image.clientWidth ? image.naturalWidth / image.clientWidth : 0;
      this.zoomTo(actual > 1.2 ? actual : 2.5, event.clientX, event.clientY);
    },
    onPointerDown(event) {
      if (this.zoom <= 1 || event.button !== 0) return;
      event.preventDefault();
      event.currentTarget.setPointerCapture?.(event.pointerId);
      this.drag = { x: event.clientX - this.panX, y: event.clientY - this.panY };
    },
    onPointerMove(event) {
      if (!this.drag) return;
      this.panX = event.clientX - this.drag.x;
      this.panY = event.clientY - this.drag.y;
    },
    onPointerUp() {
      this.drag = null;
    },
    step(direction) {
      this.resetZoom();
      this.revealed = false;
      this.index = (this.index + direction + this.items.length) % this.items.length;
      this.failed = false;
      this.schedule();
    },
    // Cull: 1 = keep, 2 = reject; the same key again clears it. Rating advances to the next item.
    async rate(rating) {
      const item = this.current;
      if (!item || !this.library?.rate) return;
      const next = item.rating === rating ? null : rating;
      const ok = await this.library.rate([item.path], next);
      if (ok && next && this.items.length > 1 && this.current === item) this.step(1);
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
      } else if ((event.key === '+' || event.key === '=') && !this.isVideo) {
        event.preventDefault();
        this.zoomTo(this.zoom * 1.25);
      } else if (event.key === '-' && !this.isVideo) {
        event.preventDefault();
        this.zoomTo(this.zoom / 1.25);
      } else if ((event.key === '1' || event.key === '2') && !event.ctrlKey && !event.metaKey && !event.altKey) {
        event.preventDefault();
        this.rate(event.key === '1' ? 'keep' : 'reject');
      } else if ((event.key === 'v' || event.key === 'V') && !event.ctrlKey && !event.metaKey) {
        event.preventDefault();
        this.revealed = !this.revealed;
      } else if (event.key === '0') {
        event.preventDefault();
        this.resetZoom();
      } else if (event.code === 'Space' && event.target.tagName !== 'BUTTON') {
        event.preventDefault();
        this.toggle();
      }
    }
  },
  template: `
    <button class="button button--compact" type="button" title="Review currently loaded items" :disabled="!assets.length" @click="open()">Slideshow</button>
    <Teleport to="body">
      <dialog ref="dialog" class="review-slideshow" aria-label="Media slideshow" @close="onClose" @keydown="keydown">
        <header class="review-toolbar">
          <div><strong>Review mode</strong><small>{{ index + 1 }} / {{ items.length }} loaded items · ← → to browse · 1 keep · 2 reject · scroll or double-click to zoom · Esc to close</small></div>
          <button ref="close" class="button" type="button" @click="close">Close slideshow</button>
        </header>
        <div class="review-stage" v-if="current" @wheel="onWheel">
          <button v-if="zoom > 1" class="review-zoom-badge" type="button" title="Reset zoom (0)" @click="resetZoom">{{ zoomLabel }} · Reset</button>
          <p v-if="failed" role="status">This media could not be displayed. You can continue to the next item.</p>
          <video v-else-if="isVideo" :key="current.path" :src="fileUrl(current.path)" :class="{ 'review-blurred': blurState }" controls @error="failed = true"></video>
          <img
            v-else
            ref="image"
            :key="current.path"
            :src="fileUrl(current.path)"
            :alt="current.name || current.path"
            :class="{ 'review-blurred': blurState && blurState.mode === 'image' }"
            :style="imageStyle"
            draggable="false"
            @error="failed = true"
            @dblclick="onImageDoubleClick"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
          />
          <component
            :is="library.overlayComponent"
            v-if="library && library.overlayComponent && !failed && !isVideo && blurState && blurState.mode === 'regions'"
            :key="'nsfw-' + current.path"
            fit="contain"
            :regions="blurState.regions"
            :layer-style="overlayStyle"
          />
          <button v-if="!failed && (blurState || revealed)" class="nsfw-reveal nsfw-reveal--stage" type="button" :aria-pressed="revealed" title="Reveal or hide blurred content (V)" @click="revealed = !revealed">{{ revealed ? 'Hide (V)' : 'Reveal (V)' }}</button>
        </div>
        <footer class="review-footer">
          <div class="review-caption">{{ current?.name || current?.path }}</div>
          <div v-if="library" class="review-rating" aria-label="Cull">
            <span class="review-rating-state" :class="current && current.rating ? 'review-rating-state--' + current.rating : ''" role="status">{{ current && current.rating === 'keep' ? '✓ Kept' : current && current.rating === 'reject' ? '✕ Rejected' : 'Unrated' }}</span>
            <button class="button" type="button" :aria-pressed="current && current.rating === 'keep'" title="Keep and go to next (1)" @click="rate('keep')">Keep</button>
            <button class="button" type="button" :aria-pressed="current && current.rating === 'reject'" title="Reject and go to next (2)" @click="rate('reject')">Reject</button>
          </div>
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
