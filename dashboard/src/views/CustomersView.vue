<script setup lang="ts">
import { ref, onMounted, computed, watch } from 'vue'
import { useRouter } from 'vue-router'
import { fetchCustomers, adjustBalance, triggerHaptic, triggerHapticNotification } from '@/api'
import { avatarInitial, avatarGradient, displayName } from '@/composables/avatar'
import {
  NCard,
  NInput,
  NSelect,
  NButton,
  NModal,
  NForm,
  NFormItem,
  NInputNumber,
  NRadioGroup,
  NRadioButton,
  NSpin,
  NPagination,
  NEmpty,
  useMessage,
} from 'naive-ui'
import {
  SearchOutline,
  CashOutline,
  ChevronForwardOutline,
  KeyOutline,
  PeopleOutline,
  CloseOutline,
} from '@vicons/ionicons5'

const router = useRouter()
const message = useMessage()

const loading = ref(false)
const customers = ref<any[]>([])
const search = ref('')
const page = ref(1)
const pageSize = ref(10)

// ── Filters & sort (all client-side over the fully-loaded list) ──────
type BalanceFilter = 'all' | 'positive' | 'zero'
type KeysFilter = 'all' | 'has' | 'none'
type ActivityFilter = 'all' | '7d' | '30d' | 'inactive' | 'never'
type SortKey =
  | 'balance_desc'
  | 'balance_asc'
  | 'active_recent'
  | 'keys_desc'
  | 'first_new'
  | 'first_old'
  | 'name_asc'

const balanceFilter = ref<BalanceFilter>('all')
const keysFilter = ref<KeysFilter>('all')
const activityFilter = ref<ActivityFilter>('all')
const sortBy = ref<SortKey>('balance_desc')

const balanceOptions = [
  { label: 'All Balances', value: 'all' },
  { label: 'Has Balance (>0)', value: 'positive' },
  { label: 'Zero Balance', value: 'zero' },
]
const keysOptions = [
  { label: 'All Keys', value: 'all' },
  { label: 'Has Keys (≥1)', value: 'has' },
  { label: 'No Keys', value: 'none' },
]
const activityOptions = [
  { label: 'All Activity', value: 'all' },
  { label: 'Active ≤ 7 days', value: '7d' },
  { label: 'Active ≤ 30 days', value: '30d' },
  { label: 'Inactive > 30 days', value: 'inactive' },
  { label: 'Never Active', value: 'never' },
]
const sortOptions = [
  { label: 'Balance: High → Low', value: 'balance_desc' },
  { label: 'Balance: Low → High', value: 'balance_asc' },
  { label: 'Recently Active', value: 'active_recent' },
  { label: 'Most Keys', value: 'keys_desc' },
  { label: 'Newest Customers', value: 'first_new' },
  { label: 'Oldest Customers', value: 'first_old' },
  { label: 'Name A–Z', value: 'name_asc' },
]

// Balance adjust modal
const showAdjustModal = ref(false)
const adjustLoading = ref(false)
const selectedCustomer = ref<any>(null)
const adjustForm = ref({
  adjustment_type: 'TOPUP' as 'TOPUP' | 'DEDUCT',
  amount_ks: 5000,
  reason: '',
})

const isDeduct = computed(() => adjustForm.value.adjustment_type === 'DEDUCT')
const currentBalance = computed(() => Number(selectedCustomer.value?.wallet_balance || 0))
// Deduct can never exceed the wallet; Top-Up is uncapped.
const amountMax = computed(() => (isDeduct.value ? currentBalance.value : undefined))
const deductExceeds = computed(
  () => isDeduct.value && Number(adjustForm.value.amount_ks || 0) > currentBalance.value,
)


async function loadCustomers(opts?: { silent?: boolean }) {
  const silent = opts?.silent ?? false
  if (!silent) loading.value = true
  try {
    const res = await fetchCustomers()
    customers.value = res.customers || []
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load customers')
  } finally {
    if (!silent) loading.value = false
  }
}

// Whole-day age of a "last_seen"/"first_seen" timestamp; null when absent/unparseable.
function daysSince(value?: string): number | null {
  if (!value) return null
  const dt = new Date(String(value).replace(' ', 'T'))
  if (isNaN(dt.getTime())) return null
  return Math.floor((Date.now() - dt.getTime()) / 86400000)
}

