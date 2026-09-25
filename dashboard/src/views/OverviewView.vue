<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchOverview, triggerHaptic } from '@/api'
import {
  NTag,
  NSpin,
  NProgress,
  NTooltip,
  useMessage,
} from 'naive-ui'
import {
  ServerOutline,
  KeyOutline,
  PeopleOutline,
  ReceiptOutline,
  CashOutline,
  ArrowForwardOutline,
  PulseOutline,
  FlashOutline,
  RefreshOutline,
  AddOutline,
  GiftOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const message = useMessage()

const loading = ref(true)
const overviewData = ref<any>(null)
const lastRefreshedAt = ref('')

// Computed cluster stats
const totalBandwidthGb = computed(() => {
  if (!overviewData.value?.servers) return '0.0'
  const sum = overviewData.value.servers
    .reduce((acc: number, s: any) => acc + (Number(s.total_transferred_gb) || 0), 0)
  return sum.toLocaleString(undefined, { minimumFractionDigits: 1, maximumFractionDigits: 2 })
})

const activeServersCount = computed(() => {
  if (!overviewData.value?.servers) return 0
  return overviewData.value.servers.filter((s: any) => s.is_active).length
})

const totalServersCount = computed(() => {
  return overviewData.value?.servers?.length || 0
})

const avgPingLatency = computed(() => {
  if (!overviewData.value?.servers) return 0
  const active = overviewData.value.servers.filter((s: any) => s.is_active && s.latency_ms > 0)
  if (!active.length) return 0
  const sum = active.reduce((acc: number, s: any) => acc + s.latency_ms, 0)
  return Math.round(sum / active.length)
})

async function loadData() {
  loading.value = true
  try {
    overviewData.value = await fetchOverview()
    const now = new Date()
    lastRefreshedAt.value = now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load telemetry data')
  } finally {
    loading.value = false
  }
}

function handleManualRefresh() {
  triggerHaptic('light')
  loadData()
}

function goToSlips() {
  triggerHaptic('light')
  router.push('/slips')
}

function goToKeys(serverId?: string | number) {
  triggerHaptic('light')
  if (serverId) {
    router.push({ path: '/keys', query: { server: String(serverId) } })
  } else {
    router.push('/keys')
  }
}

onMounted(() => {
  loadData()
})

defineExpose({
  loadData,
})
</script>

<template>
  <div class="overview-container">
    <!-- Header -->
    <div class="overview-header">
      <div class="header-titles">
        <div class="breadcrumb-tag desktop-only">
          <PulseOutline class="tag-icon" />
          <span>NETWORK OPERATIONS CENTER</span>
        </div>
        <h1 class="view-title">Cluster Overview</h1>
      </div>

      <div class="header-btns">
        <NTooltip trigger="hover">
          <template #trigger>
            <button class="btn-secondary" @click="handleManualRefresh">
              <RefreshOutline class="btn-icon" :class="{ spin: loading }" />
              <span>Sync</span>
            </button>
          </template>
          Last updated: {{ lastRefreshedAt || 'Just now' }}
        </NTooltip>

        <button class="btn-primary" @click="goToKeys()">
          <AddOutline class="btn-icon" />
          <span>New Key</span>
        </button>
      </div>
    </div>

    <NSpin :show="loading">
      <div v-if="overviewData" class="overview-grid">
        <!-- ROW 1: 4 KPI Cards (Desktop 4-col, Mobile 2x2 grid) -->
        <div class="kpi-row">
          <!-- KPI 1: Active Keys -->
          <div class="kpi-card" @click="goToKeys()">
            <div class="kpi-meta">
              <span class="kpi-label">Active Keys</span>
              <KeyOutline class="kpi-icon emerald" />
            </div>
            <div class="kpi-value font-mono">{{ overviewData.metrics.total_active_keys }}</div>
            <div class="kpi-sub">
              <span>All nodes online</span>
              <ArrowForwardOutline class="sub-arrow" />
            </div>
          </div>

          <!-- KPI 2: Customers -->
          <div class="kpi-card" @click="router.push('/customers')">
            <div class="kpi-meta">
              <span class="kpi-label">Customers</span>
              <PeopleOutline class="kpi-icon blue" />
            </div>
            <div class="kpi-value font-mono">{{ overviewData.metrics.total_customers }}</div>
            <div class="kpi-sub">
              <span>User directory</span>
              <ArrowForwardOutline class="sub-arrow" />
            </div>
          </div>

          <!-- KPI 3: Pending Slips -->
          <div
            class="kpi-card"
            :class="{ 'kpi-alert': overviewData.metrics.pending_slips > 0 }"
            @click="goToSlips"
          >
            <div class="kpi-meta">
              <span class="kpi-label">Pending Slips</span>
              <ReceiptOutline class="kpi-icon amber" />
            </div>
            <div
              class="kpi-value font-mono"
              :class="{ 'text-amber': overviewData.metrics.pending_slips > 0 }"
            >
              {{ overviewData.metrics.pending_slips }}
            </div>
            <div class="kpi-sub">
              <span v-if="overviewData.metrics.pending_slips > 0" class="alert-text">
                Needs review
              </span>
              <span v-else class="text-muted">Cleared</span>
              <ArrowForwardOutline class="sub-arrow" />
            </div>
          </div>

          <!-- KPI 4: Today's Revenue -->
          <div class="kpi-card" @click="router.push('/customers')">
            <div class="kpi-meta">
              <span class="kpi-label">Today's Sales</span>
              <CashOutline class="kpi-icon emerald" />
            </div>
            <div class="kpi-value font-mono text-emerald">
              {{ overviewData.metrics.today_revenue_ks.toLocaleString() }}
              <span class="kpi-unit">MMK</span>
            </div>
            <div class="kpi-sub">
              <span>Month: {{ overviewData.metrics.month_revenue_ks.toLocaleString() }} MMK</span>
              <ArrowForwardOutline class="sub-arrow" />
            </div>
          </div>
        </div>

        <!-- ROW 2: Split Layout (Left: Server Cluster Nodes, Right: Quick Panel) -->
        <div class="main-split-layout">
          <!-- Left: Server Cluster Nodes -->
          <div class="cluster-section">
            <div class="section-title-bar">
              <div class="title-left">
                <ServerOutline class="sec-icon" />
                <h2 class="sec-title">Server Cluster Nodes</h2>
                <span class="sec-count">{{ activeServersCount }}/{{ totalServersCount }} Online</span>
              </div>
              <span class="sec-hint desktop-only">Shadowsocks Management API</span>
            </div>

            <!-- Server Node Cards List -->
            <div class="nodes-list">
              <div
                v-for="srv in overviewData.servers"
                :key="srv.id"
                class="node-row-card"
                :class="{ 'offline': !srv.is_active }"
              >
                <!-- Node Header Row -->
                <div class="node-main">
                  <div class="node-identity">
                    <div class="flag-badge">🇸🇬 SG</div>
                    <div>
                      <div class="node-name-text">
                        {{ srv.name }}
                        <span class="node-id-tag">#{{ srv.id }}</span>
                      </div>
                      <span class="node-endpoint-text desktop-only">
                        {{ srv.is_active ? 'Connected & Healthy' : 'Endpoint Not Configured' }}
                      </span>
                    </div>
                  </div>

                  <div class="node-status-tag" :class="srv.is_active ? 'online' : 'offline'">
                    <span class="dot"></span>
                    <span>{{ srv.is_active ? 'ONLINE' : 'OFFLINE' }}</span>
                  </div>
                </div>

                <!-- Node Metrics Grid -->
                <div class="node-metrics-bar">
                  <div class="metric-item">
                    <span class="m-label">Ping</span>
                    <span
                      class="m-val font-mono"
                      :class="{
                        emerald: srv.latency_ms > 0 && srv.latency_ms < 200,
                        amber: srv.latency_ms >= 200 && srv.latency_ms < 400,
                        red: srv.latency_ms >= 400 || !srv.is_active,
                      }"
                    >
                      <FlashOutline class="mini-icon" />
                      {{ srv.is_active ? `${srv.latency_ms} ms` : 'N/A' }}
                    </span>
                  </div>

                  <div class="metric-item">
                    <span class="m-label">Keys</span>
                    <span class="m-val font-mono">{{ srv.total_keys }} keys</span>
                  </div>

                  <div class="metric-item">
                    <span class="m-label">Data</span>
                    <span class="m-val font-mono text-emerald">{{ srv.total_transferred_gb }} GB</span>
                  </div>
                </div>

                <!-- Progress & Action -->
                <div class="node-footer-bar">
                  <div class="progress-wrap">
                    <NProgress
                      type="line"
                      :percentage="Math.min(100, Math.round((srv.total_transferred_gb / 50000) * 100))"
                      :show-indicator="false"
                      status="success"
                      :height="4"
                    />
                  </div>
                  <button
                    class="node-filter-btn"
                    :disabled="!srv.is_active"
                    @click="goToKeys(srv.id)"
                  >
                    <span>View Keys</span>
                    <ArrowForwardOutline class="btn-mini-arrow" />
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Right: Telemetry Summary & Quick Actions -->
          <div class="side-panel">
            <!-- Cluster Status Card -->
            <div class="panel-card">
              <h3 class="panel-heading">Cluster Telemetry</h3>

              <div class="telemetry-items">
                <div class="telemetry-row">
                  <span class="t-label">Network Load</span>
                  <span class="t-val font-mono text-emerald">{{ totalBandwidthGb }} GB</span>
                </div>

                <div class="telemetry-row">
                  <span class="t-label">Average Latency</span>
                  <span class="t-val font-mono">{{ avgPingLatency }} ms</span>
                </div>

                <div class="telemetry-row">
                  <span class="t-label">Active Nodes</span>
                  <span class="t-val font-mono">{{ activeServersCount }} of {{ totalServersCount }}</span>
                </div>

                <div class="telemetry-row">
                  <span class="t-label">Cluster Status</span>
                  <NTag
                    :type="activeServersCount === totalServersCount ? 'success' : 'warning'"
                    size="tiny"
                    round
                    :bordered="false"
                  >
                    {{ activeServersCount === totalServersCount ? 'Optimal' : 'Degraded' }}
                  </NTag>
                </div>
              </div>
            </div>

            <!-- Quick Management Card -->
            <div class="panel-card">
              <h3 class="panel-heading">Quick Actions</h3>

              <div class="quick-actions-list">
                <button class="quick-btn" @click="goToSlips">
                  <div class="quick-btn-left">
                    <ReceiptOutline class="q-icon amber" />
                    <span>Review Pending Slips</span>
                  </div>
                  <span v-if="overviewData.metrics.pending_slips > 0" class="q-badge">
                    {{ overviewData.metrics.pending_slips }}
                  </span>
                  <ArrowForwardOutline v-else class="q-arrow" />
                </button>

                <button class="quick-btn" @click="goToKeys()">
                  <div class="quick-btn-left">
                    <KeyOutline class="q-icon emerald" />
                    <span>Create Outline Key</span>
                  </div>
                  <ArrowForwardOutline class="q-arrow" />
                </button>

                <button class="quick-btn" @click="router.push('/redeems')">
                  <div class="quick-btn-left">
                    <GiftOutline class="q-icon blue" />
                    <span>Generate Vouchers</span>
                  </div>
                  <ArrowForwardOutline class="q-arrow" />
                </button>

                <button class="quick-btn" @click="router.push('/customers')">
                  <div class="quick-btn-left">
                    <PeopleOutline class="q-icon" />
                    <span>Customer Balances</span>
                  </div>
                  <ArrowForwardOutline class="q-arrow" />
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.overview-container {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
}

