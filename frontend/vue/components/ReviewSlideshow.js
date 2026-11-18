import { fileUrl } from '/vue/api.js';

export const ReviewSlideshow = {
  props: {
    assets: { type: Array, required: true },
    selectedPath: { type: String, default: '' },
    blur: { type: Boolean, default: false }
  },
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
      drag: null
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
      } else if ((event.key === '+' || event.key === '=') && !this.isVideo) {
        event.preventDefault();
        this.zoomTo(this.zoom * 1.25);
      } else if (event.key === '-' && !this.isVideo) {
        event.preventDefault();
        this.zoomTo(this.zoom / 1.25);
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
          <div><strong>Review mode</strong><small>{{ index + 1 }} / {{ items.length }} loaded items · ← → to browse · scroll or double-click to zoom · Esc to close</small></div>
          <button ref="close" class="button" type="button" @click="close">Close slideshow</button>
        </header>
        <div class="review-stage" v-if="current" @wheel="onWheel">
          <button v-if="zoom > 1" class="review-zoom-badge" type="button" title="Reset zoom (0)" @click="resetZoom">{{ zoomLabel }} · Reset</button>
          <p v-if="failed" role="status">This media could not be displayed. You can continue to the next item.</p>
          <video v-else-if="isVideo" :key="current.path" :src="fileUrl(current.path)" :class="{ 'review-blurred': blur }" controls @error="failed = true"></video>
          <img
            v-else
            ref="image"
            :key="current.path"
            :src="fileUrl(current.path)"
            :alt="current.name || current.path"
            :class="{ 'review-blurred': blur }"
            :style="imageStyle"
            draggable="false"
            @error="failed = true"
            @dblclick="onImageDoubleClick"
            @pointerdown="onPointerDown"
            @pointermove="onPointerMove"
            @pointerup="onPointerUp"
            @pointercancel="onPointerUp"
          />
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
