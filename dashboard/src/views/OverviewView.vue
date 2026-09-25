<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchOverview, triggerHaptic } from '@/api'
import {
  NGrid,
  NGridItem,
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
  WifiOutline,
  RefreshOutline,
  CheckmarkCircleOutline,
  AlertCircleOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const message = useMessage()

const loading = ref(true)
const overviewData = ref<any>(null)
const lastRefreshedAt = ref('')

// Computed cluster stats
const totalBandwidthGb = computed(() => {
  if (!overviewData.value?.servers) return 0
  return overviewData.value.servers
    .reduce((acc: number, s: any) => acc + (Number(s.total_transferred_gb) || 0), 0)
    .toFixed(2)
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
  <div class="overview-view">
    <!-- View Header -->
    <div class="view-header">
      <div class="header-left">
        <div class="category-tag">
          <PulseOutline class="tag-icon" />
          <span>SYSTEM NOC & CLUSTER TELEMETRY</span>
        </div>
        <h1 class="page-title">Operational Overview</h1>
        <p class="page-subtitle">Real-time Outline server telemetry, key load distribution & commercial health</p>
      </div>

      <div class="header-actions">
        <NTooltip trigger="hover">
          <template #trigger>
            <button class="glass-action-btn" @click="handleManualRefresh">
              <RefreshOutline class="btn-icon" :class="{ spin: loading }" />
              <span>Refresh</span>
            </button>
          </template>
          Last updated: {{ lastRefreshedAt || 'Just now' }}
        </NTooltip>

        <button class="primary-action-btn" @click="goToSlips">
          <ReceiptOutline class="btn-icon" />
          <span>Review Slips</span>
          <span
            v-if="overviewData?.metrics?.pending_slips > 0"
            class="action-badge-pill"
          >
            {{ overviewData.metrics.pending_slips }}
          </span>
        </button>

        <button class="secondary-action-btn" @click="goToKeys()">
          <KeyOutline class="btn-icon" />
          <span>Manage Keys</span>
        </button>
      </div>
    </div>

    <NSpin :show="loading">
      <div v-if="overviewData" class="content-body">
        <!-- 1. Top Cluster Health Status Banner -->
        <div class="cluster-summary-banner">
          <div class="summary-col">
            <span class="summary-label">CLUSTER AVAILABILITY</span>
            <div class="summary-val-row">
              <span class="summary-num font-mono">{{ activeServersCount }}/{{ totalServersCount }}</span>
              <NTag
                :type="activeServersCount === totalServersCount ? 'success' : 'warning'"
                size="tiny"
                round
                :bordered="false"
              >
                {{ Math.round((activeServersCount / (totalServersCount || 1)) * 100) }}% Operational
              </NTag>
            </div>
            <span class="summary-sub">Singapore & VIP Edge Nodes</span>
          </div>

          <div class="summary-divider"></div>

          <div class="summary-col">
            <span class="summary-label">TOTAL NETWORK LOAD</span>
            <div class="summary-val-row">
              <span class="summary-num font-mono text-emerald">{{ totalBandwidthGb }}</span>
              <span class="summary-unit">GB</span>
            </div>
            <span class="summary-sub">Across All Connected Users</span>
          </div>

          <div class="summary-divider"></div>

          <div class="summary-col">
            <span class="summary-label">CLUSTER AVG LATENCY</span>
            <div class="summary-val-row">
              <FlashOutline class="latency-icon" />
              <span class="summary-num font-mono">{{ avgPingLatency }}</span>
              <span class="summary-unit">ms</span>
            </div>
            <span class="summary-sub">Outline API Ping Health</span>
          </div>

          <div class="summary-divider"></div>

          <div class="summary-col">
            <span class="summary-label">COMMERCIAL BALANCE</span>
            <div class="summary-val-row">
              <span class="summary-num font-mono text-amber">
                {{ overviewData.metrics.today_revenue_ks.toLocaleString() }}
              </span>
              <span class="summary-unit">Ks</span>
            </div>
            <span class="summary-sub">Month: {{ overviewData.metrics.month_revenue_ks.toLocaleString() }} Ks</span>
          </div>
        </div>

        <!-- 2. KPI Metric Cards -->
        <NGrid cols="1 s:2 m:4" :x-gap="16" :y-gap="16" class="metrics-grid">
          <!-- Active Keys Card -->
          <NGridItem>
            <div class="stat-card" @click="goToKeys()">
              <div class="card-glow emerald-glow"></div>
              <div class="stat-top">
                <span class="stat-eyebrow">ACTIVE KEYS</span>
                <div class="stat-icon-pill emerald">
                  <KeyOutline class="icon" />
                </div>
              </div>
              <div class="stat-val font-mono">{{ overviewData.metrics.total_active_keys }}</div>
              <div class="stat-bottom">
                <span class="stat-desc">Provisioned across nodes</span>
                <ArrowForwardOutline class="hover-arrow" />
              </div>
            </div>
          </NGridItem>

          <!-- Customers Card -->
          <NGridItem>
            <div class="stat-card" @click="router.push('/customers')">
              <div class="card-glow blue-glow"></div>
              <div class="stat-top">
                <span class="stat-eyebrow">CUSTOMERS</span>
                <div class="stat-icon-pill blue">
                  <PeopleOutline class="icon" />
                </div>
              </div>
              <div class="stat-val font-mono">{{ overviewData.metrics.total_customers }}</div>
              <div class="stat-bottom">
                <span class="stat-desc">Verified Telegram Users</span>
                <ArrowForwardOutline class="hover-arrow" />
              </div>
            </div>
          </NGridItem>

          <!-- Pending Slips Card -->
          <NGridItem>
            <div
              class="stat-card"
              :class="{ 'stat-card-alert': overviewData.metrics.pending_slips > 0 }"
              @click="goToSlips"
            >
              <div class="card-glow amber-glow"></div>
              <div class="stat-top">
                <span class="stat-eyebrow">PAYMENT SLIPS</span>
                <div class="stat-icon-pill amber">
                  <ReceiptOutline class="icon" />
                </div>
              </div>
              <div class="stat-val font-mono" :class="{ 'text-amber': overviewData.metrics.pending_slips > 0 }">
                {{ overviewData.metrics.pending_slips }}
              </div>
              <div class="stat-bottom">
                <span v-if="overviewData.metrics.pending_slips > 0" class="stat-alert-tag">
                  ⚠️ Action Required
                </span>
                <span v-else class="stat-desc text-emerald">
                  <CheckmarkCircleOutline class="mini-icon" /> All clear
                </span>
                <ArrowForwardOutline class="hover-arrow" />
              </div>
            </div>
          </NGridItem>

          <!-- Revenue Card -->
          <NGridItem>
            <div class="stat-card" @click="router.push('/customers')">
              <div class="card-glow emerald-glow"></div>
              <div class="stat-top">
                <span class="stat-eyebrow">TODAY'S SALES</span>
                <div class="stat-icon-pill emerald">
                  <CashOutline class="icon" />
                </div>
              </div>
              <div class="stat-val font-mono text-emerald">
                {{ overviewData.metrics.today_revenue_ks.toLocaleString() }} <span class="val-currency">Ks</span>
              </div>
              <div class="stat-bottom">
                <span class="stat-desc">Month: {{ overviewData.metrics.month_revenue_ks.toLocaleString() }} Ks</span>
                <ArrowForwardOutline class="hover-arrow" />
              </div>
            </div>
          </NGridItem>
        </NGrid>

        <!-- 3. Outline VPN Cluster Nodes Section -->
        <div class="section-header">
          <div class="section-title-wrap">
            <ServerOutline class="section-icon" />
            <h2 class="section-title">Outline VPN Cluster Nodes</h2>
            <span class="section-badge">3 Nodes Managed</span>
          </div>
          <span class="section-caption">Real-time health, ping response & key distribution per server</span>
        </div>

        <!-- 3-Column Node Cards Grid -->
        <NGrid cols="1 s:1 m:3" :x-gap="16" :y-gap="16" class="servers-grid">
          <NGridItem v-for="srv in overviewData.servers" :key="srv.id">
            <div class="node-card" :class="{ 'node-offline': !srv.is_active }">
              <!-- Node Header -->
              <div class="node-header">
                <div class="node-name-wrap">
                  <div class="flag-pill">🇸🇬 SG</div>
                  <div>
                    <h3 class="node-title">{{ srv.name }}</h3>
                    <span class="node-sub">Node #{{ srv.id }} &bull; Shadowsocks</span>
                  </div>
                </div>

                <div class="node-status-pill" :class="srv.is_active ? 'online' : 'offline'">
                  <span class="node-pulse-dot"></span>
                  <span>{{ srv.is_active ? 'ONLINE' : 'OFFLINE' }}</span>
                </div>
              </div>

              <!-- Node Telemetry Metrics Body -->
              <div class="node-body">
                <!-- Ping Latency Stat -->
                <div class="metric-row">
                  <div class="metric-label-group">
                    <WifiOutline class="metric-icon" />
                    <span>Ping Response</span>
                  </div>
                  <div
                    class="latency-badge"
                    :class="{
                      fast: srv.latency_ms > 0 && srv.latency_ms < 150,
                      medium: srv.latency_ms >= 150 && srv.latency_ms < 350,
                      slow: srv.latency_ms >= 350 || !srv.is_active,
                    }"
                  >
                    <FlashOutline class="mini-flash" />
                    <span class="font-mono">{{ srv.is_active ? `${srv.latency_ms} ms` : 'Offline' }}</span>
                  </div>
                </div>

                <!-- Bandwidth Transferred -->
                <div class="node-bandwidth-box">
                  <div class="bw-header">
                    <span class="bw-label">Data Transferred</span>
                    <span class="bw-val font-mono text-emerald">{{ srv.total_transferred_gb }} GB</span>
                  </div>
                  <NProgress
                    type="line"
                    :percentage="Math.min(100, Math.round((srv.total_transferred_gb / 50000) * 100))"
                    :show-indicator="false"
                    status="success"
                    class="node-progress"
                  />
                </div>

                <!-- Keys Hosted -->
                <div class="metric-row">
                  <div class="metric-label-group">
                    <KeyOutline class="metric-icon" />
                    <span>Active Keys Hosted</span>
                  </div>
                  <span class="keys-count-pill font-mono">
                    {{ srv.total_keys }} Keys
                  </span>
                </div>

                <!-- Error indicator if any -->
                <div v-if="!srv.is_active" class="node-error-banner">
                  <AlertCircleOutline class="error-icon" />
                  <span>{{ srv.error || 'Server endpoint unreachable' }}</span>
                </div>
              </div>

              <!-- Node Card Footer -->
              <div class="node-footer">
                <button
                  class="node-action-btn"
                  :disabled="!srv.is_active"
                  @click="goToKeys(srv.id)"
                >
                  <span>Filter Keys on this Node</span>
                  <ArrowForwardOutline class="btn-arrow" />
                </button>
              </div>
            </div>
          </NGridItem>
        </NGrid>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.overview-view {
  padding: 24px;
  max-width: 1360px;
  margin: 0 auto;
}

/* Header */
.view-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 16px;
}

.header-left {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.category-tag {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.8px;
  color: #10b981;
}

.tag-icon {
  width: 14px;
  height: 14px;
}

.page-title {
  margin: 0;
  font-size: 24px;
  font-weight: 800;
  color: #f8fafc;
  letter-spacing: -0.4px;
}

.page-subtitle {
  margin: 0;
  font-size: 13px;
  color: #94a3b8;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Buttons */
.glass-action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  color: #cbd5e1;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.glass-action-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
  border-color: rgba(255, 255, 255, 0.15);
}

.primary-action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 16px;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border: 1px solid rgba(16, 185, 129, 0.4);
  border-radius: 9px;
  color: #ffffff;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  box-shadow: 0 0 16px rgba(16, 185, 129, 0.25);
  transition: all 0.2s ease;
}

.primary-action-btn:hover {
  filter: brightness(1.1);
  box-shadow: 0 0 20px rgba(16, 185, 129, 0.4);
}

.action-badge-pill {
  background: #f59e0b;
  color: #0f172a;
  font-size: 11px;
  font-weight: 800;
  padding: 1px 6px;
  border-radius: 10px;
}

.secondary-action-btn {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  background: rgba(30, 41, 59, 0.6);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 9px;
  color: #cbd5e1;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.secondary-action-btn:hover {
  background: rgba(51, 65, 85, 0.6);
  color: #f8fafc;
}

.btn-icon {
  width: 16px;
  height: 16px;
}

.btn-icon.spin {
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}

/* 1. Cluster Summary Banner */
.cluster-summary-banner {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
  background: linear-gradient(135deg, rgba(14, 21, 38, 0.8) 0%, rgba(13, 19, 34, 0.6) 100%);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 18px 24px;
  margin-bottom: 24px;
  box-shadow: 0 8px 24px rgba(0, 0, 0, 0.25);
  position: relative;
  overflow: hidden;
}

.cluster-summary-banner::before {
  content: '';
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  height: 2px;
  background: linear-gradient(90deg, #10b981 0%, #06b6d4 50%, #8b5cf6 100%);
  opacity: 0.8;
}

@media (max-width: 900px) {
  .cluster-summary-banner {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 520px) {
  .cluster-summary-banner {
    grid-template-columns: 1fr;
  }
}

.summary-col {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.summary-label {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: #64748b;
}

.summary-val-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.summary-num {
  font-size: 22px;
  font-weight: 800;
  color: #f8fafc;
}

.summary-unit {
  font-size: 12px;
  font-weight: 600;
  color: #94a3b8;
}

.summary-sub {
  font-size: 11.5px;
  color: #94a3b8;
}

.summary-divider {
  display: none;
}

.latency-icon {
  width: 18px;
  height: 18px;
  color: #f59e0b;
}

/* 2. KPI Stat Cards */
.metrics-grid {
  margin-bottom: 32px;
}

.stat-card {
  position: relative;
  background: rgba(14, 21, 38, 0.7);
  border: 1px solid rgba(255, 255, 255, 0.07);
  border-radius: 14px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  gap: 12px;
  cursor: pointer;
  overflow: hidden;
  transition: all 0.22s ease;
}

.stat-card:hover {
  transform: translateY(-2px);
  border-color: rgba(255, 255, 255, 0.16);
  background: rgba(18, 27, 48, 0.85);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.3);
}

.stat-card:hover .hover-arrow {
  transform: translateX(4px);
  color: #f8fafc;
}

.stat-card-alert {
  border-color: rgba(245, 158, 11, 0.4);
  background: rgba(245, 158, 11, 0.05);
}

.card-glow {
  position: absolute;
  top: -20px;
  right: -20px;
  width: 90px;
  height: 90px;
  border-radius: 50%;
  pointer-events: none;
  filter: blur(28px);
  opacity: 0.15;
}

.emerald-glow { background: #10b981; }
.blue-glow { background: #0ea5e9; }
.amber-glow { background: #f59e0b; }

.stat-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.stat-eyebrow {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.6px;
  color: #64748b;
}

.stat-icon-pill {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon-pill.emerald {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.stat-icon-pill.blue {
  background: rgba(14, 165, 233, 0.15);
  color: #0ea5e9;
}

.stat-icon-pill.amber {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.stat-icon-pill .icon {
  width: 18px;
  height: 18px;
}

.stat-val {
  font-size: 30px;
  font-weight: 800;
  color: #f8fafc;
  line-height: 1.1;
  letter-spacing: -0.5px;
}

.val-currency {
  font-size: 16px;
  font-weight: 600;
  color: #94a3b8;
}

.stat-bottom {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12px;
  color: #64748b;
  border-top: 1px solid rgba(255, 255, 255, 0.04);
  padding-top: 10px;
}

.stat-desc {
  display: flex;
  align-items: center;
  gap: 4px;
}

.mini-icon {
  width: 14px;
  height: 14px;
}

.stat-alert-tag {
  color: #f59e0b;
  font-weight: 700;
}

.hover-arrow {
  width: 14px;
  height: 14px;
  color: #64748b;
  transition: transform 0.2s ease, color 0.2s ease;
}

/* 3. Section Header */
.section-header {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 18px;
}

.section-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.section-icon {
  width: 20px;
  height: 20px;
  color: #10b981;
}

.section-title {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #f8fafc;
}

.section-badge {
  font-size: 11px;
  font-weight: 600;
  color: #94a3b8;
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 12px;
}

.section-caption {
  font-size: 12.5px;
  color: #64748b;
}

/* 3-Column Node Cards */
.servers-grid {
  margin-bottom: 24px;
}

.node-card {
  background: rgba(14, 21, 38, 0.85);
  border: 1px solid rgba(255, 255, 255, 0.08);
  border-radius: 14px;
  padding: 18px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 16px;
  position: relative;
  transition: all 0.22s ease;
}

.node-card:hover {
  border-color: rgba(16, 185, 129, 0.35);
  box-shadow: 0 10px 24px rgba(0, 0, 0, 0.35);
  transform: translateY(-2px);
}

.node-offline {
  border-color: rgba(239, 68, 68, 0.3);
  background: rgba(239, 68, 68, 0.03);
}

.node-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  border-bottom: 1px solid rgba(255, 255, 255, 0.06);
  padding-bottom: 14px;
}

.node-name-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.flag-pill {
  background: rgba(255, 255, 255, 0.05);
  border: 1px solid rgba(255, 255, 255, 0.1);
  font-size: 11px;
  font-weight: 700;
  padding: 4px 7px;
  border-radius: 6px;
  color: #e2e8f0;
}

.node-title {
  margin: 0;
  font-size: 14.5px;
  font-weight: 700;
  color: #f8fafc;
}

.node-sub {
  font-size: 11px;
  color: #64748b;
}

.node-status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.5px;
  padding: 4px 8px;
  border-radius: 14px;
}

.node-status-pill.online {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.25);
}

.node-status-pill.offline {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.node-pulse-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background-color: currentColor;
}

.online .node-pulse-dot {
  box-shadow: 0 0 6px #10b981;
}

/* Node Body */
.node-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.metric-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 12.5px;
}

.metric-label-group {
  display: flex;
  align-items: center;
  gap: 6px;
  color: #94a3b8;
}

.metric-icon {
  width: 15px;
  height: 15px;
  color: #64748b;
}

.latency-badge {
  display: flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 700;
  padding: 2px 7px;
  border-radius: 6px;
}

.latency-badge.fast {
  background: rgba(16, 185, 129, 0.12);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.latency-badge.medium {
  background: rgba(245, 158, 11, 0.12);
  color: #f59e0b;
  border: 1px solid rgba(245, 158, 11, 0.2);
}

.latency-badge.slow {
  background: rgba(239, 68, 68, 0.12);
  color: #f87171;
  border: 1px solid rgba(239, 68, 68, 0.2);
}

.mini-flash {
  width: 12px;
  height: 12px;
}

.node-bandwidth-box {
  background: rgba(0, 0, 0, 0.25);
  border: 1px solid rgba(255, 255, 255, 0.05);
  border-radius: 9px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.bw-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 12px;
}

.bw-label {
  color: #94a3b8;
}

.bw-val {
  font-weight: 700;
}

.node-progress :deep(.n-progress-graph-line-fill) {
  background: linear-gradient(90deg, #10b981 0%, #06b6d4 100%) !important;
}

.keys-count-pill {
  background: rgba(255, 255, 255, 0.04);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #e2e8f0;
}

.node-error-banner {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(239, 68, 68, 0.1);
  border: 1px solid rgba(239, 68, 68, 0.2);
  padding: 6px 10px;
  border-radius: 6px;
  font-size: 11px;
  color: #fca5a5;
}

.error-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

/* Node Footer */
.node-footer {
  border-top: 1px solid rgba(255, 255, 255, 0.06);
  padding-top: 12px;
}

.node-action-btn {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}

.node-action-btn:hover:not(:disabled) {
  background: rgba(16, 185, 129, 0.1);
  color: #10b981;
  border-color: rgba(16, 185, 129, 0.25);
}

.node-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.btn-arrow {
  width: 13px;
  height: 13px;
}

/* Utility classes */
.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.text-emerald {
  color: #10b981 !important;
}

.text-amber {
  color: #f59e0b !important;
}
</style>
