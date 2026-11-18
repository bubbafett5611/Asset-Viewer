/**
 * Blurs NSFW regions over the <img> rendered immediately before this component.
 * Region boxes are normalised [x1, y1, x2, y2] in source-image space; `fit` says how the image is drawn
 * inside its element ('cover' for grid thumbnails, 'contain' where the element already matches the image).
 */
export function imageBox(image, fit) {
  const width = image.offsetWidth;
  const height = image.offsetHeight;
  const naturalWidth = image.naturalWidth || width;
  const naturalHeight = image.naturalHeight || height;
  if (!width || !height || !naturalWidth || !naturalHeight) return null;
  const scale =
    fit === 'cover'
      ? Math.max(width / naturalWidth, height / naturalHeight)
      : Math.min(width / naturalWidth, height / naturalHeight);
  const drawnWidth = naturalWidth * scale;
  const drawnHeight = naturalHeight * scale;
  return {
    left: image.offsetLeft + (width - drawnWidth) / 2,
    top: image.offsetTop + (height - drawnHeight) / 2,
    width: drawnWidth,
    height: drawnHeight
  };
}

export const NsfwOverlay = {
  name: 'NsfwOverlay',
  props: {
    regions: { type: Array, default: () => [] },
    fit: { type: String, default: 'contain' },
    layerStyle: { type: Object, default: () => ({}) }
  },
  data() {
    return { box: null };
  },
  computed: {
    style() {
      if (!this.box) return { display: 'none' };
      return {
        left: `${this.box.left}px`,
        top: `${this.box.top}px`,
        width: `${this.box.width}px`,
        height: `${this.box.height}px`,
        ...this.layerStyle
      };
    }
  },
  mounted() {
    this.image = this.$el.previousElementSibling;
    if (!this.image || this.image.tagName !== 'IMG') return;
    this.measure = () => {
      this.box = imageBox(this.image, this.fit);
    };
    this.image.addEventListener('load', this.measure);
    if (typeof ResizeObserver !== 'undefined') {
      this.observer = new ResizeObserver(this.measure);
      this.observer.observe(this.image);
    }
    if (this.image.complete) this.measure();
  },
  beforeUnmount() {
    this.image?.removeEventListener('load', this.measure);
    this.observer?.disconnect();
  },
  methods: {
    regionStyle(region) {
      const [x1, y1, x2, y2] = region.box;
      return {
        left: `${x1 * 100}%`,
        top: `${y1 * 100}%`,
        width: `${Math.max(0, x2 - x1) * 100}%`,
        height: `${Math.max(0, y2 - y1) * 100}%`
      };
    }
  },
  template: `
    <div class="nsfw-layer" :style="style" aria-hidden="true">
      <span v-for="(region, index) in regions" :key="index" class="nsfw-region" :style="regionStyle(region)"></span>
    </div>`
};
