import { computed, nextTick, onMounted, onUnmounted, ref, watch } from '/vendor/vue.esm-browser.prod.js';

export function useViewerLayout(options) {
  const { assets, filters, getDensityConfig } = options;

  const detailsWidth = ref(340);
  const inspectorVisible = ref(true);
  const viewportWidth = ref(Math.max(1024, window.innerWidth));
  const previewHeight = ref(320);
  const assetListRef = ref(null);
  const searchInputRef = ref(null);
  const assetScrollTop = ref(0);
  const assetViewportHeight = ref(0);
  const assetListWidth = ref(0);
  let resizeObserver = null;

  const densityClass = computed(() => `density-${filters.density}`);
  const densityConfig = computed(() => getDensityConfig(filters.density));
  const layoutStyle = computed(() => ({
    '--details-width': `${Math.max(280, Math.min(detailsWidth.value, viewportWidth.value - 220 - 24 - 16 - 420))}px`,
    '--preview-height': `${previewHeight.value}px`
  }));
  const assetListStyle = computed(() => ({
    '--asset-min-col-width': `${densityConfig.value.minWidth}px`,
    '--asset-row-height': `${densityConfig.value.rowHeight}px`,
    '--asset-gap': filters.density === 'large' ? '14px' : '10px'
  }));
  const shouldVirtualize = computed(() => assets.value.length > 240);
  const virtualColumnCount = computed(() => {
    const width = Math.max(1, (assetListWidth.value || assetListRef.value?.clientWidth || 1) - 12);
    const gap = filters.density === 'large' ? 14 : 10;
    return Math.max(1, Math.floor((width + gap) / (densityConfig.value.minWidth + gap)));
  });
  const virtualRowHeight = computed(() => densityConfig.value.rowHeight);
  const virtualRowCount = computed(() => Math.ceil(assets.value.length / virtualColumnCount.value));
  const virtualStartRow = computed(() => Math.max(0, Math.floor(assetScrollTop.value / virtualRowHeight.value) - 2));
  const virtualVisibleRows = computed(() => Math.ceil((assetViewportHeight.value || 1) / virtualRowHeight.value) + 5);
  const virtualStartIndex = computed(() => virtualStartRow.value * virtualColumnCount.value);
  const virtualEndIndex = computed(() =>
    Math.min(assets.value.length, (virtualStartRow.value + virtualVisibleRows.value) * virtualColumnCount.value)
  );
  const visibleAssets = computed(() => {
    if (!shouldVirtualize.value) {
      return assets.value;
    }
    return assets.value.slice(virtualStartIndex.value, virtualEndIndex.value);
  });
  const virtualSpacerStyle = computed(() => ({ height: `${virtualRowCount.value * virtualRowHeight.value}px` }));
  const virtualWindowStyle = computed(() => ({
    transform: `translateY(${virtualStartRow.value * virtualRowHeight.value}px)`,
    gridTemplateColumns: `repeat(${virtualColumnCount.value}, minmax(0, 1fr))`
  }));

  function measureAssetList() {
    viewportWidth.value = Math.max(1024, window.innerWidth);
    const element = assetListRef.value;
    if (!element) {
      return;
    }
    assetViewportHeight.value = element.clientHeight;
    assetListWidth.value = element.clientWidth;
    assetScrollTop.value = element.scrollTop;
  }

  function onAssetListScroll() {
    assetScrollTop.value = assetListRef.value?.scrollTop || 0;
  }

  function setAssetListRef(element) {
    assetListRef.value = element;
    if (resizeObserver) {
      resizeObserver.disconnect();
      if (assetListRef.value) {
        resizeObserver.observe(assetListRef.value);
      }
    }
  }

  function setSearchInputRef(element) {
    searchInputRef.value = element;
  }

  function startDetailsResize(event) {
    const clampWidth = (value) => Math.max(280, Math.min(viewportWidth.value - 220 - 24 - 16 - 420, value));
    if (event.key) {
      if (['ArrowLeft', 'ArrowRight'].includes(event.key)) {
        event.preventDefault();
        detailsWidth.value = clampWidth(detailsWidth.value + (event.key === 'ArrowLeft' ? 16 : -16));
      }
      return;
    }
    if (event.button !== 0) {
      return;
    }

    const startX = event.clientX;
    const startWidth = detailsWidth.value;

    function onMove(moveEvent) {
      const delta = startX - moveEvent.clientX;
      detailsWidth.value = clampWidth(startWidth + delta);
    }

    function onUp() {
      document.body.classList.remove('panel-resizing');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }

    document.body.classList.add('panel-resizing');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  function startPreviewResize(event) {
    const panelHeight = event.currentTarget?.closest('.asset-details-panel')?.clientHeight || window.innerHeight;
    const clampHeight = (value) => Math.max(140, Math.min(720, panelHeight - 360, value));
    if (event.key) {
      if (['ArrowUp', 'ArrowDown'].includes(event.key)) {
        event.preventDefault();
        previewHeight.value = clampHeight(previewHeight.value + (event.key === 'ArrowDown' ? 16 : -16));
      }
      return;
    }
    if (event.button !== 0) {
      return;
    }
    event.preventDefault();

    const startY = event.clientY;
    const startHeight = previewHeight.value;

    function onMove(moveEvent) {
      const delta = moveEvent.clientY - startY;
      previewHeight.value = clampHeight(startHeight + delta);
    }

    function onUp() {
      document.body.classList.remove('preview-resizing');
      document.removeEventListener('mousemove', onMove);
      document.removeEventListener('mouseup', onUp);
    }

    document.body.classList.add('preview-resizing');
    document.addEventListener('mousemove', onMove);
    document.addEventListener('mouseup', onUp);
  }

  watch(
    () => [assets.value.length, filters.density],
    async () => {
      await nextTick();
      measureAssetList();
    }
  );

  onMounted(() => {
    if (window.ResizeObserver) {
      resizeObserver = new ResizeObserver(measureAssetList);
      if (assetListRef.value) {
        resizeObserver.observe(assetListRef.value);
      }
    }
  });

  onUnmounted(() => {
    resizeObserver?.disconnect();
  });

  return {
    inspectorVisible,
    toggleInspector: () => {
      inspectorVisible.value = !inspectorVisible.value;
      nextTick(measureAssetList);
    },
    detailsWidth,
    previewHeight,
    assetListRef,
    searchInputRef,
    densityClass,
    densityConfig,
    layoutStyle,
    assetListStyle,
    shouldVirtualize,
    virtualColumnCount,
    virtualRowHeight,
    visibleAssets,
    virtualSpacerStyle,
    virtualWindowStyle,
    measureAssetList,
    onAssetListScroll,
    setAssetListRef,
    setSearchInputRef,
    startDetailsResize,
    startPreviewResize
  };
}
