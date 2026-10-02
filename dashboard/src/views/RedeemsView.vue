<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { fetchRedeems, createRedeemBatch, deleteRedeem, deleteRedeemsBulk, triggerHaptic, triggerHapticNotification } from '@/api'
import {
  NCard,
  NButton,
  NTag,
  NModal,
  NForm,
  NFormItem,
  NInputNumber,
  NInput,
  NRadioGroup,
  NRadioButton,
  NSpin,
  NEmpty,
  NProgress,
  NCheckbox,
  useMessage,
} from 'naive-ui'
import { AddOutline, CopyOutline, SearchOutline, TrashOutline } from '@vicons/ionicons5'


const message = useMessage()

const loading = ref(false)
const redeemsList = ref<any[]>([])

// Toolbar state
const search = ref('')
const modeFilter = ref<'all' | 'single' | 'shared'>('all')
const selected = ref<Set<string>>(new Set())

// Batch modal state
const showBatchModal = ref(false)
const batchLoading = ref(false)
const batchForm = ref({
  amount_ks: 2000,
  mode: 'single' as 'single' | 'shared',
  valid_days: 30,
  count: 5,
})

// Result modal
const showResultModal = ref(false)
const generatedCodes = ref<string[]>([])

// Delete confirmation
const confirmOpen = ref(false)
const confirmBusy = ref(false)
const deleteTargets = ref<string[]>([])

async function loadRedeems(opts?: { silent?: boolean }) {
  const silent = opts?.silent ?? false
  if (!silent) loading.value = true
  try {
    redeemsList.value = await fetchRedeems()
    const alive = new Set(redeemsList.value.map((r: any) => r.code))
    selected.value = new Set([...selected.value].filter((c) => alive.has(c)))
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load redeem codes')
  } finally {
    if (!silent) loading.value = false
  }
}

const filteredCodes = computed(() => {
  const q = search.value.trim().toLowerCase()
  return redeemsList.value
    .filter((r) => modeFilter.value === 'all' || r.mode === modeFilter.value)
    .filter((r) => !q || String(r.code).toLowerCase().includes(q))
    .slice()
    .sort((a, b) => String(b.created_at || '').localeCompare(String(a.created_at || '')))
})

const summary = computed(() => {
  const pool = filteredCodes.value.reduce(
    (acc, r) => acc + (Number(r.remaining) || Number(r.amount) || 0), 0)
  return { total: filteredCodes.value.length, pool }
})

function poolPct(r: any): number {
  const amount = Number(r.amount) || 0
  if (!amount) return 0
  return Math.max(0, Math.min(100, Math.round(((Number(r.remaining) || 0) / amount) * 100)))
}

function poolColor(pct: number): string {
  if (pct <= 10) return '#ef4444'
  if (pct <= 30) return '#f59e0b'
  return '#10b981'
}

function toggleSelect(code: string) {
  const s = new Set(selected.value)
  if (s.has(code)) s.delete(code)
  else s.add(code)
  selected.value = s
}

function toggleSelectAll() {
  if (filteredCodes.value.length > 0 && selected.value.size >= filteredCodes.value.length) {
    selected.value = new Set()
  } else {
    selected.value = new Set(filteredCodes.value.map((r) => r.code))
  }
}

function askDelete(codes: string[]) {
  triggerHaptic('medium')
  deleteTargets.value = codes
  confirmOpen.value = true
}

async function confirmDelete() {
  confirmBusy.value = true
  try {
    if (deleteTargets.value.length === 1) {
      await deleteRedeem(deleteTargets.value[0])
    } else {
      const res: any = await deleteRedeemsBulk(deleteTargets.value)
      if (res?.not_found?.length) message.warning(`${res.not_found.length} code(s) were already gone`)
    }
    triggerHapticNotification('success')
    message.success(`Deleted ${deleteTargets.value.length} redeem code(s)`)
    selected.value = new Set()
    confirmOpen.value = false
    await loadRedeems({ silent: true })
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to delete redeem code')
  } finally {
    confirmBusy.value = false
  }
}