// Epoch ms for sorting; NaN when absent so those rows sink to the bottom.
function toTs(value?: string): number {
  if (!value) return NaN
  const t = new Date(String(value).replace(' ', 'T')).getTime()
  return isNaN(t) ? NaN : t
}

// Newest-first date sort that always parks missing dates last.
function byDateDesc(a?: string, b?: string): number {
  const ta = toTs(a)
  const tb = toTs(b)
  if (isNaN(ta) && isNaN(tb)) return 0
  if (isNaN(ta)) return 1
  if (isNaN(tb)) return -1
  return tb - ta
}

const filteredCustomers = computed(() => {
  const q = search.value.trim().toLowerCase()

  const list = customers.value.filter((c) => {
    if (q) {
      const hit =
        String(c.chat_id).toLowerCase().includes(q) ||
        String(c.full_name || '').toLowerCase().includes(q) ||
        String(c.username || '').toLowerCase().includes(q)
      if (!hit) return false
    }

    const bal = Number(c.wallet_balance || 0)
    if (balanceFilter.value === 'positive' && bal <= 0) return false
    if (balanceFilter.value === 'zero' && bal > 0) return false

    const keys = Number(c.keys_count || 0)
    if (keysFilter.value === 'has' && keys < 1) return false
    if (keysFilter.value === 'none' && keys >= 1) return false

    if (activityFilter.value !== 'all') {
      const d = daysSince(c.last_seen)
      if (activityFilter.value === 'never' && d !== null) return false
      if (activityFilter.value === '7d' && (d === null || d > 7)) return false
      if (activityFilter.value === '30d' && (d === null || d > 30)) return false
      if (activityFilter.value === 'inactive' && (d === null || d <= 30)) return false
    }

    return true
  })

  const arr = [...list]
  switch (sortBy.value) {
    case 'balance_asc':
      arr.sort((a, b) => (a.wallet_balance || 0) - (b.wallet_balance || 0))
      break
    case 'keys_desc':
      arr.sort((a, b) => (b.keys_count || 0) - (a.keys_count || 0))
      break
    case 'active_recent':
      arr.sort((a, b) => byDateDesc(a.last_seen, b.last_seen))
      break
    case 'first_new':
      arr.sort((a, b) => byDateDesc(a.first_seen, b.first_seen))
      break
    case 'first_old':
      arr.sort((a, b) => -byDateDesc(a.first_seen, b.first_seen))
      break
    case 'name_asc':
      arr.sort((a, b) =>
        displayName(a.full_name, a.username, a.chat_id).localeCompare(
          displayName(b.full_name, b.username, b.chat_id),
        ),
      )
      break
    case 'balance_desc':
    default:
      // Highest balance first so the accounts that matter surface at the top.
      arr.sort((a, b) => (b.wallet_balance || 0) - (a.wallet_balance || 0))
  }
  return arr
})

const hasActiveFilters = computed(
  () =>
    !!search.value.trim() ||
    balanceFilter.value !== 'all' ||
    keysFilter.value !== 'all' ||
    activityFilter.value !== 'all',
)

function clearFilters() {
  triggerHaptic('light')
  search.value = ''
  balanceFilter.value = 'all'
  keysFilter.value = 'all'
  activityFilter.value = 'all'
}

const filteredCount = computed(() => filteredCustomers.value.length)
const totalBalance = computed(() =>
  customers.value.reduce((sum, c) => sum + (c.wallet_balance || 0), 0),
)

const pagedCustomers = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredCustomers.value.slice(start, start + pageSize.value)
})

const rangeStart = computed(() => (filteredCount.value === 0 ? 0 : (page.value - 1) * pageSize.value + 1))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, filteredCount.value))

watch([search, balanceFilter, keysFilter, activityFilter, sortBy, pageSize], () => {
  page.value = 1
})

function lastActive(value?: string): string {
  if (!value) return '—'
  const dt = new Date(String(value).replace(' ', 'T'))
  if (isNaN(dt.getTime())) return value
  return dt.toLocaleDateString('en-GB', { day: '2-digit', month: 'short', year: 'numeric' })
}

