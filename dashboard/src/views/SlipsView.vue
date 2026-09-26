<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  fetchSlips,
  fetchSlipImage,
  reviewSlip,
  triggerHaptic,
  triggerHapticNotification,
} from '@/api'
import {
  NCard,
  NTabs,
  NTabPane,
  NButton,
  NSpin,
  NModal,
  NInput,
  NEmpty,
  useMessage,
} from 'naive-ui'
import {
  CheckmarkCircleOutline,
  CloseCircleOutline,
  TimeOutline,
} from '@vicons/ionicons5'

const message = useMessage()

const currentTab = ref('PENDING')
const loading = ref(false)
const slips = ref<any[]>([])

// Reject modal state
const showRejectModal = ref(false)
const rejectReason = ref('')
const selectedSlipId = ref<string | null>(null)
const actionLoading = ref(false)

// Image Lightbox state
const showImageModal = ref(false)
const selectedImageUrl = ref('')
const imageLoading = ref(false)

// slip.id → blob object URL, filled asynchronously via the authed proxy.
const imageUrls = ref<Record<string, string>>({})

async function loadSlips(opts?: { silent?: boolean }) {
  // Silent mode = background refresh on a pushed change: no spinner overlay,
  // the queue updates in place without dimming.
  const silent = opts?.silent ?? false
  if (!silent) loading.value = true
  try {
    slips.value = await fetchSlips(currentTab.value)
    prefetchImages()
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load slips queue')
  } finally {
    if (!silent) loading.value = false
  }
}

function prefetchImages() {
  for (const slip of slips.value) {
    if (!slip.file_id || imageUrls.value[slip.id]) continue
    fetchSlipImage(slip.id).then((url) => {
      if (url) imageUrls.value = { ...imageUrls.value, [slip.id]: url }
    })
  }
}

function handleTabChange(tab: string) {
  triggerHaptic('light')
  currentTab.value = tab
  loadSlips()
}

async function handleApprove(slip: any) {
  triggerHaptic('medium')
  actionLoading.value = true
  try {
    const res = await reviewSlip(slip.id, 'APPROVE')
    if (res.success) {
      triggerHapticNotification('success')
      message.success(`Approved slip ${slip.id}. User wallet balance: ${res.new_balance.toLocaleString()} Ks`)
      await loadSlips()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to approve slip')
  } finally {
    actionLoading.value = false
  }
}

function openRejectPrompt(slipId: string) {
  triggerHaptic('light')
  selectedSlipId.value = slipId
  rejectReason.value = 'ပြေစာအချက်အလက် မကိုက်ညီပါ'
  showRejectModal.value = true
}

async function confirmReject() {
  if (!selectedSlipId.value) return
  actionLoading.value = true
  try {
    const res = await reviewSlip(selectedSlipId.value, 'REJECT', rejectReason.value)
    if (res.success) {
      triggerHapticNotification('warning')
      message.warning(`Rejected slip ${selectedSlipId.value}`)
      showRejectModal.value = false
      await loadSlips()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to reject slip')
  } finally {
    actionLoading.value = false
  }
}

async function viewImage(slip: any) {
  showImageModal.value = true
  const cached = imageUrls.value[slip.id] || slip.image_url
  if (cached) {
    selectedImageUrl.value = cached
    return
  }
  if (!slip.file_id) {
    selectedImageUrl.value = 'https://placehold.co/600x800/1e293b/10b981?text=No+Receipt+Stored'
    return
  }
  selectedImageUrl.value = ''
  imageLoading.value = true
  try {
    const url = await fetchSlipImage(slip.id)
    if (url) imageUrls.value = { ...imageUrls.value, [slip.id]: url }
    selectedImageUrl.value =
      url || 'https://placehold.co/600x800/1e293b/10b981?text=Receipt+Unavailable'
  } finally {
    imageLoading.value = false
  }
}

// "2026-09-26 13:01:06" → "26 Sep, 13:01" for the compact mobile sub-line.
function shortTime(value?: string): string {
  if (!value) return '—'
  const dt = new Date(value.replace(' ', 'T'))
  if (isNaN(dt.getTime())) return value
  return dt.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
  })
}

onMounted(() => {
  loadSlips()
})

defineExpose({ loadData: loadSlips })
</script>