async function handleGenerateBatch() {
  triggerHaptic('medium')
  batchLoading.value = true
  try {
    const res = await createRedeemBatch({
      amount_ks: batchForm.value.amount_ks,
      mode: batchForm.value.mode,
      valid_days: batchForm.value.valid_days,
      count: batchForm.value.count,
    })
    if (res.codes) {
      triggerHapticNotification('success')
      generatedCodes.value = res.codes
      showBatchModal.value = false
      showResultModal.value = true
      await loadRedeems()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to generate redeem codes')
  } finally {
    batchLoading.value = false
  }
}

function copyCode(code: string) {
  triggerHaptic('light')
  navigator.clipboard.writeText(code)
  message.success(`Copied: ${code}`)
}

function copyAllGenerated() {
  triggerHaptic('light')
  const text = generatedCodes.value.join('\n')
  navigator.clipboard.writeText(text)
  message.success('Copied all codes to clipboard!')
}

onMounted(() => {
  loadRedeems()
})

defineExpose({ loadData: loadRedeems })
</script>

<template>
  <div class="redeems-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Redeem Voucher Codes</h1>
        <p class="page-subtitle">Batch generate and manage wallet credit redeem vouchers</p>
      </div>
      <NButton type="primary" size="medium" @click="showBatchModal = true">
        <template #icon>
          <AddOutline />
        </template>
        Batch Generator
      </NButton>
    </div>

    <!-- Toolbar: search, mode filter, selection actions -->
    <div class="toolbar">
      <NInput
        v-model:value="search"
        size="small"
        clearable
        placeholder="Search code…"
        style="max-width: 220px;"
      >
        <template #prefix>
          <SearchOutline />
        </template>
      </NInput>
      <NRadioGroup v-model:value="modeFilter" size="small">
        <NRadioButton value="all">All</NRadioButton>
        <NRadioButton value="single">Single Use</NRadioButton>
        <NRadioButton value="shared">Shared</NRadioButton>
      </NRadioGroup>
      <span class="toolbar-summary">
        {{ summary.total }} code{{ summary.total === 1 ? '' : 's' }} ·
        {{ summary.pool.toLocaleString() }} Ks available
      </span>
      <div class="toolbar-spacer" />
      <template v-if="selected.size > 0">
        <NButton size="small" tertiary @click="toggleSelectAll">
          {{ selected.size >= filteredCodes.length ? 'Clear selection' : 'Select all' }}
        </NButton>
        <NButton size="small" type="error" secondary @click="askDelete([...selected])">
          <template #icon>
            <TrashOutline />
          </template>
          Delete Selected ({{ selected.size }})
        </NButton>
      </template>
      <NButton v-else-if="filteredCodes.length > 0" size="small" tertiary @click="toggleSelectAll">
        Select all
      </NButton>
    </div>

    <!-- Codes Grid / List -->
    <NSpin :show="loading">
      <div v-if="filteredCodes.length > 0" class="redeems-grid">
        <NCard
          v-for="r in filteredCodes"
          :key="r.code"
          class="code-card"
          :class="{ 'code-card--expired': r.expired, 'code-card--selected': selected.has(r.code) }"
          hoverable
        >
          <div class="code-header">
            <div class="code-id">
              <NCheckbox
                :checked="selected.has(r.code)"
                size="small"
                @update:checked="() => toggleSelect(r.code)"
              />
              <span class="code-val font-mono">{{ r.code }}</span>
            </div>
            <div class="code-tags">
              <NTag v-if="r.expired" type="error" size="small" round>Expired</NTag>
              <NTag v-else type="success" size="small" round>Active</NTag>
              <NTag :type="r.mode === 'single' ? 'info' : 'warning'" size="small" round>
                {{ r.mode === 'single' ? 'Single Use' : 'Shared' }}
              </NTag>
            </div>
          </div>

          <div class="code-body">
            <div class="val-row">
              <span class="val-label">Credit:</span>
              <span class="val-amount font-mono">+{{ (r.amount || 0).toLocaleString() }} Ks</span>
            </div>

            <div v-if="r.mode === 'shared'" class="pool-block">
              <NProgress
                type="line"
                :percentage="poolPct(r)"
                :color="poolColor(poolPct(r))"
                :show-indicator="false"
                :height="6"
                :border-radius="3"
              />
              <div class="pool-meta">
                <span>{{ (r.remaining ?? r.amount ?? 0).toLocaleString() }} Ks left</span>
                <span>{{ r.claimed_count ?? 0 }} claimed</span>
              </div>
            </div>

            <div v-if="r.created_at" class="val-row">
              <span class="val-label">Created:</span>
              <span class="val-exp font-mono">{{ String(r.created_at).slice(0, 10) }}</span>
            </div>
            <div class="val-row">
              <span class="val-label">Expires:</span>
              <span class="val-exp font-mono">{{ r.expires_at || 'Never' }}</span>
            </div>
          </div>

          <div class="code-footer">
            <NButton size="small" secondary style="flex: 1;" @click="copyCode(r.code)">
              <template #icon>
                <CopyOutline />
              </template>
              Copy Code
            </NButton>
            <NButton
              size="small"
              secondary
              type="error"
              style="flex: 1;"
              @click="askDelete([r.code])"
            >
              <template #icon>
                <TrashOutline />
              </template>
              Delete
            </NButton>
          </div>
        </NCard>
      </div>

      <div v-else class="empty-wrap">
        <NEmpty :description="redeemsList.length > 0 ? 'No codes match the current filters' : 'No active redeem codes found'" />
      </div>
    </NSpin>

    <!-- Delete confirmation -->
    <NModal :block-scroll="false"
      v-model:show="confirmOpen"
      preset="card"
      :title="deleteTargets.length === 1 ? 'Delete Redeem Code' : `Delete ${deleteTargets.length} Redeem Codes`"
      style="max-width: 420px;"
    >
      <template v-if="deleteTargets.length === 1">
        <p class="confirm-text">
          Delete <span class="font-mono confirm-code">{{ deleteTargets[0] }}</span> permanently?
        </p>
      </template>
      <div v-else class="codes-output-box confirm-list">
        <div v-for="c in deleteTargets" :key="c" class="code-line font-mono">{{ c }}</div>
      </div>
      <p class="confirm-warning">
        ⚠️ Customers who already received {{ deleteTargets.length === 1 ? 'this code' : 'these codes' }}
        will not be able to redeem {{ deleteTargets.length === 1 ? 'it' : 'them' }} anymore. This cannot be undone.
      </p>
      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
        <NButton :disabled="confirmBusy" @click="confirmOpen = false">Cancel</NButton>
        <NButton type="error" :loading="confirmBusy" @click="confirmDelete">
          Delete {{ deleteTargets.length > 1 ? deleteTargets.length + ' codes' : 'code' }}
        </NButton>
      </div>
    </NModal>

    <!-- Batch Gen Modal -->
    <NModal :block-scroll="false"
      v-model:show="showBatchModal"
      preset="card"
      title="Batch Generate Redeem Codes"
      style="max-width: 440px;"
    >
      <NForm :model="batchForm" label-placement="left" label-width="120">
        <NFormItem label="Amount (MMK)">
          <NInputNumber v-model:value="batchForm.amount_ks" :step="1000" :min="100" />
        </NFormItem>

        <NFormItem label="Mode">
          <NRadioGroup v-model:value="batchForm.mode">
            <NRadioButton value="single">Single Use</NRadioButton>
            <NRadioButton value="shared">Shared (Multi)</NRadioButton>
          </NRadioGroup>
        </NFormItem>

        <NFormItem label="Valid Days">
          <NInputNumber v-model:value="batchForm.valid_days" :min="1" :max="180" />
        </NFormItem>

        <NFormItem label="Number of Codes">
          <NInputNumber v-model:value="batchForm.count" :min="1" :max="50" />
        </NFormItem>

        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
          <NButton @click="showBatchModal = false">Cancel</NButton>
          <NButton type="primary" :loading="batchLoading" @click="handleGenerateBatch">
            Create Batch
          </NButton>
        </div>
      </NForm>
    </NModal>

    <!-- Result Modal -->
    <NModal :block-scroll="false"
      v-model:show="showResultModal"
      preset="card"
      title="Generated Voucher Codes"
      style="max-width: 460px;"
    >
      <p style="color: var(--text-3); font-size: 13px; margin-bottom: 12px;">
        Successfully generated {{ generatedCodes.length }} redeem codes:
      </p>
      <div class="codes-output-box">
        <div v-for="c in generatedCodes" :key="c" class="code-line font-mono">
          {{ c }}
        </div>
      </div>
      <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
        <NButton secondary @click="copyAllGenerated">
          <template #icon>
            <CopyOutline />
          </template>
          Copy All
        </NButton>
        <NButton type="primary" @click="showResultModal = false">Done</NButton>
      </div>
    </NModal>
  </div>
</template>

<style scoped>
.redeems-view {
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
  color: var(--text-1);
}

.page-subtitle {
  margin: 4px 0 0 0;
  font-size: 13px;
  color: var(--text-3);
}

.redeems-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(260px, 1fr));
  gap: 16px;
}

