<script setup lang="ts">
import { ref, computed, watch, onMounted } from 'vue'
import {
  fetchKeys,
  fetchServers,
  createKey,
  extendKey,
  deleteKey,
  triggerHaptic,
  triggerHapticNotification,
} from '@/api'
import {
  NCard,
  NInput,
  NSelect,
  NButton,
  NModal,
  NForm,
  NFormItem,
  NInputNumber,
  NSpin,
  NPagination,
  NEmpty,
  useMessage,
} from 'naive-ui'
import {
  AddOutline,
  SearchOutline,
  CopyOutline,
  CalendarOutline,
  TrashOutline,
} from '@vicons/ionicons5'

const message = useMessage()

const loading = ref(false)
const allKeys = ref<any[]>([])
const totalKeys = ref(0)

const searchQuery = ref('')
const selectedServer = ref<string>('')
const statusFilter = ref<'all' | 'expiring' | 'expired' | 'active'>('all')
const page = ref(1)
const pageSize = ref(20)

const statusOptions = [
  { label: 'All Statuses', value: 'all' },
  { label: 'Expiring Soon (≤7 days)', value: 'expiring' },
  { label: 'Expired', value: 'expired' },
  { label: 'Active', value: 'active' },
]

// Expiry dates arrive in mixed formats (DD.MM.YY, DD.MM.YYYY, DD/MM/YYYY).
function parseExpiry(value?: string): Date | null {
  if (!value) return null
  const m = String(value).match(/(\d{1,2})[./-](\d{1,2})[./-](\d{2,4})/)
  if (!m) return null
  let year = parseInt(m[3], 10)
  if (year < 100) year += 2000
  const dt = new Date(year, parseInt(m[2], 10) - 1, parseInt(m[1], 10))
  return isNaN(dt.getTime()) ? null : dt
}

function daysLeft(value?: string): number | null {
  const dt = parseExpiry(value)
  if (!dt) return null
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  return Math.round((dt.getTime() - today.getTime()) / 86400000)
}

function expiryLabel(value?: string): string {
  const d = daysLeft(value)
  if (d === null) return 'No expiry'
  if (d < 0) return `Expired ${Math.abs(d)}d ago`
  if (d === 0) return 'Expires today'
  if (d === 1) return '1 day left'
  return `${d} days left`
}

function expiryClass(value?: string): string {
  const d = daysLeft(value)
  if (d === null) return 'muted'
  if (d < 0) return 'expired'
  if (d <= 7) return 'expiring'
  return 'active'
}

const expiringSoonCount = computed(
  () => allKeys.value.filter((k) => { const d = daysLeft(k.expire_date); return d !== null && d >= 0 && d <= 7 }).length,
)

const filteredKeys = computed(() => {
  let list = allKeys.value
  if (selectedServer.value) {
    list = list.filter((k) => String(k.server) === String(selectedServer.value))
  }
  const q = searchQuery.value.trim().toLowerCase()
  if (q) {
    list = list.filter(
      (k) =>
        String(k.name || '').toLowerCase().includes(q) ||
        String(k.chat_id || '').toLowerCase().includes(q) ||
        String(k.key_id || '').toLowerCase().includes(q),
    )
  }
  if (statusFilter.value !== 'all') {
    list = list.filter((k) => {
      const d = daysLeft(k.expire_date)
      if (statusFilter.value === 'expired') return d !== null && d < 0
      if (statusFilter.value === 'expiring') return d !== null && d >= 0 && d <= 7
      return d === null || d > 7
    })
  }
  return [...list].sort((a, b) => {
    const da = daysLeft(a.expire_date)
    const db = daysLeft(b.expire_date)
    if (da === null && db === null) return 0
    if (da === null) return 1
    if (db === null) return -1
    return da - db
  })
})

const filteredCount = computed(() => filteredKeys.value.length)

const pagedKeys = computed(() => {
  const start = (page.value - 1) * pageSize.value
  return filteredKeys.value.slice(start, start + pageSize.value)
})

const rangeStart = computed(() => (filteredCount.value === 0 ? 0 : (page.value - 1) * pageSize.value + 1))
const rangeEnd = computed(() => Math.min(page.value * pageSize.value, filteredCount.value))

// Any filter or page-size change returns to the first page.
watch([searchQuery, selectedServer, statusFilter, pageSize], () => {
  page.value = 1
})