function goToDetail(chatId: string | number) {
  triggerHaptic('light')
  router.push(`/customers/${chatId}`)
}

function openAdjustModal(customer: any) {
  triggerHaptic('light')
  selectedCustomer.value = customer
  adjustForm.value.adjustment_type = 'TOPUP'
  adjustForm.value.amount_ks = 5000
  adjustForm.value.reason = ''
  showAdjustModal.value = true
}

async function handleAdjustBalance() {
  if (!selectedCustomer.value) return
  adjustLoading.value = true
  try {
    const res = await adjustBalance(selectedCustomer.value.chat_id, {
      adjustment_type: adjustForm.value.adjustment_type,
      amount_ks: adjustForm.value.amount_ks,
      reason: adjustForm.value.reason || undefined,
    })
    if (res.success) {
      triggerHapticNotification('success')
      message.success(
        `Updated balance for ${selectedCustomer.value.chat_id}: ${res.new_balance.toLocaleString()} Ks`,
      )
      showAdjustModal.value = false
      await loadCustomers()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to adjust balance')
  } finally {
    adjustLoading.value = false
  }
}

onMounted(() => {
  loadCustomers()
})

defineExpose({ loadData: loadCustomers })
</script>

<template>
  <div class="customers-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Customer Wallets</h1>
        <p class="page-subtitle">Inspect user balances, activity, and perform administrative adjustments</p>
      </div>
    </div>

    <!-- Filters + summary -->
    <NCard class="filter-card">
      <div class="filters-row">
        <NInput
          v-model:value="search"
          placeholder="Search by Chat ID, name, or @username..."
          clearable
          class="search-input"
        >
          <template #prefix>
            <SearchOutline />
          </template>
        </NInput>

        <NSelect
          v-model:value="balanceFilter"
          :options="balanceOptions"
          class="filter-select"
        />
        <NSelect
          v-model:value="keysFilter"
          :options="keysOptions"
          class="filter-select"
        />
        <NSelect
          v-model:value="activityFilter"
          :options="activityOptions"
          class="filter-select"
        />
        <NSelect
          v-model:value="sortBy"
          :options="sortOptions"
          class="filter-select sort-select"
        />
      </div>

      <div class="filter-summary">
        <span><PeopleOutline class="sum-icon" /> {{ customers.length }} customers</span>
        <span class="sum-accent">{{ totalBalance.toLocaleString() }} MMK total balance</span>
        <span v-if="filteredCount !== customers.length" class="summary-muted">
          {{ filteredCount }} match filters
        </span>
        <NButton
          v-if="hasActiveFilters"
          class="clear-btn"
          size="tiny"
          quaternary
          @click="clearFilters"
        >
          <template #icon><CloseOutline /></template>
          Clear filters
        </NButton>
      </div>
    </NCard>

    <NSpin :show="loading">
      <div v-if="filteredCount > 0" class="table-wrap">
        <div class="cust-table">
          <!-- Column headers (desktop) -->
          <div class="table-head">
            <span class="cell c-customer">Customer</span>
            <span class="cell c-id">User ID</span>
            <span class="cell c-balance">Wallet Balance</span>
            <span class="cell c-keys">Keys</span>
            <span class="cell c-seen">Last Active</span>
            <span class="cell c-actions">Actions</span>
          </div>

          <div class="table-scroll">
            <div v-for="c in pagedCustomers" :key="c.chat_id" class="table-row" @click="goToDetail(c.chat_id)">
              <div class="cell c-customer">
                <span class="avatar" :style="{ background: avatarGradient(c.chat_id) }">
                  {{ avatarInitial(c.full_name || c.username, c.chat_id) }}
                </span>
                <div class="cust-identity">
                  <span class="cust-name">{{ displayName(c.full_name, c.username, c.chat_id) }}</span>
                  <span v-if="c.username" class="cust-username">@{{ c.username }}</span>
                </div>
              </div>

              <div class="cell c-id">
                <span class="id-chip font-mono">{{ c.chat_id }}</span>
              </div>

              <div class="cell c-balance">
                <span class="balance-val font-mono">{{ (c.wallet_balance || 0).toLocaleString() }}</span>
                <span class="balance-cur">MMK</span>
              </div>

              <div class="cell c-keys">
                <span class="keys-chip">
                  <KeyOutline class="keys-icon" />{{ c.keys_count || 0 }}
                </span>
              </div>

              <div class="cell c-seen">{{ lastActive(c.last_seen) }}</div>

              <div class="cell c-actions" @click.stop>
                <NButton size="small" type="primary" secondary @click="openAdjustModal(c)">
                  <template #icon><CashOutline /></template>
                  <span class="btn-text">Adjust</span>
                </NButton>
                <NButton size="small" tertiary class="view-btn" @click="goToDetail(c.chat_id)">
                  <template #icon><ChevronForwardOutline /></template>
                </NButton>
              </div>
            </div>
          </div>
        </div>
      </div>

      <div v-else class="empty-wrap">
        <NEmpty description="No customers match the current filters" />
      </div>
    </NSpin>

    <div v-if="filteredCount > 0" class="pagination-bar">
      <span class="result-count">Showing {{ rangeStart }}–{{ rangeEnd }} of {{ filteredCount }}</span>
      <NPagination
        v-model:page="page"
        v-model:page-size="pageSize"
        :item-count="filteredCount"
        :page-sizes="[10, 20, 50]"
        show-size-picker
      />
    </div>

    <!-- Balance Adjustment Modal -->
    <NModal
      v-model:show="showAdjustModal"
      preset="card"
      title="Adjust Customer Wallet Balance"
      style="max-width: 440px;"
    >
      <div v-if="selectedCustomer" class="modal-target">
        <span class="modal-target-label">Target: </span>
        <span class="font-mono modal-target-id">{{ selectedCustomer.chat_id }}</span>
        <span v-if="selectedCustomer.full_name" class="modal-target-name">
          ({{ selectedCustomer.full_name }})
        </span>
        <br />
        <span class="modal-target-label">Current Balance: </span>
        <span class="font-mono text-emerald modal-target-bal">
          {{ (selectedCustomer.wallet_balance || 0).toLocaleString() }} Ks
        </span>
      </div>

      <NForm :model="adjustForm" label-placement="left" label-width="120">
        <NFormItem label="Action">
          <NRadioGroup v-model:value="adjustForm.adjustment_type">
            <NRadioButton value="TOPUP">Top-Up (+)</NRadioButton>
            <NRadioButton value="DEDUCT">Deduct (-)</NRadioButton>
          </NRadioGroup>
        </NFormItem>
        <NFormItem label="Amount (Ks)">
          <NInputNumber v-model:value="adjustForm.amount_ks" :step="1000" :min="100" :max="amountMax" />
        </NFormItem>
        <p v-if="deductExceeds" class="deduct-warning">
          ⚠️ လက်ကျန်ငွေ ({{ currentBalance.toLocaleString() }} Ks) ထက် ပို၍ နှုတ်ယူ၍ မရပါ။
        </p>
        <NFormItem label="Reason">
          <NInput v-model:value="adjustForm.reason" placeholder="e.g. Compensation bonus" />
        </NFormItem>
        <div class="modal-actions">
          <NButton @click="showAdjustModal = false">Cancel</NButton>
          <NButton type="primary" :loading="adjustLoading" :disabled="deductExceeds" @click="handleAdjustBalance">
            Confirm Adjustment
          </NButton>
        </div>
      </NForm>
    </NModal>
  </div>
</template>

<style scoped>
.customers-view {
  padding: 24px;
  container-type: inline-size;
  container-name: cust;
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

.filter-card {
  margin-bottom: 20px;
  background: var(--surface-2);
}

.filters-row {
  display: flex;
  gap: 16px;
  flex-wrap: wrap;
}

.search-input {
  flex: 2;
  min-width: 220px;
}

.filter-select {
  flex: 1;
  min-width: 150px;
}

.sort-select {
  min-width: 175px;
}

.clear-btn {
  margin-left: auto;
  color: var(--text-3);
}

.filter-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-3);
  align-items: center;
}