.code-card {
  border: 1px solid var(--border);
}

.toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
  margin-bottom: 18px;
}

.toolbar-spacer {
  flex: 1;
}

.toolbar-summary {
  font-size: 12px;
  color: var(--text-3);
  font-family: 'JetBrains Mono', monospace;
}

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}

.code-id {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.code-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.code-card--expired .code-val {
  color: var(--text-4);
  text-decoration: line-through;
}

.code-card--selected {
  border-color: var(--accent) !important;
}

.pool-block {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 2px 0;
}

.pool-meta {
  display: flex;
  justify-content: space-between;
  font-size: 11px;
  color: var(--text-3);
}

.confirm-text {
  margin: 0 0 8px 0;
  font-size: 14px;
  color: var(--text-1);
}

.confirm-code {
  color: var(--accent);
  font-weight: 700;
}

.confirm-list {
  max-height: 160px;
  margin-bottom: 8px;
}

.confirm-warning {
  margin: 8px 0 0 0;
  font-size: 12px;
  color: var(--warn, #f59e0b);
}

.code-val {
  font-size: 14px;
  font-weight: 700;
  color: var(--accent);
}

.code-body {
  display: flex;
  flex-direction: column;
  gap: 6px;
  margin-bottom: 14px;
  font-size: 13px;
}

.code-footer {
  display: flex;
  gap: 8px;
}

.val-row {
  display: flex;
  justify-content: space-between;
}

.val-label {
  color: var(--text-3);
}

.val-amount {
  font-weight: 600;
  color: var(--text-1);
}

.val-exp {
  font-size: 11px;
  color: var(--text-4);
}

.codes-output-box {
  background: var(--surface-2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 12px;
  max-height: 200px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.code-line {
  color: var(--accent);
  font-size: 13px;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.empty-wrap {
  padding: 48px 0;
  display: flex;
  justify-content: center;
}
</style>