// Create modal
const showCreateModal = ref(false)
const createLoading = ref(false)
const createForm = ref({
  server_id: '1',
  name: '',
  data_limit_gb: 50,
  valid_days: 30,
  assign_to_user_id: '',
})

// Server dropdowns are driven by the backend's configured server list
// (Settings / .env) — never a hardcoded set, so unconfigured servers
// (e.g. a deleted "Server 3") cannot appear as filter or target options.
const configuredServers = ref<{ id: number | string; name: string }[]>([])

const serverOptions = computed(() => [
  { label: 'All Servers', value: '' },
  ...configuredServers.value.map((s) => ({ label: s.name, value: String(s.id) })),
])

const provisionServerOptions = computed(() =>
  configuredServers.value.map((s) => ({ label: s.name, value: String(s.id) })),
)

async function loadServers() {
  try {
    const res = await fetchServers()
    configuredServers.value = res.servers || []
  } catch {
    configuredServers.value = []
  }
  // Keep the current selections valid if the configured set changed.
  if (!configuredServers.value.some((s) => String(s.id) === String(selectedServer.value))) {
    selectedServer.value = ''
  }
  if (!configuredServers.value.some((s) => String(s.id) === createForm.value.server_id)) {
    createForm.value.server_id = configuredServers.value[0]
      ? String(configuredServers.value[0].id)
      : '1'
  }
}


async function loadKeys(opts?: { silent?: boolean }) {
  // Silent mode = background refresh on a pushed change: update data in
  // place without the NSpin overlay, so the list never dims or flickers.
  const silent = opts?.silent ?? false
  if (!silent) loading.value = true
  try {
    // Fetch the full set once; search, server, status filtering and pagination
    // are all handled client-side for instant response (no per-keystroke round trip).
    const res = await fetchKeys({ page_size: 1000 })
    allKeys.value = res.items || []
    totalKeys.value = res.total || allKeys.value.length
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load access keys')
  } finally {
    if (!silent) loading.value = false
  }
}

async function handleExtend(row: any): Promise<boolean> {
  triggerHaptic('medium')
  try {
    const res = await extendKey(row.key_id, 30)
    if (res.success) {
      triggerHapticNotification('success')
      message.success(`Extended key ${row.key_id} to ${res.new_expire_date}`)
      await loadKeys()
      return true
    }
    return false
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to extend key')
    return false
  }
}

function copyKeyUrl(url: string) {
  triggerHaptic('light')
  navigator.clipboard.writeText(url)
  message.info('Key access URL copied to clipboard!')
}

async function handleDelete(row: any): Promise<boolean> {
  triggerHaptic('medium')
  try {
    const res = await deleteKey(row.server, row.key_id)
    if (res.success) {
      triggerHapticNotification('success')
      message.success(`Deleted key ${row.name || row.key_id}`)
      await loadKeys()
      return true
    }
    return false
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to delete key')
    return false
  }
}

// ── Confirm dialog (replaces the cramped anchored NPopconfirm) ──────
type ConfirmAction = 'extend' | 'delete'
const confirmOpen = ref(false)
const confirmAction = ref<ConfirmAction>('extend')
const confirmTarget = ref<any>(null)
const confirmBusy = ref(false)

function openConfirm(action: ConfirmAction, row: any) {
  triggerHaptic('light')
  confirmAction.value = action
  confirmTarget.value = row
  confirmOpen.value = true
}

function closeConfirm() {
  if (confirmBusy.value) return
  confirmOpen.value = false
}

async function runConfirm() {
  if (!confirmTarget.value || confirmBusy.value) return
  confirmBusy.value = true
  try {
    const ok = confirmAction.value === 'extend'
      ? await handleExtend(confirmTarget.value)
      : await handleDelete(confirmTarget.value)
    if (ok) {
      confirmOpen.value = false
      confirmTarget.value = null
    }
  } finally {
    confirmBusy.value = false
  }
}

const confirmTitle = computed(() =>
  confirmAction.value === 'extend' ? 'Extend Access Key' : 'Delete Access Key')
const confirmVerb = computed(() =>
  confirmAction.value === 'extend' ? 'Extend +30 Days' : 'Delete Permanently')

