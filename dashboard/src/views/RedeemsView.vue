<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { fetchRedeems, createRedeemBatch, triggerHaptic, triggerHapticNotification } from '@/api'
import {
  NCard,
  NButton,
  NTag,
  NModal,
  NForm,
  NFormItem,
  NInputNumber,
  NRadioGroup,
  NRadioButton,
  NSpin,
  NEmpty,
  useMessage,
} from 'naive-ui'
import { AddOutline, CopyOutline } from '@vicons/ionicons5'


const message = useMessage()

const loading = ref(false)
const redeemsList = ref<any[]>([])

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

async function loadRedeems() {
  loading.value = true
  try {
    redeemsList.value = await fetchRedeems()
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load redeem codes')
  } finally {
    loading.value = false
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

    <!-- Codes Grid / List -->
    <NSpin :show="loading">
      <div v-if="redeemsList.length > 0" class="redeems-grid">
        <NCard v-for="r in redeemsList" :key="r.code" class="code-card" hoverable>
          <div class="code-header">
            <span class="code-val font-mono">{{ r.code }}</span>
            <NTag :type="r.mode === 'single' ? 'info' : 'warning'" size="small" round>
              {{ r.mode === 'single' ? 'Single Use' : 'Shared' }}
            </NTag>
          </div>

          <div class="code-body">
            <div class="val-row">
              <span class="val-label">Credit:</span>
              <span class="val-amount font-mono">+{{ (r.amount || 0).toLocaleString() }} Ks</span>
            </div>
            <div class="val-row">
              <span class="val-label">Expires:</span>
              <span class="val-exp font-mono">{{ r.expires_at || 'Never' }}</span>
            </div>
          </div>

          <div class="code-footer">
            <NButton size="small" secondary block @click="copyCode(r.code)">
              <template #icon>
                <CopyOutline />
              </template>
              Copy Code
            </NButton>
          </div>
        </NCard>
      </div>

      <div v-else class="empty-wrap">
        <NEmpty description="No active redeem codes found" />
      </div>
    </NSpin>

    <!-- Batch Gen Modal -->
    <NModal
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
    <NModal
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

.code-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
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