@media (max-width: 767px) {
  .overview-container {
    padding: 14px 12px 85px 12px;
  }
}

/* Header */
.overview-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-end;
  margin-bottom: 16px;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 12px;
}

@media (max-width: 767px) {
  .overview-header {
    align-items: center;
    margin-bottom: 12px;
    padding-bottom: 10px;
  }
}

.header-titles {
  display: flex;
  flex-direction: column;
}

.breadcrumb-tag {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: #10b981;
  margin-bottom: 2px;
}

.tag-icon {
  width: 13px;
  height: 13px;
}

.view-title {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: -0.3px;
  line-height: 1.2;
}

@media (max-width: 767px) {
  .view-title {
    font-size: 18px;
  }
}

.header-btns {
  display: flex;
  align-items: center;
  gap: 8px;
}

.btn-secondary {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 11px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 7px;
  color: #cbd5e1;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-secondary:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
}

.btn-primary {
  display: flex;
  align-items: center;
  gap: 5px;
  padding: 6px 12px;
  background: #10b981;
  border: 1px solid #10b981;
  border-radius: 7px;
  color: #041f14;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-primary:hover {
  background: #34d399;
  border-color: #34d399;
}

.btn-icon {
  width: 14px;
  height: 14px;
}

.btn-icon.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

/* Overview Grid */
.overview-grid {
  display: flex;
  flex-direction: column;
  gap: 16px;
}

