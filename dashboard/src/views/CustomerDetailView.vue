<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import { fetchCustomerDetail, adjustBalance, triggerHaptic, triggerHapticNotification } from '@/api'
import { avatarInitial, avatarGradient, displayName } from '@/composables/avatar'
import {
  NButton,
  NSpin,
  NTabs,
  NTabPane,
  NModal,
  NForm,
  NFormItem,
  NInput,
  NInputNumber,
  NRadioGroup,
  NRadioButton,
  NEmpty,
  useMessage,
} from 'naive-ui'
import {
  ArrowBackOutline,
  CashOutline,
  KeyOutline,
  CopyOutline,
  PersonOutline,
  TimeOutline,
} from '@vicons/ionicons5'

const props = defineProps<{ chatId: string }>()
const router = useRouter()
const message = useMessage()

const loading = ref(false)
const detail = ref<any>(null)

const profile = computed(() => detail.value?.profile || {})
const keys = computed(() => detail.value?.keys || [])
const purchases = computed(() => detail.value?.purchases || [])
const slips = computed(() => detail.value?.slips || [])
const redeems = computed(() => detail.value?.redeems || [])
const audit = computed(() => detail.value?.audit || [])

// Adjust modal
const showAdjustModal = ref(false)
const adjustLoading = ref(false)
const adjustForm = ref({
  adjustment_type: 'TOPUP' as 'TOPUP' | 'DEDUCT',
  amount_ks: 5000,
  reason: '',
})

const isDeduct = computed(() => adjustForm.value.adjustment_type === 'DEDUCT')
const currentBalance = computed(() => Number(profile.value.wallet_balance || 0))
// Deduct can never exceed the wallet; Top-Up is uncapped.
const amountMax = computed(() => (isDeduct.value ? currentBalance.value : undefined))
const deductExceeds = computed(
  () => isDeduct.value && Number(adjustForm.value.amount_ks || 0) > currentBalance.value,
)

async function loadDetail(opts?: { silent?: boolean }) {
  const silent = opts?.silent ?? false
  if (!silent) loading.value = true
  try {
    detail.value = await fetchCustomerDetail(props.chatId)
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load customer detail')
  } finally {
    if (!silent) loading.value = false
  }
}

function goBack() {
  triggerHaptic('light')
  router.push('/customers')
}