const newExpiryText = computed(() => {
  const dt = parseExpiry(confirmTarget.value?.expire_date)
  if (!dt) return ''
  const nd = new Date(dt.getTime() + 30 * 86400000)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${p(nd.getDate())}.${p(nd.getMonth() + 1)}.${nd.getFullYear()}`
})

async function handleCreateKey() {
  if (!createForm.value.name) {
    message.warning('Key name is required')
    return
  }
  createLoading.value = true
  try {
    const res = await createKey({
      server_id: createForm.value.server_id,
      name: createForm.value.name,
      data_limit_gb: createForm.value.data_limit_gb,
      valid_days: createForm.value.valid_days,
      assign_to_user_id: createForm.value.assign_to_user_id || undefined,
    })
    if (res.success) {
      triggerHapticNotification('success')
      message.success('New Outline key successfully provisioned!')
      showCreateModal.value = false
      createForm.value.name = ''
      await loadKeys()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to create key')
  } finally {
    createLoading.value = false
  }
}

onMounted(() => {
  loadKeys()
  loadServers()
})

defineExpose({
  loadData: loadKeys,
})
</script>

<template>
  <div class="keys-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Outline Access Keys</h1>
        <p class="page-subtitle">Manage, extend, and provision VPN credentials across servers</p>
      </div>
      <NButton class="provision-btn" type="primary" size="medium" @click="showCreateModal = true">
        <template #icon>
          <AddOutline />
        </template>
        Provision Key
      </NButton>
    </div>

    <!-- Filters Bar -->
    <NCard class="filter-card">
      <div class="filters-row">
        <NInput
          v-model:value="searchQuery"
          placeholder="Search by key name, chat ID, key ID..."
          clearable
          class="search-input"
        >
          <template #prefix>
            <SearchOutline />
          </template>
        </NInput>

        <NSelect
          v-model:value="statusFilter"
          :options="statusOptions"
          class="status-select"
        />

        <NSelect
          v-model:value="selectedServer"
          :options="serverOptions"
          placeholder="Filter by Server"
          class="server-select"
        />
      </div>

      <div class="filter-summary">
        <span>{{ totalKeys }} total keys</span>
        <span v-if="expiringSoonCount > 0" class="summary-warn">
          {{ expiringSoonCount }} expiring within 7 days
        </span>
        <span v-if="filteredCount !== totalKeys" class="summary-muted">
          {{ filteredCount }} match current filters
        </span>
      </div>
    </NCard>

    <!-- Keys List / Table -->
    <NSpin :show="loading">
      <div v-if="pagedKeys.length > 0" class="keys-list-wrap">
        <div v-for="k in pagedKeys" :key="`${k.server}_${k.key_id}`" class="key-card">
          <div class="key-main">
            <div class="key-identity">
              <span class="key-name">{{ k.label || k.name }}</span>
              <span class="expiry-pill" :class="expiryClass(k.expire_date)">
                {{ expiryLabel(k.expire_date) }}
              </span>
            </div>

            <div class="key-meta">
              <span class="meta-server">Server {{ k.server }}</span>
              <span class="meta-sep">·</span>
              <span class="font-mono">ID {{ k.key_id }}</span>
              <template v-if="k.chat_id">
                <span class="meta-sep">·</span>
                <span class="font-mono">UID {{ k.chat_id }}</span>
              </template>
            </div>

            <div class="key-expiry">
              <CalendarOutline class="cal-icon" />
              <span class="expiry-label">Expires</span>
              <span class="expiry-val font-mono">{{ k.expire_date || 'N/A' }}</span>
            </div>
          </div>

          <div class="key-actions">
            <NButton
              v-if="k.access_url"
              class="action-copy"
              size="small"
              secondary
              aria-label="Copy access link"
              @click="copyKeyUrl(k.access_url)"
            >
              <template #icon>
                <CopyOutline />
              </template>
              <span class="btn-text">Copy Link</span>
            </NButton>

            <NButton
              class="action-extend"
              size="small"
              type="primary"
              secondary
              @click="openConfirm('extend', k)"
            >
              +30 Days Extend
            </NButton>

            <NButton
              class="action-delete"
              size="small"
              type="error"
              secondary
              aria-label="Delete key"
              @click="openConfirm('delete', k)"
            >
              <template #icon>
                <TrashOutline />
              </template>
              <span class="btn-text">Delete</span>
            </NButton>
          </div>
        </div>
      </div>

      <!-- Pagination -->
      <div v-if="filteredCount > 0" class="pagination-bar">
        <span class="result-count">
          Showing {{ rangeStart }}–{{ rangeEnd }} of {{ filteredCount }}
        </span>
        <NPagination
          v-model:page="page"
          v-model:page-size="pageSize"
          :item-count="filteredCount"
          :page-sizes="[10, 20, 50]"
          show-size-picker
        />
      </div>

      <div v-else class="empty-wrap">
        <NEmpty description="No keys match the current filters" />
      </div>
    </NSpin>

    <!-- Create Key Modal -->
    <NModal
      v-model:show="showCreateModal"
      preset="card"
      title="Provision Outline Key"
      style="max-width: 480px;"
    >
      <NForm :model="createForm" label-placement="left" label-width="120">
        <NFormItem label="Target Server">
          <NSelect
            v-model:value="createForm.server_id"
            :options="provisionServerOptions"
          />
        </NFormItem>

        <NFormItem label="Key Label / Name">
          <NInput v-model:value="createForm.name" placeholder="e.g. VIP Customer John" />
        </NFormItem>

        <NFormItem label="Data Limit (GB)">
          <NInputNumber v-model:value="createForm.data_limit_gb" :min="0" :max="1000" />
        </NFormItem>

        <NFormItem label="Validity (Days)">
          <NInputNumber v-model:value="createForm.valid_days" :min="1" :max="365" />
        </NFormItem>

        <NFormItem label="Assign Chat ID">
          <NInput v-model:value="createForm.assign_to_user_id" placeholder="Optional Telegram Chat ID" />
        </NFormItem>

        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
          <NButton @click="showCreateModal = false">Cancel</NButton>
          <NButton type="primary" :loading="createLoading" @click="handleCreateKey">
            Generate Key
          </NButton>
        </div>
      </NForm>
    </NModal>

    <!-- Confirm Extend / Delete -->
    <NModal
      v-model:show="confirmOpen"
      preset="card"
      :bordered="false"
      :auto-focus="false"
      :mask-closable="!confirmBusy"
      class="confirm-modal"
      style="max-width: 400px; width: calc(100vw - 32px);"
    >
      <div class="confirm-body">
        <div class="confirm-icon" :class="confirmAction">
          <CalendarOutline v-if="confirmAction === 'extend'" />
          <TrashOutline v-else />
        </div>
        <h3 class="confirm-title">{{ confirmTitle }}</h3>
        <p class="confirm-desc">
          <span class="confirm-key-name">{{ confirmTarget?.name || confirmTarget?.key_id }}</span>
          <template v-if="confirmAction === 'extend'">
            gets 30 more days on Server {{ confirmTarget?.server }}<template v-if="newExpiryText">
            — new expiry {{ newExpiryText }}.</template
            >
          </template>
          <template v-else>
            will be permanently removed from Server {{ confirmTarget?.server }}.
            This cannot be undone.
          </template>
        </p>
      </div>
      <div class="confirm-actions">
        <NButton class="confirm-cancel" :disabled="confirmBusy" @click="closeConfirm">
          Cancel
        </NButton>
        <NButton
          class="confirm-ok"
          :type="confirmAction === 'delete' ? 'error' : 'primary'"
          :loading="confirmBusy"
          @click="runConfirm"
        >
          {{ confirmVerb }}
        </NButton>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.keys-view {
  padding: 24px;
}

.view-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 20px;
  flex-wrap: wrap;
  gap: 16px;
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

.status-select {
  flex: 1;
  min-width: 170px;
}

.server-select {
  flex: 1;
  min-width: 180px;
}

.filter-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 14px;
  margin-top: 12px;
  font-size: 12px;
  color: var(--text-3);
}

.summary-warn {
  color: var(--warn);
  font-weight: 600;
}

.summary-muted {
  color: var(--text-4);
}

.keys-list-wrap {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.key-card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
  transition: border-color 0.15s ease, background 0.15s ease;
}

.key-card:hover {
  border-color: var(--border-strong);
  background: var(--surface-hover);
}

.key-main {
  display: flex;
  flex-direction: column;
  gap: 6px;
  flex: 1;
  min-width: 0;
}

.key-identity {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.key-name {
  font-size: 15px;
  font-weight: 600;
  color: var(--text-1);
  flex: 1;
  min-width: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.key-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 11.5px;
  color: var(--text-4);
  min-width: 0;
}

.meta-server {
  color: var(--text-3);
  font-weight: 600;
}

.meta-sep {
  color: var(--text-4);
}

.key-expiry {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
}

.expiry-pill {
  font-size: 11px;
  font-weight: 600;
  padding: 2px 9px;
  border-radius: 10px;
  flex-shrink: 0;
  white-space: nowrap;
}

.expiry-pill.expired {
  color: var(--danger);
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.25);
}

.expiry-pill.expiring {
  color: var(--warn);
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.expiry-pill.active {
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-border);
}

.expiry-pill.muted {
  color: var(--text-4);
  background: var(--fill-subtle);
  border: 1px solid var(--border);
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

.empty-wrap {
  padding: 48px 0;
  display: flex;
  justify-content: center;
}

.cal-icon {
  width: 14px;
  height: 14px;
  color: var(--text-3);
}

.expiry-label {
  color: var(--text-4);
}

.expiry-val {
  color: var(--text-2);
  font-weight: 600;
}

.key-actions {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-shrink: 0;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

/* ── Confirm dialog (extend / delete) ───────────────────────────── */
.confirm-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 10px;
  padding: 6px 4px 2px;
}

.confirm-icon {
  width: 46px;
  height: 46px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 2px;
}

.confirm-icon :deep(svg) {
  width: 20px;
  height: 20px;
}

.confirm-icon.extend {
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-border);
  color: var(--accent);
}

.confirm-icon.delete {
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.28);
  color: var(--danger-soft);
}

.confirm-title {
  margin: 0;
  font-size: 16.5px;
  font-weight: 700;
  color: var(--text-1);
}

.confirm-desc {
  margin: 0;
  font-size: 13px;
  line-height: 1.55;
  color: var(--text-3);
}

.confirm-key-name {
  display: block;
  color: var(--text-1);
  font-weight: 600;
  margin-bottom: 2px;
  word-break: break-word;
}

.confirm-actions {
  display: flex;
  gap: 10px;
  margin-top: 18px;
}

.confirm-cancel,
.confirm-ok {
  flex: 1;
}

/* ── Mobile (Telegram Mini App width) ───────────────────────────── */
@media (max-width: 767px) {
  .keys-view {
    padding: 12px;
  }

  .view-header {
    flex-direction: column;
    align-items: stretch;
    gap: 10px;
    margin-bottom: 14px;
  }

  .page-title {
    font-size: 18px;
  }

  .provision-btn {
    width: 100%;
  }

  .filter-card {
    margin-bottom: 14px;
  }

  .filters-row {
    gap: 8px;
  }

  .search-input {
    flex: 1 1 100%;
    min-width: 0;
  }

  .status-select,
  .server-select {
    flex: 1 1 0;
    min-width: 0;
  }

  .filter-summary {
    gap: 10px;
    margin-top: 10px;
  }

  .keys-list-wrap {
    gap: 10px;
  }

  /* With flex-wrap: wrap on a column container, align-items: stretch does not
     size the items — pin children to 100% so long names truncate instead of
     pushing the expiry pill outside the card. */
  .key-card {
    flex-direction: column;
    flex-wrap: nowrap;
    align-items: stretch;
    gap: 12px;
    padding: 14px;
  }

  .key-main,
  .key-actions {
    width: 100%;
  }

  .key-identity {
    overflow: hidden;
  }

  .key-name {
    font-size: 14px;
  }

  /* Copy/Delete become icon-only; Extend keeps its label and takes the slack */
  .key-actions {
    display: grid;
    grid-template-columns: 46px 1fr 46px;
    gap: 8px;
  }

  .key-actions :deep(.n-button) {
    width: 100%;
    height: 40px;
    padding-inline: 0;
    justify-content: center;
  }

  .action-copy :deep(.n-button__content),
  .action-delete :deep(.n-button__content) {
    display: none;
  }

  .pagination-bar {
    flex-direction: column;
    align-items: center;
    gap: 10px;
  }

  .pagination-bar :deep(.n-pagination) {
    flex-wrap: wrap;
    justify-content: center;
  }
}
</style>
