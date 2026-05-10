import { computed } from '/vendor/vue.esm-browser.prod.js';

export function useStats(options) {
  const {
    API,
    buildQuery,
    roots,
    filters,
    rootStatsReports,
    metadataHealth,
    metadataHealthStatus,
    isLoadingMetadataHealth,
    folderStats,
    folderStatsStatus,
    isLoadingFolderStats,
    formatBytes
  } = options;

  function formatNumber(value) {
    return Number(value || 0).toLocaleString();
  }

  function metadataCoveragePercent(value, source) {
    const denominator = source?.total_assets || source?.png_assets || source?.image_files || source?.total_files || 0;
    if (!denominator) {
      return 0;
    }
    return Math.max(0, Math.min(100, Math.round((Number(value || 0) / denominator) * 100)));
  }

  function buildFolderStatsMetrics(stats) {
    if (!stats) {
      return [];
    }
    return [
      { key: 'files', label: 'Files', value: formatNumber(stats.total_files || 0), note: 'All files' },
      { key: 'size', label: 'Storage', value: formatBytes(stats.total_bytes || 0), note: 'Total size' },
      { key: 'images', label: 'Images', value: formatNumber(stats.image_files || 0), note: 'Previewable files' },
      { key: 'other', label: 'Other', value: formatNumber(stats.other_files || 0), note: 'Everything else' }
    ];
  }

  function buildMetadataStatsMetrics(source) {
    if (!source) {
      return [];
    }
    return [
      { key: 'bubba', label: 'Bubba', value: source.bubba_metadata || 0 },
      { key: 'workflow', label: 'Workflow', value: source.workflow || 0 },
      { key: 'parameters', label: 'Params', value: source.parameters || 0 },
      { key: 'missing', label: 'Missing', value: source.no_tracked_metadata || 0 },
      { key: 'invalid', label: 'Invalid', value: source.invalid_bubba_metadata || 0 }
    ].map((item) => ({
      ...item,
      valueLabel: formatNumber(item.value),
      percent: metadataCoveragePercent(item.value, source)
    }));
  }

  function defaultRootStatsState() {
    return {
      folderStats: null,
      metadataHealth: null,
      folderStatsStatus: 'Folder stats not loaded.',
      metadataHealthStatus: 'Metadata report not loaded.',
      isLoadingFolderStats: false,
      isLoadingMetadataHealth: false
    };
  }

  function statsStateForRoot(root) {
    const key = root?.key || '';
    if (!key) {
      return defaultRootStatsState();
    }
    if (!rootStatsReports[key]) {
      rootStatsReports[key] = defaultRootStatsState();
    }
    return rootStatsReports[key];
  }

  const folderStatsSummary = computed(() => {
    if (!folderStats.value) {
      return [];
    }
    return [
      `Files ${folderStats.value.total_files || 0}`,
      `Size ${formatBytes(folderStats.value.total_bytes || 0)}`,
      `Images ${folderStats.value.image_files || 0}`,
      `Bubba ${folderStats.value.bubba_metadata || 0}`,
      `Workflow ${folderStats.value.workflow || 0}`,
      `Params ${folderStats.value.parameters || 0}`,
      `Missing ${folderStats.value.no_tracked_metadata || 0}`
    ];
  });

  const folderStatsMetrics = computed(() => buildFolderStatsMetrics(folderStats.value));
  const metadataStatsMetrics = computed(() => {
    const source = metadataHealth.value || folderStats.value;
    return buildMetadataStatsMetrics(source);
  });
  const statsPrimaryCount = computed(() => {
    const source = metadataHealth.value || folderStats.value;
    if (!source) {
      return 0;
    }
    return source.total_assets || source.png_assets || source.image_files || source.total_files || 0;
  });
  const statsRootReports = computed(() =>
    roots.value.map((root) => {
      const state = statsStateForRoot(root);
      const metadataSource = state.metadataHealth || state.folderStats;
      return {
        key: root.key,
        label: root.label || root.key,
        folderStats: state.folderStats,
        metadataHealth: state.metadataHealth,
        folderStatsStatus: state.folderStatsStatus,
        metadataHealthStatus: state.metadataHealthStatus,
        isLoadingFolderStats: state.isLoadingFolderStats,
        isLoadingMetadataHealth: state.isLoadingMetadataHealth,
        folderMetrics: buildFolderStatsMetrics(state.folderStats),
        metadataMetrics: buildMetadataStatsMetrics(metadataSource)
      };
    })
  );
  const isLoadingAnyFolderStats = computed(() => statsRootReports.value.some((report) => report.isLoadingFolderStats));
  const isLoadingAnyMetadataHealth = computed(() =>
    statsRootReports.value.some((report) => report.isLoadingMetadataHealth)
  );

  async function fetchRootMetadataHealth(root, { refresh = true, cacheOnly = false } = {}) {
    if (!root?.key) {
      return;
    }
    const state = statsStateForRoot(root);
    state.isLoadingMetadataHealth = true;
    state.metadataHealthStatus = 'Loading metadata report...';
    try {
      const response = await fetch(buildQuery(API.metadataHealth, { root: root.key, refresh, cache_only: cacheOnly }));
      if (!response.ok) {
        throw new Error(`Metadata report failed (${response.status})`);
      }
      const payload = await response.json();
      state.metadataHealth = payload.stats || null;
      if (payload.stats) {
        state.metadataHealthStatus = payload.cached ? 'Loaded cached metadata report.' : 'Metadata report loaded.';
      } else {
        state.metadataHealthStatus = 'Metadata report not loaded.';
      }
    } catch (error) {
      console.error(error);
      state.metadataHealth = null;
      state.metadataHealthStatus = error?.message || 'Metadata report failed.';
    } finally {
      state.isLoadingMetadataHealth = false;
    }
  }

  async function fetchMetadataHealth(options = {}) {
    const targets = roots.value.length ? roots.value : filters.root ? [{ key: filters.root, label: filters.root }] : [];
    if (!targets.length) {
      metadataHealthStatus.value = 'Select a folder before loading metadata report.';
      return;
    }
    isLoadingMetadataHealth.value = true;
    await Promise.all(targets.map((root) => fetchRootMetadataHealth(root, options)));
    metadataHealth.value = statsStateForRoot(targets[0]).metadataHealth;
    metadataHealthStatus.value = 'Metadata reports loaded.';
    isLoadingMetadataHealth.value = false;
  }

  async function fetchRootFolderStats(root, { refresh = false } = {}) {
    if (!root?.key) {
      return;
    }
    const state = statsStateForRoot(root);
    state.isLoadingFolderStats = true;
    state.folderStatsStatus = 'Loading folder stats...';
    try {
      const response = await fetch(buildQuery(API.stats, { root: root.key, refresh }));
      if (!response.ok) {
        throw new Error(`Folder stats failed (${response.status})`);
      }
      const payload = await response.json();
      state.folderStats = payload.stats || null;
      state.folderStatsStatus = payload.cached ? 'Loaded cached folder stats.' : 'Folder stats loaded.';
    } catch (error) {
      console.error(error);
      state.folderStats = null;
      state.folderStatsStatus = error?.message || 'Folder stats failed.';
    } finally {
      state.isLoadingFolderStats = false;
    }
  }

  async function fetchFolderStats(options = {}) {
    const targets = roots.value.length ? roots.value : filters.root ? [{ key: filters.root, label: filters.root }] : [];
    if (!targets.length) {
      folderStatsStatus.value = 'Select a folder before loading folder stats.';
      return;
    }
    isLoadingFolderStats.value = true;
    await Promise.all(targets.map((root) => fetchRootFolderStats(root, options)));
    folderStats.value = statsStateForRoot(targets[0]).folderStats;
    folderStatsStatus.value = 'Folder stats loaded.';
    isLoadingFolderStats.value = false;
  }

  return {
    folderStatsSummary,
    folderStatsMetrics,
    metadataStatsMetrics,
    statsPrimaryCount,
    statsRootReports,
    isLoadingAnyFolderStats,
    isLoadingAnyMetadataHealth,
    fetchRootMetadataHealth,
    fetchMetadataHealth,
    fetchRootFolderStats,
    fetchFolderStats
  };
}
