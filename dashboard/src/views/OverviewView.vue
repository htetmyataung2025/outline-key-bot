<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { fetchOverview, triggerHaptic } from '@/api'
import {
  NCard,
  NGrid,
  NGridItem,
  NTag,
  NSpin,
  NButton,
  useMessage,
} from 'naive-ui'
import {
  ServerOutline,
  KeyOutline,
  PeopleOutline,
  ReceiptOutline,
  CashOutline,
  ArrowForwardOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const message = useMessage()

const loading = ref(true)
const overviewData = ref<any>(null)

async function loadData() {
  loading.value = true
  try {
    overviewData.value = await fetchOverview()
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load overview data')
  } finally {
    loading.value = false
  }
}

function goToSlips() {
  triggerHaptic('light')
  router.push('/slips')
}

function goToKeys() {
  triggerHaptic('light')
  router.push('/keys')
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
    <div class="view-header">
      <div>
        <h1 class="page-title">Operational Overview</h1>
        <p class="page-subtitle">Real-time Outline server telemetry and commercial health</p>
      </div>
      <div class="header-actions">
        <NButton type="primary" size="medium" @click="goToSlips">
          <template #icon>
            <ReceiptOutline />
          </template>
          Review Slips
        </NButton>
        <NButton secondary size="medium" @click="goToKeys">
          <template #icon>
            <KeyOutline />
          </template>
          Manage Keys
        </NButton>
      </div>
    </div>

    <NSpin :show="loading">
      <div v-if="overviewData" class="content-body">
        <!-- 1. KPI Metric Cards -->
        <NGrid cols="2 s:2 m:4" :x-gap="16" :y-gap="16" class="metrics-grid">
          <NGridItem>
            <NCard class="stat-card" hoverable>
              <div class="stat-inner">
                <div class="stat-icon-wrap emerald">
                  <KeyOutline class="stat-icon" />
                </div>
                <div class="stat-info">
                  <span class="stat-label">Active Keys</span>
                  <span class="stat-val">{{ overviewData.metrics.total_active_keys }}</span>
                </div>
              </div>
            </NCard>
          </NGridItem>

          <NGridItem>
            <NCard class="stat-card" hoverable>
              <div class="stat-inner">
                <div class="stat-icon-wrap blue">
                  <PeopleOutline class="stat-icon" />
                </div>
                <div class="stat-info">
                  <span class="stat-label">Total Customers</span>
                  <span class="stat-val">{{ overviewData.metrics.total_customers }}</span>
                </div>
              </div>
            </NCard>
          </NGridItem>

          <NGridItem>
            <NCard
              class="stat-card"
              :class="{ 'stat-highlight': overviewData.metrics.pending_slips > 0 }"
              hoverable
              @click="goToSlips"
            >
              <div class="stat-inner">
                <div class="stat-icon-wrap amber">
                  <ReceiptOutline class="stat-icon" />
                </div>
                <div class="stat-info">
                  <span class="stat-label">Pending Slips</span>
                  <div class="val-with-action">
                    <span class="stat-val">{{ overviewData.metrics.pending_slips }}</span>
                    <ArrowForwardOutline class="action-hint" />
                  </div>
                </div>
              </div>
            </NCard>
          </NGridItem>

          <NGridItem>
            <NCard class="stat-card" hoverable>
              <div class="stat-inner">
                <div class="stat-icon-wrap emerald">
                  <CashOutline class="stat-icon" />
                </div>
                <div class="stat-info">
                  <span class="stat-label">Today's Revenue</span>
                  <span class="stat-val">{{ overviewData.metrics.today_revenue_ks.toLocaleString() }} Ks</span>
                  <span class="stat-sub">Month: {{ overviewData.metrics.month_revenue_ks.toLocaleString() }} Ks</span>
                </div>
              </div>
            </NCard>
          </NGridItem>
        </NGrid>

        <!-- 2. Outline Server Health Cards -->
        <h2 class="section-title">Outline VPN Cluster Health</h2>
        <NGrid cols="1 s:2 m:3" :x-gap="16" :y-gap="16">
          <NGridItem v-for="srv in overviewData.servers" :key="srv.id">
            <NCard class="server-card" hoverable>
              <div class="server-header">
                <div class="server-title-wrap">
                  <ServerOutline class="server-icon" />
                  <span class="server-name">{{ srv.name }}</span>
                </div>
                <NTag
                  :type="srv.is_active ? 'success' : 'error'"
                  size="small"
                  round
                  :bordered="false"
                >
                  {{ srv.is_active ? 'ONLINE' : 'OFFLINE' }}
                </NTag>
              </div>

              <div class="server-specs">
                <div class="spec-row">
                  <span class="spec-label">Ping Latency</span>
                  <span
                    class="spec-val"
                    :class="{
                      emerald: srv.latency_ms > 0 && srv.latency_ms < 100,
                      amber: srv.latency_ms >= 100 && srv.latency_ms < 300,
                      red: srv.latency_ms >= 300 || !srv.is_active,
                    }"
                  >
                    {{ srv.is_active ? `${srv.latency_ms} ms` : 'N/A' }}
                  </span>
                </div>

                <div class="spec-row">
                  <span class="spec-label">Keys Hosted</span>
                  <span class="spec-val font-mono">{{ srv.total_keys }} keys</span>
                </div>

                <div class="spec-row">
                  <span class="spec-label">Bandwidth Transferred</span>
                  <span class="spec-val font-mono text-emerald">{{ srv.total_transferred_gb }} GB</span>
                </div>
              </div>
            </NCard>
          </NGridItem>
        </NGrid>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.overview-view {
  padding: 24px;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 24px;
  flex-wrap: wrap;
  gap: 16px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: #f8fafc;
}

.page-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: #94a3b8;
}