<template>
  <div class="slips-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Slips Verification Queue</h1>
        <p class="page-subtitle">Verify user payment receipts and credit wallet balances</p>
      </div>
    </div>

    <!-- Filter Tabs -->
    <NTabs
      v-model:value="currentTab"
      type="line"
      animated
      class="filter-tabs"
      @update:value="handleTabChange"
    >
      <NTabPane name="PENDING" tab="Pending Review" />
      <NTabPane name="APPROVED" tab="Approved" />
      <NTabPane name="REJECTED" tab="Rejected" />
      <NTabPane name="ALL" tab="All History" />
    </NTabs>

    <NSpin :show="loading">
      <div v-if="slips.length > 0" class="slips-table">
        <!-- Column headers (desktop only) -->
        <div class="table-head">
          <span class="cell c-slip">Slip</span>
          <span class="cell c-customer">Customer</span>
          <span class="cell c-amount">Amount</span>
          <span class="cell c-tx">Tx ID (OCR)</span>
          <span class="cell c-time">Submitted</span>
          <span class="cell c-status">Status</span>
          <span class="cell c-actions">Actions</span>
        </div>

        <div v-for="slip in slips" :key="slip.id" class="table-row">
          <div class="cell c-slip">
            <button class="slip-thumb" aria-label="View receipt image" @click="viewImage(slip)">
              <img
                v-if="imageUrls[slip.id] || slip.image_url"
                :src="imageUrls[slip.id] || slip.image_url"
                alt="Receipt"
                loading="lazy"
              />
              <span v-else-if="slip.file_id" class="thumb-loading" />
              <span v-else class="thumb-empty">—</span>
            </button>
            <div class="slip-id-block">
              <span class="slip-id font-mono">{{ slip.id }}</span>
              <span class="slip-sub desktop-hidden">
                {{ slip.username }} · {{ shortTime(slip.created_at) }}
              </span>
            </div>
          </div>

          <div class="cell c-customer">
            <span class="customer-name">{{ slip.username }}</span>
            <span class="customer-chat font-mono">{{ slip.chat_id }}</span>
          </div>

          <div class="cell c-amount">
            <span class="amount-val font-mono">+{{ slip.amount.toLocaleString() }}</span>
            <span class="amount-cur">Ks</span>
          </div>

          <div class="cell c-tx">
            <span v-if="slip.extracted_tx_id" class="tx-chip font-mono">{{ slip.extracted_tx_id }}</span>
            <span v-else class="muted">—</span>
          </div>

          <div class="cell c-time">
            <TimeOutline class="time-icon" />
            <span class="time-val">{{ slip.created_at }}</span>
          </div>

          <div class="cell c-status">
            <span class="status-pill" :class="slip.status.toLowerCase()">{{ slip.status }}</span>
          </div>

          <div class="cell c-actions">
            <template v-if="slip.status === 'PENDING'">
              <NButton
                size="small"
                type="primary"
                class="act-btn"
                :loading="actionLoading"
                @click="handleApprove(slip)"
              >
                <template #icon>
                  <CheckmarkCircleOutline />
                </template>
                Approve
              </NButton>
              <NButton
                size="small"
                type="error"
                secondary
                class="act-btn"
                :loading="actionLoading"
                @click="openRejectPrompt(slip.id)"
              >
                <template #icon>
                  <CloseCircleOutline />
                </template>
                Reject
              </NButton>
            </template>
            <span v-else class="reviewed-note">
              by {{ slip.reviewed_by || 'Admin' }}<template v-if="slip.review_reason"> · “{{ slip.review_reason }}”</template>
            </span>
          </div>
        </div>
      </div>

      <div v-else class="empty-wrap">
        <NEmpty description="No slips found in this queue" />
      </div>
    </NSpin>

    <!-- Reject Reason Modal -->
    <NModal
      v-model:show="showRejectModal"
      preset="dialog"
      title="Reject Payment Receipt"
      positive-text="Confirm Reject"
      negative-text="Cancel"
      type="error"
      @positive-click="confirmReject"
    >
      <p style="color: var(--text-2); font-size: 13px; margin-bottom: 12px;">
        User will be notified in Telegram that this slip was rejected.
      </p>
      <NInput
        v-model:value="rejectReason"
        type="textarea"
        placeholder="Enter rejection reason (e.g. Transaction ID already claimed)"
        :rows="3"
      />
    </NModal>

    <!-- Image Lightbox Modal -->
    <NModal v-model:show="showImageModal">
      <NCard
        style="width: 90vw; max-width: 600px; max-height: 90vh; overflow: auto;"
        title="Payment Receipt Lightbox"
        :bordered="false"
        size="huge"
        role="dialog"
        aria-modal="true"
        closable
        @close="showImageModal = false"
      >
        <div class="lightbox-body">
          <NSpin v-if="imageLoading" size="large" />
          <img
            v-else-if="selectedImageUrl"
            :src="selectedImageUrl"
            alt="Receipt Full Preview"
            style="max-width: 100%; height: auto; border-radius: 8px;"
          />
        </div>
      </NCard>
    </NModal>
  </div>