.filter-summary span {
  display: inline-flex;
  align-items: center;
  gap: 5px;
}

.sum-icon {
  width: 14px;
  height: 14px;
}

.sum-accent {
  color: var(--accent);
  font-weight: 600;
}

.summary-muted {
  color: var(--text-4);
}
/* ── Table shell ────────────────────────────────────────────────── */
.table-wrap {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: minmax(180px, 2fr) 150px 150px 70px 130px 130px;
  align-items: center;
  gap: 12px;
  padding: 0 16px;
}

.table-head {
  height: 40px;
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

/* Fixed-height scroll region: a full page never pushes the layout, and
   overflowing rows scroll inside the card with a sticky header above. */
.table-scroll {
  max-height: 560px;
  overflow-y: auto;
}

.table-row {
  min-height: 62px;
  border-bottom: 1px solid var(--border-subtle);
  cursor: pointer;
  transition: background 0.12s ease;
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
/* Customer cell */
.c-customer {
  display: flex;
  align-items: center;
  gap: 12px;
}

.avatar {
  width: 38px;
  height: 38px;
  flex-shrink: 0;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 2px rgba(0, 0, 0, 0.3);
}

.cust-identity {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.cust-name {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.cust-username {
  font-size: 11.5px;
  color: var(--text-4);
}

/* User ID cell */
.id-chip {
  font-size: 12.5px;
  color: var(--text-2);
  padding: 3px 9px;
  border-radius: 6px;
  background: var(--fill-subtle);
  border: 1px solid var(--border);
}

/* Balance cell */
.c-balance {
  display: flex;
  align-items: baseline;
  gap: 4px;
}

.balance-val {
  color: var(--accent);
  font-weight: 700;
  font-size: 14px;
}

.balance-cur {
  font-size: 11px;
  color: var(--text-4);
}
/* Keys cell */
.keys-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  font-weight: 600;
  color: var(--text-2);
}

.keys-icon {
  width: 13px;
  height: 13px;
  color: var(--text-4);
}

/* Last active cell */
.c-seen {
  font-size: 12px;
  color: var(--text-3);
  white-space: nowrap;
}

/* Actions cell */
.c-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.view-btn {
  flex-shrink: 0;
}

/* Pagination */
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

.empty-wrap {
  padding: 48px 0;
  display: flex;
  justify-content: center;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.text-emerald {
  color: var(--accent);
}

/* Modal */
.modal-target {
  margin-bottom: 16px;
  font-size: 13px;
}

.modal-target-label {
  color: var(--text-3);
}

.modal-target-id {
  color: var(--text-1);
  font-weight: 600;
}

.modal-target-name {
  color: var(--text-3);
}

.modal-target-bal {
  font-weight: 600;
}

.modal-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
}
.deduct-warning {
  margin: -4px 0 12px 120px;
  font-size: 12.5px;
  color: #f87171;
}
/* ── Medium column: drop the two secondary columns ──────────────── */
@container cust (max-width: 980px) {
  .table-head,
  .table-row {
    grid-template-columns: minmax(160px, 2fr) 140px 140px 120px;
  }

  .c-keys,
  .c-seen {
    display: none;
  }
}

/* ── Tight column: each row becomes a compact card ──────────────── */
@container cust (max-width: 680px) {
  .table-head {
    display: none;
  }

  .table-wrap {
    background: transparent;
    border: none;
    border-radius: 0;
  }

  .table-scroll {
    max-height: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
    overflow: visible;
  }

  .table-row {
    grid-template-columns: 1fr auto;
    grid-template-areas:
      "customer balance"
      "meta actions";
    gap: 12px;
    padding: 14px;
    min-height: 0;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
  }

  .c-customer { grid-area: customer; }
  .c-balance { grid-area: balance; justify-self: end; align-self: center; }
  .c-id { grid-area: meta; align-self: center; }
  .c-keys,
  .c-seen { display: none; }
  .c-actions { grid-area: actions; justify-self: end; }

  .balance-val {
    font-size: 15px;
  }

  .view-btn {
    display: none;
  }
}

/* Real mobile / Telegram Mini App: trim outer padding. */
@media (max-width: 767px) {
  .customers-view {
    padding: 12px;
  }

  .page-title {
    font-size: 18px;
  }

  .pagination-bar {
    flex-direction: column;
    align-items: center;
  }

  .pagination-bar :deep(.n-pagination) {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>

