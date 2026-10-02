<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import {
  fetchPurchases,
  fetchServers,
  triggerHaptic,
  triggerHapticNotification,
} from '@/api'
import { usePagedList } from '@/composables/usePagedList'
import {
  NButton,
  NInput,
  NSelect,
  NSpin,
  NEmpty,
  NPagination,
  NModal,
  NCard,
  NTag,
  useMessage,
} from 'naive-ui'
import { ChevronForwardOutline, CopyOutline } from '@vicons/ionicons5'

const message = useMessage()
const router = useRouter()

interface PurchaseItem {
  order_id: string
  chat_id: string
  timestamp: string
  ts: string
  time_str: string
  plan_name: string
  months: number
  disp_gb: string
  price: number
  price_str: string
  server: string
  server_name: string
  expire_date: string
  vpn_key: string
  kind: 'paid' | 'points'
  source: string
  username: string
  full_name: string
}

const loading = ref(false)
const items = ref<PurchaseItem[]>([])
const summary = ref({
  today_revenue_ks: 0,
  today_count: 0,
  month_revenue_ks: 0,
  month_count: 0,
})

// Server-side filters: window (rolling days), server, search.
const daysWindow = ref<string>('0')
const WINDOW_CHIPS = [
  { label: '24h', value: '1' },
  { label: '7d', value: '7' },
  { label: '30d', value: '30' },
  { label: 'All', value: '0' },
]
const serverFilter = ref<string | null>(null)
const searchQuery = ref('')
const serverOptions = ref<{ label: string; value: string }[]>([])

const {
  page: listPage, pageSize: listPageSize, paged: pagedItems,
  count: listCount, rangeStart: rangeStart, rangeEnd: rangeEnd,
} = usePagedList(items)

let searchTimer: ReturnType<typeof setTimeout> | null = null

async function loadPurchases(opts?: { silent?: boolean }) {
  const silent = opts?.silent ?? false
  if (!silent) loading.value = true
  try {
    const params: { days?: number; server?: string; q?: string } = {}
    const days = parseInt(daysWindow.value, 10)
    if (days > 0) params.days = days
    if (serverFilter.value) params.server = serverFilter.value
    if (searchQuery.value.trim()) params.q = searchQuery.value.trim()
    const data = await fetchPurchases(params)
    items.value = data.items || []
    if (data.summary) summary.value = data.summary
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load purchase history')
  } finally {
    if (!silent) loading.value = false
  }
}

function handleWindowChange() {
  triggerHaptic('light')
  loadPurchases()
}

function handleServerChange() {
  triggerHaptic('light')
  loadPurchases()
}

function handleSearchInput() {
  if (searchTimer) clearTimeout(searchTimer)
  searchTimer = setTimeout(() => loadPurchases(), 400)
}

async function loadServerOptions() {
  try {
    const data = await fetchServers()
    const opts = (data.servers || []).map((s: any) => ({
      label: s.name || `Server ${s.id}`,
      value: String(s.id),
    }))
    opts.push({ label: '⭐ VIP (Manual)', value: 'VIP' })
    serverOptions.value = opts
  } catch {
    // Dropdown stays empty; the list itself still loads.
  }
}

function customerLabel(item: PurchaseItem): string {
  return item.username || item.full_name || ''
}

function openCustomer(item: PurchaseItem) {
  triggerHaptic('light')
  router.push(`/customers/${item.chat_id}`)
}

const showDetail = ref(false)
const detailItem = ref<PurchaseItem | null>(null)

function openDetail(item: PurchaseItem) {
  triggerHaptic('light')
  detailItem.value = item
  showDetail.value = true
}

async function copyKey() {
  const key = detailItem.value?.vpn_key || ''
  if (!key) return
  try {
    await navigator.clipboard.writeText(key)
    triggerHapticNotification('success')
    message.success('Key copied to clipboard')
  } catch {
    message.error('Could not copy the key')
  }
}

onMounted(() => {
  loadPurchases()
  loadServerOptions()
})

defineExpose({ loadData: loadPurchases })
</script>