.header-actions {
  display: flex;
  gap: 12px;
}

.section-title {
  font-size: 16px;
  font-weight: 600;
  color: #cbd5e1;
  margin: 32px 0 16px 0;
}

.metrics-grid {
  margin-bottom: 8px;
}

.stat-card {
  cursor: default;
}

.stat-inner {
  display: flex;
  align-items: center;
  gap: 16px;
}

.stat-icon-wrap {
  width: 48px;
  height: 48px;
  border-radius: 12px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon-wrap.emerald {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
}

.stat-icon-wrap.blue {
  background: rgba(14, 165, 233, 0.15);
  color: #0ea5e9;
}

.stat-icon-wrap.amber {
  background: rgba(245, 158, 11, 0.15);
  color: #f59e0b;
}

.stat-icon {
  width: 24px;
  height: 24px;
}

.stat-info {
  display: flex;
  flex-direction: column;
}

.stat-label {
  font-size: 12px;
  color: #94a3b8;
  font-weight: 500;
}

.stat-val {
  font-size: 20px;
  font-weight: 700;
  color: #f8fafc;
  font-family: 'JetBrains Mono', monospace;
}

.stat-sub {
  font-size: 11px;
  color: #64748b;
  margin-top: 2px;
}

.val-with-action {
  display: flex;
  align-items: center;
  gap: 8px;
}

.action-hint {
  width: 14px;
  height: 14px;
  color: #f59e0b;
}

.stat-highlight {
  border-color: rgba(245, 158, 11, 0.5) !important;
  cursor: pointer;
}

.server-card {
  border: 1px solid #334155;
}

.server-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}

.server-title-wrap {
  display: flex;
  align-items: center;
  gap: 10px;
}

.server-icon {
  width: 20px;
  height: 20px;
  color: #10b981;
}

.server-name {
  font-weight: 600;
  font-size: 14px;
  color: #f8fafc;
}

.server-specs {
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.spec-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.spec-label {
  color: #94a3b8;
}

.spec-val {
  font-weight: 600;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.text-emerald {
  color: #10b981;
}

.spec-val.emerald {
  color: #10b981;
}

.spec-val.amber {
  color: #f59e0b;
}

.spec-val.red {
  color: #ef4444;
}
</style>
