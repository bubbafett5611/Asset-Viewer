export const StatsView = {
  name: 'StatsView',
  props: {
    layoutStyle: {
      type: Object,
      required: true
    },
    statsRootReports: {
      type: Array,
      required: true
    },
    isLoadingAnyFolderStats: {
      type: Boolean,
      default: false
    },
    isLoadingAnyMetadataHealth: {
      type: Boolean,
      default: false
    },
    fetchFolderStats: {
      type: Function,
      required: true
    },
    fetchMetadataHealth: {
      type: Function,
      required: true
    },
    fetchRootFolderStats: {
      type: Function,
      required: true
    },
    fetchRootMetadataHealth: {
      type: Function,
      required: true
    },
    exportMetadataHealth: {
      type: Function,
      required: true
    }
  },
  template: `
        <div class="layout layout--single layout--utility stats-layout tab-panel" :style="layoutStyle">
            <section class="panel stats-panel">
                <div class="settings-header stats-header">
                    <div>
                        <h2>Stats</h2>
                        <p>{{ statsRootReports.length }} root{{ statsRootReports.length === 1 ? '' : 's' }}</p>
                    </div>
                    <div class="stats-header-actions">
                        <button class="button button--compact" type="button" :disabled="isLoadingAnyFolderStats" @click="fetchFolderStats({ refresh: true })">
                            {{ isLoadingAnyFolderStats ? 'Refreshing...' : 'Refresh all stats' }}
                        </button>
                        <button class="button button--compact" type="button" :disabled="isLoadingAnyMetadataHealth" @click="fetchMetadataHealth({ refresh: true })">
                            {{ isLoadingAnyMetadataHealth ? 'Scanning...' : 'Scan all metadata' }}
                        </button>
                    </div>
                </div>

                <div class="stats-content">
                    <div v-if="!statsRootReports.length" class="stats-empty">No roots configured.</div>
                    <article v-for="report in statsRootReports" :key="report.key" class="stats-root">
                        <div class="stats-root-header">
                            <div>
                                <h3>{{ report.label }}</h3>
                                <p>{{ report.key }}</p>
                            </div>
                            <div class="stats-header-actions">
                                <button class="button button--compact" type="button" :disabled="report.isLoadingFolderStats" @click="fetchRootFolderStats(report, { refresh: true })">
                                    {{ report.isLoadingFolderStats ? 'Refreshing...' : 'Refresh stats' }}
                                </button>
                                <button class="button button--compact" type="button" :disabled="report.isLoadingMetadataHealth" @click="fetchRootMetadataHealth(report, { refresh: true })">
                                    {{ report.isLoadingMetadataHealth ? 'Scanning...' : 'Scan metadata' }}
                                </button>
                            </div>
                        </div>

                        <section class="stats-block">
                            <div class="stats-block-header">
                                <div>
                                    <h4>Folder Overview</h4>
                                    <p>Current folder snapshot</p>
                                </div>
                            </div>
                            <div v-if="report.folderStats" class="stats-metric-grid">
                                <div v-for="metric in report.folderMetrics" :key="metric.key" class="stats-metric">
                                    <span>{{ metric.label }}</span>
                                    <strong>{{ metric.value }}</strong>
                                    <small>{{ metric.note }}</small>
                                </div>
                            </div>
                            <div v-else class="stats-empty">{{ report.folderStatsStatus }}</div>
                        </section>

                        <section class="stats-block">
                            <div class="stats-block-header">
                                <div>
                                    <h4>Metadata Coverage</h4>
                                    <p v-if="report.metadataHealth">Scanned {{ report.metadataHealth.total_assets }} media item(s), including {{ report.metadataHealth.png_assets }} PNG files.</p>
                                    <p v-else>Scan PNG metadata coverage for this root.</p>
                                </div>
                                <div v-if="report.metadataHealth" class="stats-export-actions">
                                    <button class="inline-export" type="button" @click="exportMetadataHealth('json', report.metadataHealth, report.label)">JSON</button>
                                    <button class="inline-export" type="button" @click="exportMetadataHealth('csv', report.metadataHealth, report.label)">CSV</button>
                                </div>
                            </div>
                            <div v-if="report.metadataMetrics.length" class="stats-coverage-list">
                                <div v-for="metric in report.metadataMetrics" :key="metric.key" class="stats-coverage-row">
                                    <div class="stats-coverage-label">
                                        <span>{{ metric.label }}</span>
                                        <strong>{{ metric.valueLabel }}</strong>
                                    </div>
                                    <div class="stats-coverage-track" aria-hidden="true">
                                        <span :style="{ width: metric.percent + '%' }"></span>
                                    </div>
                                    <small>{{ metric.percent }}%</small>
                                </div>
                            </div>
                            <div v-else class="stats-empty">{{ report.metadataHealthStatus }}</div>
                        </section>
                    </article>
                </div>
            </section>
        </div>
    `
};