<template>
  <div class="purchases-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Purchases History</h1>
        <p class="page-subtitle">Live feed of every key purchase — updates automatically as sales come in</p>
      </div>
    </div>

    <!-- Summary cards -->
    <div class="summary-row">
      <div class="summary-card">
        <span class="summary-label">Today Revenue</span>
        <span class="summary-value font-mono">{{ summary.today_revenue_ks.toLocaleString() }} <small>Ks</small></span>
      </div>
      <div class="summary-card">
        <span class="summary-label">Today Purchases</span>
        <span class="summary-value font-mono">{{ summary.today_count }}</span>
      </div>
      <div class="summary-card">
        <span class="summary-label">This Month Revenue</span>
        <span class="summary-value font-mono">{{ summary.month_revenue_ks.toLocaleString() }} <small>Ks</small></span>
      </div>
      <div class="summary-card">
        <span class="summary-label">This Month Purchases</span>
        <span class="summary-value font-mono">{{ summary.month_count }}</span>
      </div>
    </div>

    <!-- Filters -->
    <div class="filter-bar">
      <div class="window-chips">
        <button
          v-for="w in WINDOW_CHIPS"
          :key="w.value"
          type="button"
          class="window-chip"
          :class="{ active: daysWindow === w.value }"
          @click="daysWindow = w.value; handleWindowChange()"
        >
          {{ w.label }}
        </button>
      </div>

      <NSelect
        v-model:value="serverFilter"
        :options="serverOptions"
        placeholder="All servers"
        clearable
        size="small"
        class="server-select"
        @update:value="handleServerChange"
      />

      <NInput
        v-model:value="searchQuery"
        size="small"
        placeholder="Search chat ID / order / plan…"
        clearable
        class="search-input"
        @input="handleSearchInput"
      />
    </div>

    <NSpin :show="loading">
      <div v-if="items.length > 0" class="purchases-table">
        <!-- Column headers (desktop only) -->
        <div class="table-head">
          <span class="cell c-time">Time</span>
          <span class="cell c-customer">Customer</span>
          <span class="cell c-plan">Plan</span>
          <span class="cell c-server">Server</span>
          <span class="cell c-amount">Amount</span>
          <span class="cell c-order">Order</span>
          <span class="cell c-chevron" />
        </div>

        <div v-for="item in pagedItems" :key="item.order_id + item.ts + item.chat_id" class="table-row" @click="openDetail(item)">
          <div class="cell c-time">
            <span class="time-val">{{ item.time_str || '—' }}</span>
          </div>

          <div class="cell c-customer">
            <span class="customer-name">{{ customerLabel(item) || '—' }}</span>
            <span class="customer-chat font-mono">{{ item.chat_id }}</span>
          </div>

          <div class="cell c-plan">
            <span class="plan-name">
              {{ item.plan_name }}
              <NTag v-if="item.kind === 'points'" size="tiny" type="info" :bordered="false" class="kind-tag">Points</NTag>
            </span>
            <span class="plan-sub">
              <template v-if="item.disp_gb">{{ item.disp_gb }} · </template>
              <template v-if="item.months">{{ item.months }} month{{ item.months > 1 ? 's' : '' }}</template>
            </span>
          </div>

          <div class="cell c-server">
            <span class="server-chip">{{ item.server_name || item.server }}</span>
          </div>

          <div class="cell c-amount">
            <span class="amount-val font-mono" :class="{ 'amount-points': item.kind === 'points' }">
              {{ item.kind === 'points' ? '🎁' : '+' }}{{ item.price.toLocaleString() }}
            </span>
            <span class="amount-cur">Ks</span>
          </div>

          <div class="cell c-order">
            <span class="order-id font-mono">{{ item.order_id }}</span>
          </div>

          <div class="cell c-chevron">
            <ChevronForwardOutline class="chevron-icon" />
          </div>
        </div>

        <div v-if="listCount > listPageSize" class="pagination-bar">
          <span class="result-count">Showing {{ rangeStart }}–{{ rangeEnd }} of {{ listCount }}</span>
          <NPagination v-model:page="listPage" :item-count="listCount" :page-size="listPageSize" />
        </div>
      </div>

      <div v-else class="empty-wrap">
        <NEmpty description="No purchases found for this filter" />
      </div>
    </NSpin>

    <!-- Purchase detail modal -->
    <NModal v-model:show="showDetail">
      <NCard
        style="width: 90vw; max-width: 520px; max-height: 85vh; overflow: auto;"
        title="Purchase Detail"
        :bordered="false"
        size="small"
        role="dialog"
        aria-modal="true"
        closable
        @close="showDetail = false"
      >
        <div v-if="detailItem" class="detail-body">
          <div class="detail-row">
            <span class="detail-label">Order</span>
            <span class="detail-value font-mono">{{ detailItem.order_id }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Customer</span>
            <button class="customer-link" @click.stop="openCustomer(detailItem)">
              {{ customerLabel(detailItem) || detailItem.chat_id }}
              <span class="customer-link-id font-mono">· {{ detailItem.chat_id }}</span>
            </button>
          </div>
          <div class="detail-row">
            <span class="detail-label">Plan</span>
            <span class="detail-value">
              {{ detailItem.plan_name }}
              <template v-if="detailItem.disp_gb"> · {{ detailItem.disp_gb }}</template>
              <template v-if="detailItem.months"> · {{ detailItem.months }}m</template>
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Server</span>
            <span class="detail-value">{{ detailItem.server_name || detailItem.server }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Amount</span>
            <span class="detail-value font-mono detail-amount">
              {{ detailItem.kind === 'points' ? '🎁 Points Reward' : detailItem.price_str || (detailItem.price.toLocaleString() + ' Ks') }}
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Time</span>
            <span class="detail-value">{{ detailItem.time_str || detailItem.timestamp }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">Expires</span>
            <span class="detail-value">{{ detailItem.expire_date || '—' }}</span>
          </div>
          <div v-if="detailItem.vpn_key" class="key-block">
            <span class="detail-label">VPN Key</span>
            <div class="key-line">
              <code class="key-text font-mono">{{ detailItem.vpn_key }}</code>
              <NButton size="tiny" secondary @click.stop="copyKey">
                <template #icon><CopyOutline /></template>
                Copy
              </NButton>
            </div>
          </div>
        </div>
      </NCard>
    </NModal>
  </div>
</template>

<style scoped>
.purchases-view {
  padding: 24px;
  container-type: inline-size;
  container-name: purchases;
}

.view-header {
  margin-bottom: 16px;
}

.page-title {
  margin: 0;
  font-size: 22px;
  font-weight: 700;
  color: var(--text-1);
}

.page-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-3);
}

/* ── Summary cards ──────────────────────────────────────────────── */
.summary-row {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 16px;
}

.summary-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 14px 16px;
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.summary-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.summary-value {
  font-size: 20px;
  font-weight: 700;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.summary-value small {
  font-size: 11px;
  font-weight: 600;
  color: var(--text-4);
}

/* ── Filter bar ─────────────────────────────────────────────────── */
.filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}

.window-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  flex-shrink: 0;
}

