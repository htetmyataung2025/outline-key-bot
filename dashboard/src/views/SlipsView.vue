<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  fetchSlips,
  reviewSlip,
  triggerHaptic,
  triggerHapticNotification,
} from '@/api'
import {
  NCard,
  NGrid,
  NGridItem,
  NTabs,
  NTabPane,
  NTag,
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
  ImageOutline,
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

async function loadSlips() {
  loading.value = true
  try {
    slips.value = await fetchSlips(currentTab.value)
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load slips queue')
  } finally {
    loading.value = false
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

function viewImage(url: string) {
  selectedImageUrl.value = url || 'https://placehold.co/600x800/1e293b/10b981?text=Slip+Preview'
  showImageModal.value = true
}

onMounted(() => {
  loadSlips()
})
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
      <div v-if="slips.length > 0" class="slips-grid-wrap">
        <NGrid cols="1 s:2 m:3 l:4" :x-gap="16" :y-gap="16">
          <NGridItem v-for="slip in slips" :key="slip.id">
            <NCard class="slip-card" hoverable>
              <div class="slip-header">
                <span class="slip-id font-mono">#{{ slip.id }}</span>
                <NTag
                  :type="
                    slip.status === 'APPROVED'
                      ? 'success'
                      : slip.status === 'REJECTED'
                      ? 'error'
                      : 'warning'
                  "
                  size="small"
                  round
                >
                  {{ slip.status }}
                </NTag>
              </div>

              <!-- Slip Image Thumbnail / Lightbox trigger -->
              <div class="slip-preview" @click="viewImage(slip.image_url)">
                <div class="preview-overlay">
                  <ImageOutline class="zoom-icon" />
                  <span>Inspect Slip</span>
                </div>
                <img
                  :src="slip.image_url || 'https://placehold.co/400x300/1e293b/334155?text=Receipt+Photo'"
                  alt="Receipt"
                  class="preview-img"
                  loading="lazy"
                />
              </div>

              <!-- Slip Details -->
              <div class="slip-info">
                <div class="info-row">
                  <span class="info-label">Customer:</span>
                  <span class="info-val">{{ slip.username }}</span>
                </div>

                <div class="info-row">
                  <span class="info-label">Chat ID:</span>
                  <span class="info-val font-mono">{{ slip.chat_id }}</span>
                </div>

                <div class="info-row highlight-amount">
                  <span class="info-label">Amount:</span>
                  <span class="amount-val font-mono">+{{ slip.amount.toLocaleString() }} MMK</span>
                </div>

                <div v-if="slip.extracted_tx_id" class="info-row">
                  <span class="info-label">Tx ID (OCR):</span>
                  <NTag size="tiny" type="info" class="font-mono">
                    {{ slip.extracted_tx_id }}
                  </NTag>
                </div>

                <div class="info-row time-row">
                  <TimeOutline class="time-icon" />
                  <span class="time-val">{{ slip.created_at }}</span>
                </div>
              </div>

              <!-- Actions (Only for Pending) -->
              <div v-if="slip.status === 'PENDING'" class="slip-actions">
                <NButton
                  type="primary"
                  block
                  :loading="actionLoading"
                  @click="handleApprove(slip)"
                >
                  <template #icon>
                    <CheckmarkCircleOutline />
                  </template>
                  Approve (+{{ slip.amount.toLocaleString() }} Ks)
                </NButton>

                <NButton
                  type="error"
                  ghost
                  block
                  :loading="actionLoading"
                  @click="openRejectPrompt(slip.id)"
                >
                  <template #icon>
                    <CloseCircleOutline />
                  </template>
                  Reject
                </NButton>
              </div>

              <!-- Status Info for Approved/Rejected -->
              <div v-else class="reviewed-info">
                <span class="reviewed-text">
                  Reviewed by {{ slip.reviewed_by || 'Admin' }}
                </span>
                <span v-if="slip.review_reason" class="reason-text">
                  "{{ slip.review_reason }}"
                </span>
              </div>
            </NCard>
          </NGridItem>
        </NGrid>
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
        <div style="display: flex; justify-content: center;">
          <img
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

.slip-card {
  display: flex;
  flex-direction: column;
}

.slip-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.slip-id {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-2);
}

.slip-preview {
  position: relative;
  width: 100%;
  height: 160px;
  border-radius: 8px;
  overflow: hidden;
  cursor: pointer;
  background: var(--surface-2);
  border: 1px solid var(--border);
  margin-bottom: 12px;
}

.preview-img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  transition: transform 0.2s ease;
}

.preview-overlay {
  position: absolute;
  inset: 0;
  background: rgba(15, 23, 42, 0.7);
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 6px;
  color: var(--text-1);
  font-size: 12px;
  opacity: 0;
  transition: opacity 0.2s ease;
  z-index: 2;
}

.slip-preview:hover .preview-overlay {
  opacity: 1;
}

.slip-preview:hover .preview-img {
  transform: scale(1.05);
}

.zoom-icon {
  width: 24px;
  height: 24px;
}

.slip-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}

.info-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-size: 13px;
}

.info-label {
  color: var(--text-3);
}

.info-val {
  color: var(--text-1);
  font-weight: 500;
}

.highlight-amount {
  background: rgba(16, 185, 129, 0.1);
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid rgba(16, 185, 129, 0.2);
}

.amount-val {
  color: var(--accent);
  font-weight: 700;
  font-size: 14px;
}

.time-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
}

.time-icon {
  width: 14px;
  height: 14px;
  color: var(--text-4);
}

.time-val {
  font-size: 11px;
  color: var(--text-4);
}

.slip-actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.reviewed-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 8px;
  background: var(--surface-2);
  border-radius: 6px;
  font-size: 11px;
}

.reviewed-text {
  color: var(--text-3);
}

.reason-text {
  color: var(--text-2);
  font-style: italic;
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