/* 1. KPI Row: Desktop 4-col, Mobile 2x2 grid */
.kpi-row {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 12px;
}

@media (max-width: 900px) {
  .kpi-row {
    grid-template-columns: repeat(2, 1fr);
    gap: 8px;
  }
}

.kpi-card {
  background: #0d131f;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  cursor: pointer;
  transition: all 0.15s ease;
  min-height: 82px;
}

@media (max-width: 767px) {
  .kpi-card {
    padding: 10px 11px;
    min-height: 74px;
  }
}

.kpi-card:hover {
  background: #111827;
  border-color: rgba(255, 255, 255, 0.14);
}

.kpi-alert {
  border-color: rgba(245, 158, 11, 0.4);
  background: rgba(245, 158, 11, 0.03);
}

.kpi-meta {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.kpi-label {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
}

.kpi-icon {
  width: 15px;
  height: 15px;
  color: #64748b;
}

.kpi-icon.emerald { color: #10b981; }
.kpi-icon.blue { color: #0ea5e9; }
.kpi-icon.amber { color: #f59e0b; }

.kpi-value {
  font-size: 21px;
  font-weight: 700;
  color: #f8fafc;
  line-height: 1.1;
  margin: 4px 0 2px 0;
}

@media (max-width: 767px) {
  .kpi-value {
    font-size: 19px;
  }
}

.kpi-unit {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
  margin-left: 2px;
}

.kpi-sub {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 10.5px;
  color: #64748b;
}

.alert-text {
  color: #f59e0b;
  font-weight: 600;
}

.sub-arrow {
  width: 11px;
  height: 11px;
  color: #64748b;
  transition: transform 0.15s ease;
}

.kpi-card:hover .sub-arrow {
  transform: translateX(2px);
  color: #cbd5e1;
}

/* 2. Split Layout: 1fr on mobile, 1fr 320px on desktop */
.main-split-layout {
  display: grid;
  grid-template-columns: 1fr 320px;
  gap: 16px;
  align-items: start;
}

@media (max-width: 900px) {
  .main-split-layout {
    grid-template-columns: 1fr;
  }
}

/* Section Header */
.section-title-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.title-left {
  display: flex;
  align-items: center;
  gap: 7px;
}

.sec-icon {
  width: 16px;
  height: 16px;
  color: #10b981;
}

.sec-title {
  margin: 0;
  font-size: 14.5px;
  font-weight: 700;
  color: #f8fafc;
}

.sec-count {
  font-size: 10.5px;
  font-weight: 600;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 1px 6px;
  border-radius: 6px;
}

.sec-hint {
  font-size: 11px;
  color: #64748b;
}

/* Node Cards List */
.nodes-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.node-row-card {
  background: #0d131f;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  padding: 12px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  transition: all 0.15s ease;
}

@media (max-width: 767px) {
  .node-row-card {
    padding: 10px 12px;
  }
}

.node-row-card:hover {
  background: #101625;
  border-color: rgba(255, 255, 255, 0.12);
}

.node-row-card.offline {
  border-color: rgba(239, 68, 68, 0.2);
  background: rgba(239, 68, 68, 0.02);
}

.node-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.node-identity {
  display: flex;
  align-items: center;
  gap: 8px;
}

.flag-badge {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  font-size: 10px;
  font-weight: 700;
  padding: 2px 5px;
  border-radius: 5px;
  color: #e2e8f0;
}

.node-name-text {
  font-size: 13.5px;
  font-weight: 700;
  color: #f8fafc;
  display: flex;
  align-items: center;
  gap: 6px;
}

.node-id-tag {
  font-size: 10px;
  font-weight: 600;
  color: #64748b;
}

.node-endpoint-text {
  font-size: 10.5px;
  color: #64748b;
}

.node-status-tag {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 9.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 2px 7px;
  border-radius: 10px;
}

.node-status-tag.online {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.node-status-tag.offline {
  background: rgba(239, 68, 68, 0.1);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.node-status-tag .dot {
  width: 4px;
  height: 4px;
  border-radius: 50%;
  background-color: currentColor;
}

/* Node Metrics Bar */
.node-metrics-bar {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 8px;
  background: rgba(0, 0, 0, 0.2);
  border: 1px solid rgba(255, 255, 255, 0.04);
  border-radius: 7px;
  padding: 6px 10px;
}

.metric-item {
  display: flex;
  flex-direction: column;
  gap: 1px;
}

.m-label {
  font-size: 10px;
  color: #64748b;
  font-weight: 500;
}

.m-val {
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
  display: flex;
  align-items: center;
  gap: 3px;
}

.m-val.emerald { color: #10b981; }
.m-val.amber { color: #f59e0b; }
.m-val.red { color: #ef4444; }

.mini-icon {
  width: 11px;
  height: 11px;
}

/* Node Footer */
.node-footer-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
}

.progress-wrap {
  flex: 1;
}

.node-filter-btn {
  display: flex;
  align-items: center;
  gap: 3px;
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: color 0.15s ease;
  padding: 0;
}

.node-filter-btn:hover:not(:disabled) {
  color: #10b981;
}

.node-filter-btn:disabled {
  opacity: 0.3;
  cursor: not-allowed;
}

.btn-mini-arrow {
  width: 10px;
  height: 10px;
}

/* Right Side Panel */
.side-panel {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.panel-card {
  background: #0d131f;
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 10px;
  padding: 14px;
}

.panel-heading {
  margin: 0 0 10px 0;
  font-size: 12.5px;
  font-weight: 700;
  color: #f8fafc;
}

.telemetry-items {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.telemetry-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 11.5px;
}

.t-label {
  color: #94a3b8;
}

.t-val {
  font-weight: 600;
  color: #f8fafc;
}

/* Quick Actions List */
.quick-actions-list {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.quick-btn {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 7px 9px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 7px;
  color: #cbd5e1;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.quick-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #f8fafc;
  border-color: rgba(255, 255, 255, 0.12);
}

.quick-btn-left {
  display: flex;
  align-items: center;
  gap: 7px;
}

.q-icon {
  width: 14px;
  height: 14px;
  color: #94a3b8;
}

.q-icon.amber { color: #f59e0b; }
.q-icon.emerald { color: #10b981; }
.q-icon.blue { color: #0ea5e9; }

.q-badge {
  background: #f59e0b;
  color: #0f172a;
  font-size: 9.5px;
  font-weight: 800;
  padding: 1px 5px;
  border-radius: 8px;
}

.q-arrow {
  width: 11px;
  height: 11px;
  color: #64748b;
}

/* Visibility helpers */
.desktop-only {
  display: flex;
}

@media (max-width: 767px) {
  .desktop-only {
    display: none !important;
  }
}

/* Font & color utilities */
.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.text-emerald {
  color: #10b981 !important;
}

.text-amber {
  color: #f59e0b !important;
}

.text-muted {
  color: #64748b !important;
}
</style>