.window-chip {
  min-height: 34px;
  padding: 0 14px;
  border-radius: 999px;
  border: 1px solid rgba(148, 163, 184, 0.35);
  background: transparent;
  color: var(--text-3);
  font-size: 13px;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background 0.15s;
}

.window-chip.active {
  border-color: var(--accent);
  color: var(--accent);
  background: rgba(16, 185, 129, 0.12);
  font-weight: 600;
}

.server-select {
  width: 180px;
  flex-shrink: 0;
}

.search-input {
  flex: 1;
  min-width: 160px;
}

/* ── Purchases table ────────────────────────────────────────────── */
.purchases-table {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: 130px minmax(130px, 1.1fr) minmax(170px, 1.4fr) 110px 96px 100px 24px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.table-head {
  height: 38px;
  border-bottom: 1px solid var(--border);
  background: var(--surface-2);
}

.table-head .cell {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.5px;
  text-transform: uppercase;
  color: var(--text-4);
}

.table-row {
  min-height: 58px;
  border-bottom: 1px solid var(--border-subtle);
  transition: background 0.12s ease;
  cursor: pointer;
}

.table-row:last-child {
  border-bottom: none;
}

.table-row:hover {
  background: var(--fill-subtle);
}

.cell {
  min-width: 0;
}

/* Time cell */
.time-val {
  font-size: 11.5px;
  color: var(--text-3);
  white-space: nowrap;
}

/* Customer cell */
.c-customer {
  display: flex;
  flex-direction: column;
}

.customer-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.customer-chat {
  font-size: 11px;
  color: var(--text-4);
}

/* Plan cell */
.c-plan {
  display: flex;
  flex-direction: column;
}

.plan-name {
  font-size: 13px;
  font-weight: 500;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.kind-tag {
  margin-left: 4px;
  vertical-align: middle;
}

.plan-sub {
  font-size: 11px;
  color: var(--text-4);
}

/* Server chip */
.server-chip {
  display: inline-block;
  font-size: 11.5px;
  padding: 2px 8px;
  border-radius: 6px;
  background: var(--fill-subtle);
  border: 1px solid var(--border);
  color: var(--text-2);
  max-width: 100%;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Amount cell */
.c-amount {
  display: flex;
  align-items: baseline;
  gap: 3px;
}

.amount-val {
  color: var(--accent);
  font-weight: 700;
  font-size: 13.5px;
}

.amount-points {
  color: var(--text-2);
}

.amount-cur {
  font-size: 11px;
  color: var(--text-4);
}

/* Order cell */
.order-id {
  font-size: 12px;
  color: var(--text-2);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Chevron */
.chevron-icon {
  width: 14px;
  height: 14px;
  color: var(--text-4);
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.empty-wrap {
  padding: 48px 0;
  display: flex;
  justify-content: center;
}

.pagination-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 12px;
  margin-top: 18px;
}

.result-count {
  font-size: 12px;
  color: var(--text-3);
}

/* ── Detail modal ───────────────────────────────────────────────── */
.detail-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.detail-row {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
}

.detail-label {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--text-4);
  flex-shrink: 0;
}

.detail-value {
  font-size: 13px;
  color: var(--text-1);
  text-align: right;
  min-width: 0;
  overflow-wrap: anywhere;
}

.detail-amount {
  color: var(--accent);
  font-weight: 700;
}

.customer-link {
  background: none;
  border: none;
  padding: 0;
  cursor: pointer;
  font-size: 13px;
  color: var(--accent);
  text-decoration: underline;
  text-underline-offset: 3px;
}

.customer-link-id {
  font-size: 11px;
  color: var(--text-4);
}

.key-block {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.key-line {
  display: flex;
  align-items: center;
  gap: 8px;
}

.key-text {
  flex: 1;
  min-width: 0;
  font-size: 11px;
  color: var(--text-2);
  background: var(--fill-subtle);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ── Narrow column / tablet: drop secondary columns ─────────────── */
@container purchases (max-width: 1000px) {
  .table-head,
  .table-row {
    grid-template-columns: 120px minmax(110px, 1fr) minmax(140px, 1.2fr) 96px 24px;
  }

  .c-server,
  .c-order {
    display: none;
  }
}

/* ── Tight column: rows become compact cards ────────────────────── */
@container purchases (max-width: 720px) {
  .table-head {
    display: none;
  }

  .purchases-table {
    background: transparent;
    border: none;
    border-radius: 0;
    display: flex;
    flex-direction: column;
    gap: 10px;
  }

  .table-row {
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "plan amount"
      "customer amount"
      "time server";
    gap: 4px 10px;
    padding: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
  }

  .c-plan { grid-area: plan; }
  .c-amount { grid-area: amount; justify-self: end; align-self: center; }
  .c-customer { grid-area: customer; }
  .c-time { grid-area: time; }
  .c-server { grid-area: server; justify-self: end; }
  .c-chevron { display: none; }
}

/* Real mobile / Telegram Mini App: trim the outer padding. */
@media (max-width: 767px) {
  .purchases-view {
    padding: 12px;
  }

  .summary-row {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

</style>