function fmtDate(value?: string): string {
  if (!value) return '—'
  const dt = new Date(String(value).replace(' ', 'T'))
  if (isNaN(dt.getTime())) return value
  return dt.toLocaleString('en-GB', {
    day: '2-digit',
    month: 'short',
    year: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function copyText(text: string) {
  if (!text) return
  triggerHaptic('light')
  navigator.clipboard.writeText(text)
  message.info('Copied to clipboard')
}

function openAdjustModal() {
  triggerHaptic('light')
  adjustForm.value.adjustment_type = 'TOPUP'
  adjustForm.value.amount_ks = 5000
  adjustForm.value.reason = ''
  showAdjustModal.value = true
}

async function handleAdjustBalance() {
  adjustLoading.value = true
  try {
    const res = await adjustBalance(props.chatId, {
      adjustment_type: adjustForm.value.adjustment_type,
      amount_ks: adjustForm.value.amount_ks,
      reason: adjustForm.value.reason || undefined,
    })
    if (res.success) {
      triggerHapticNotification('success')
      message.success(`Balance updated: ${res.new_balance.toLocaleString()} Ks`)
      showAdjustModal.value = false
      await loadDetail()
    }
  } catch (err: any) {
    triggerHapticNotification('error')
    message.error(err?.response?.data?.error || 'Failed to adjust balance')
  } finally {
    adjustLoading.value = false
  }
}

onMounted(() => {
  loadDetail()
})

defineExpose({ loadData: loadDetail })
</script>

<template>
  <div class="detail-view">
    <button class="back-bar" @click="goBack">
      <ArrowBackOutline class="back-icon" />
      <span>Back to Customers</span>
    </button>

    <NSpin :show="loading">
      <div class="detail-layout">
        <!-- LEFT: account info -->
        <aside class="info-panel">
          <div class="info-head">
            <span class="avatar-lg" :style="{ background: avatarGradient(profile.chat_id || chatId) }">
              {{ avatarInitial(profile.full_name || profile.username, profile.chat_id || chatId) }}
            </span>
            <h2 class="info-name">{{ displayName(profile.full_name, profile.username, profile.chat_id || chatId) }}</h2>
            <span v-if="profile.username" class="info-username">@{{ profile.username }}</span>
            <button class="id-badge font-mono" @click="copyText(String(profile.chat_id || chatId))">
              ID {{ profile.chat_id || chatId }}
              <CopyOutline class="copy-icon" />
            </button>
            <span class="role-tag">Customer</span>
          </div>

          <div class="balance-block">
            <div class="balance-total">
              <span class="bt-label">Total Balance</span>
              <span class="bt-value font-mono">{{ (profile.wallet_balance || 0).toLocaleString() }} <small>MMK</small></span>
            </div>
            <div class="balance-split">
              <div class="split-item">
                <span class="split-label">Main</span>
                <span class="split-val font-mono">{{ (profile.main_balance || 0).toLocaleString() }}</span>
              </div>
              <div class="split-item">
                <span class="split-label">Bonus</span>
                <span class="split-val font-mono">{{ (profile.bonus_balance || 0).toLocaleString() }}</span>
              </div>
            </div>
          </div>

          <div class="info-stats">
            <div class="stat-row">
              <span class="stat-label"><KeyOutline class="stat-icon" /> Active Keys</span>
              <span class="stat-val">{{ profile.keys_count || 0 }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label"><PersonOutline class="stat-icon" /> First Seen</span>
              <span class="stat-val">{{ fmtDate(profile.first_seen) }}</span>
            </div>
            <div class="stat-row">
              <span class="stat-label"><TimeOutline class="stat-icon" /> Last Active</span>
              <span class="stat-val">{{ fmtDate(profile.last_seen) }}</span>
            </div>
          </div>

          <NButton type="primary" block class="adjust-btn" @click="openAdjustModal">
            <template #icon><CashOutline /></template>
            Adjust Balance
          </NButton>
        </aside>

        <!-- RIGHT: tabbed records -->
        <section class="records-panel">
          <NTabs type="line" animated class="rec-tabs">
            <NTabPane name="keys" :tab="`Access Keys (${keys.length})`">
              <div v-if="keys.length" class="rec-scroll">
                <table class="rec-table">
                  <thead>
                    <tr><th>Name</th><th>Server</th><th>Expires</th><th>Key ID</th><th></th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="k in keys" :key="`${k.server}_${k.key_id}`">
                      <td class="rec-strong">{{ k.label || k.name || '—' }}</td>
                      <td>Server {{ k.server }}</td>
                      <td class="font-mono">{{ k.expire_date || 'N/A' }}</td>
                      <td class="font-mono rec-muted">{{ k.key_id }}</td>
                      <td>
                        <NButton v-if="k.access_url" size="tiny" tertiary @click="copyText(k.access_url)">
                          <template #icon><CopyOutline /></template>
                        </NButton>
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <NEmpty v-else description="No access keys for this user" class="rec-empty" />
            </NTabPane>

            <NTabPane name="purchases" :tab="`Purchases (${purchases.length})`">
              <div v-if="purchases.length" class="rec-scroll">
                <table class="rec-table">
                  <thead>
                    <tr><th>Plan</th><th>Data</th><th>Months</th><th>Price</th><th>Expires</th><th>Date</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(p, i) in purchases" :key="i">
                      <td class="rec-strong">{{ p.plan_name || '—' }}</td>
                      <td>{{ p.disp_gb || '—' }}</td>
                      <td>{{ p.months || 1 }}</td>
                      <td class="font-mono">{{ p.price_str || '—' }}</td>
                      <td class="font-mono">{{ p.expire_date || '—' }}</td>
                      <td class="rec-muted">{{ p.timestamp || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <NEmpty v-else description="No purchase history" class="rec-empty" />
            </NTabPane>
            <NTabPane name="slips" :tab="`Payment Slips (${slips.length})`">
              <div v-if="slips.length" class="rec-scroll">
                <table class="rec-table">
                  <thead>
                    <tr><th>Slip ID</th><th>Amount</th><th>Status</th><th>Tx ID</th><th>Submitted</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="s in slips" :key="s.id">
                      <td class="font-mono rec-strong">{{ s.id }}</td>
                      <td class="font-mono rec-amount">+{{ (s.amount || 0).toLocaleString() }}</td>
                      <td><span class="status-pill" :class="String(s.status).toLowerCase()">{{ s.status }}</span></td>
                      <td class="font-mono rec-muted">{{ s.extracted_tx_id || '—' }}</td>
                      <td class="rec-muted">{{ s.created_at || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <NEmpty v-else description="No payment slips" class="rec-empty" />
            </NTabPane>

            <NTabPane name="redeems" :tab="`Redeems (${redeems.length})`">
              <div v-if="redeems.length" class="rec-scroll">
                <table class="rec-table">
                  <thead>
                    <tr><th>Code</th><th>Amount</th><th>Validity</th><th>Mode</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="r in redeems" :key="r.code">
                      <td class="font-mono rec-strong">{{ r.code }}</td>
                      <td class="font-mono rec-amount">+{{ (r.amount || 0).toLocaleString() }}</td>
                      <td>{{ r.valid_days || 0 }} days</td>
                      <td><span class="mode-pill">{{ r.mode }}</span></td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <NEmpty v-else description="No redeemed codes tracked" class="rec-empty" />
            </NTabPane>

            <NTabPane name="audit" :tab="`Audit Log (${audit.length})`">
              <div v-if="audit.length" class="rec-scroll">
                <table class="rec-table">
                  <thead>
                    <tr><th>Action</th><th>Details</th><th>By</th><th>Time</th></tr>
                  </thead>
                  <tbody>
                    <tr v-for="(a, i) in audit" :key="i">
                      <td><span class="action-pill">{{ a.action }}</span></td>
                      <td class="rec-muted rec-details">
                        <template v-if="a.details && a.details.amount">{{ a.details.amount.toLocaleString() }} Ks</template>
                        <template v-if="a.details && a.details.reason"> · {{ a.details.reason }}</template>
                      </td>
                      <td class="font-mono rec-muted">{{ a.admin_id }}</td>
                      <td class="rec-muted">{{ a.timestamp }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
              <NEmpty v-else description="No audit entries" class="rec-empty" />
            </NTabPane>
          </NTabs>
        </section>
      </div>
    </NSpin>

    <NModal
      v-model:show="showAdjustModal"
      preset="card"
      title="Adjust Customer Wallet Balance"
      style="max-width: 440px;"
    >
      <div class="modal-target">
        <span class="modal-target-label">Target: </span>
        <span class="font-mono modal-target-id">{{ profile.chat_id || chatId }}</span>
        <br />
        <span class="modal-target-label">Current Balance: </span>
        <span class="font-mono text-emerald">{{ (profile.wallet_balance || 0).toLocaleString() }} Ks</span>
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
.detail-view {
  padding: 24px;
  container-type: inline-size;
  container-name: detail;
}

.back-bar {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  background: transparent;
  border: none;
  color: var(--text-3);
  font-size: 13px;
  cursor: pointer;
  padding: 4px 0;
  margin-bottom: 16px;
  transition: color 0.12s ease;
}

.back-bar:hover {
  color: var(--accent);
}

.back-icon {
  width: 16px;
  height: 16px;
}

.detail-layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 20px;
  align-items: start;
}

/* ── Left: account info ─────────────────────────────────────────── */
.info-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 24px 20px;
}

.info-head {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 8px;
  padding-bottom: 20px;
  border-bottom: 1px solid var(--border-subtle);
}

.avatar-lg {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 30px;
  font-weight: 700;
  color: #fff;
  text-shadow: 0 1px 3px rgba(0, 0, 0, 0.35);
}

.info-name {
  margin: 4px 0 0;
  font-size: 18px;
  font-weight: 700;
  color: var(--text-1);
  word-break: break-word;
}

.info-username {
  font-size: 13px;
  color: var(--text-4);
}
.id-badge {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-2);
  background: var(--fill-subtle);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 4px 10px;
  cursor: pointer;
  transition: border-color 0.12s ease;
}

.id-badge:hover {
  border-color: var(--border-strong);
}

.copy-icon {
  width: 12px;
  height: 12px;
  color: var(--text-4);
}

.role-tag {
  margin-top: 4px;
  font-size: 11px;
  font-weight: 600;
  color: var(--accent);
  background: var(--accent-soft);
  border: 1px solid var(--accent-soft-border);
  border-radius: 10px;
  padding: 2px 12px;
}

.balance-block {
  padding: 20px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.balance-total {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  margin-bottom: 14px;
}

.bt-label {
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  color: var(--text-4);
}

.bt-value {
  font-size: 26px;
  font-weight: 700;
  color: var(--accent);
}

.bt-value small {
  font-size: 13px;
  color: var(--text-4);
}

.balance-split {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.split-item {
  background: var(--surface-2);
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  padding: 8px 10px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  align-items: center;
}

.split-label {
  font-size: 11px;
  color: var(--text-4);
}

.split-val {
  font-size: 14px;
  font-weight: 600;
  color: var(--text-2);
}
.info-stats {
  padding: 18px 0;
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.stat-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  font-size: 12.5px;
}

.stat-label {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  color: var(--text-3);
}

.stat-icon {
  width: 14px;
  height: 14px;
  color: var(--text-4);
}

.stat-val {
  color: var(--text-1);
  font-weight: 600;
  text-align: right;
}

.adjust-btn {
  margin-top: 4px;
}

/* ── Right: records ─────────────────────────────────────────────── */
.records-panel {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 8px 20px 20px;
  min-width: 0;
}

.rec-scroll {
  overflow-x: auto;
  max-height: 560px;
  overflow-y: auto;
}

.rec-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 13px;
}

.rec-table thead th {
  position: sticky;
  top: 0;
  background: var(--surface);
  text-align: left;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.4px;
  text-transform: uppercase;
  color: var(--text-4);
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}

.rec-table tbody td {
  padding: 11px 12px;
  border-bottom: 1px solid var(--border-subtle);
  color: var(--text-2);
  white-space: nowrap;
}

.rec-table tbody tr:hover {
  background: var(--fill-subtle);
}

.rec-strong {
  color: var(--text-1);
  font-weight: 600;
}

.rec-muted {
  color: var(--text-4);
}

.rec-amount {
  color: var(--accent);
  font-weight: 700;
}

.rec-details {
  white-space: normal;
  min-width: 160px;
}

.rec-empty {
  padding: 40px 0;
}
.status-pill,
.mode-pill,
.action-pill {
  display: inline-block;
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.3px;
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

.mode-pill,
.action-pill {
  color: var(--text-2);
  background: var(--fill-subtle);
  border: 1px solid var(--border);
  text-transform: none;
  font-family: 'JetBrains Mono', monospace;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.text-emerald {
  color: var(--accent);
  font-weight: 600;
}

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

/* ── Mobile: stack panels, trim padding ─────────────────────────── */
@container detail (max-width: 860px) {
  .detail-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 767px) {
  .detail-view {
    padding: 12px;
  }

  .info-panel {
    padding: 20px 16px;
  }

  .records-panel {
    padding: 4px 12px 16px;
  }

  .rec-tabs :deep(.n-tabs-nav) {
    overflow-x: auto;
  }
}
</style>