</template>

<style scoped>
.slips-view {
  padding: 24px;
  /* Query the table against the width it actually gets (content area minus
     the 250px desktop sidebar), not the viewport — so it degrades on a
     narrow content column even on a wide screen. */
  container-type: inline-size;
  container-name: slips;
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

.filter-tabs {
  margin-bottom: 20px;
}

/* ── Compact slips table ────────────────────────────────────────── */
.slips-table {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  overflow: hidden;
}

.table-head,
.table-row {
  display: grid;
  grid-template-columns: 190px minmax(120px, 1.2fr) 80px minmax(90px, 1fr) 150px 92px 200px;
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

/* Slip cell: thumbnail + id */
.c-slip {
  display: flex;
  align-items: center;
  gap: 10px;
}

.slip-thumb {
  width: 40px;
  height: 40px;
  flex-shrink: 0;
  padding: 0;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  border: 1px solid var(--border);
  background: var(--surface-2);
}

.slip-thumb img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  display: block;
}

/* Shimmer shown while the receipt blob is being fetched through the proxy */
.thumb-loading {
  display: block;
  width: 100%;
  height: 100%;
  background: linear-gradient(100deg, var(--surface-2) 40%, var(--surface-hover) 50%, var(--surface-2) 60%);
  background-size: 200% 100%;
  animation: thumb-shimmer 1.2s ease-in-out infinite;
}

@keyframes thumb-shimmer {
  from { background-position: 120% 0; }
  to { background-position: -20% 0; }
}

.thumb-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 100%;
  color: var(--text-4);
  font-size: 12px;
}

.lightbox-body {
  display: flex;
  justify-content: center;
  align-items: center;
  min-height: 240px;
}

.slip-id-block {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.slip-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-1);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.slip-sub {
  font-size: 11px;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
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

.amount-cur {
  font-size: 11px;
  color: var(--text-4);
}

/* Tx ID cell */
.tx-chip {
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

.muted {
  color: var(--text-4);
}

/* Time cell */
.c-time {
  display: flex;
  align-items: center;
  gap: 6px;
}

.time-icon {
  width: 13px;
  height: 13px;
  color: var(--text-4);
  flex-shrink: 0;
}

.time-val {
  font-size: 11.5px;
  color: var(--text-3);
  white-space: nowrap;
}

/* Status pill */
.status-pill {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.4px;
  padding: 2px 9px;
  border-radius: 10px;
  white-space: nowrap;
}

.status-pill.pending {
  color: var(--warn);
  background: rgba(245, 158, 11, 0.12);
  border: 1px solid rgba(245, 158, 11, 0.25);
}

.status-pill.approved {
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-border);
}

.status-pill.rejected {
  color: var(--danger-soft);
  background: rgba(239, 68, 68, 0.12);
  border: 1px solid rgba(239, 68, 68, 0.25);
}

/* Actions cell */
.c-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.act-btn {
  flex: 1 1 0;
  min-width: 0;
}

.reviewed-note {
  font-size: 11.5px;
  color: var(--text-4);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.desktop-hidden {
  display: none;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.empty-wrap {
  padding: 48px 0;
  display: flex;
  justify-content: center;
}

/* ── Narrow column / tablet: drop the two secondary columns so the
      status pill and action buttons keep their full width ─────────── */
@container slips (max-width: 1100px) {
  .table-head,
  .table-row {
    grid-template-columns: 170px minmax(90px, 1fr) 76px 88px 190px;
  }

  .c-tx,
  .c-time {
    display: none;
  }
}

/* ── Tight column: each row becomes a compact two-line card ─────── */
@container slips (max-width: 760px) {
  .table-head {
    display: none;
  }

  .slips-table {
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
      "slip amount"
      "slip status"
      "actions actions";
    gap: 6px 10px;
    padding: 12px;
    background: var(--surface);
    border: 1px solid var(--border);
    border-radius: 10px;
  }

  .c-slip { grid-area: slip; align-self: center; }
  .c-amount { grid-area: amount; justify-self: end; }
  .c-status { grid-area: status; justify-self: end; }
  .c-actions { grid-area: actions; }
  .c-customer,
  .c-tx,
  .c-time {
    display: none;
  }

  .slip-thumb {
    width: 44px;
    height: 44px;
  }

  .desktop-hidden {
    display: block;
  }

  .amount-val {
    font-size: 15px;
  }

  .act-btn {
    height: 40px;
  }
}

/* Real mobile / Telegram Mini App: trim the outer padding. */
@media (max-width: 767px) {
  .slips-view {
    padding: 12px;
  }
}

</style>
