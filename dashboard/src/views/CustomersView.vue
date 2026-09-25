<script setup lang="ts">
import { ref, onMounted, computed } from 'vue'
import { fetchCustomers, adjustBalance, triggerHaptic, triggerHapticNotification } from '@/api'
import {
  NCard,
  NInput,
  NButton,
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
import { SearchOutline, WalletOutline, CashOutline } from '@vicons/ionicons5'

const message = useMessage()

const loading = ref(false)
const customers = ref<any[]>([])
const search = ref('')

// Balance adjust modal
const showAdjustModal = ref(false)
const adjustLoading = ref(false)
const selectedCustomer = ref<any>(null)
const adjustForm = ref({
  adjustment_type: 'TOPUP' as 'TOPUP' | 'DEDUCT',
  amount_ks: 5000,
  reason: '',
})

async function loadCustomers() {
  loading.value = true
  try {
    const res = await fetchCustomers()
    customers.value = res.customers || []
  } catch (err: any) {
    message.error(err?.response?.data?.error || 'Failed to load customers')
  } finally {
    loading.value = false
  }
}

const filteredCustomers = computed(() => {
  if (!search.value) return customers.value
  const q = search.value.trim()
  return customers.value.filter((c) => String(c.chat_id).includes(q))
})

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
        `Updated balance for user ${selectedCustomer.value.chat_id}: ${res.new_balance.toLocaleString()} Ks`
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
</script>

<template>
  <div class="customers-view">
    <div class="view-header">
      <div>
        <h1 class="page-title">Customer Wallets</h1>
        <p class="page-subtitle">Inspect user balances and perform administrative adjustments</p>
      </div>
    </div>

    <!-- Search Bar -->
    <NCard class="filter-card">
      <NInput
        v-model:value="search"
        placeholder="Filter by Telegram Chat ID..."
        clearable
        class="search-input"
      >
        <template #prefix>
          <SearchOutline />
        </template>
      </NInput>
    </NCard>

    <NSpin :show="loading">
      <div v-if="filteredCustomers.length > 0" class="customers-grid">
        <div v-for="c in filteredCustomers" :key="c.chat_id" class="customer-card">
          <div class="customer-main">
            <div class="chat-id-wrap">
              <span class="user-label">Chat ID:</span>
              <span class="user-val font-mono">{{ c.chat_id }}</span>
            </div>

            <div class="wallet-wrap">
              <WalletOutline class="wallet-icon" />
              <span class="balance-val font-mono">
                {{ (c.wallet_balance || 0).toLocaleString() }} MMK
              </span>
            </div>
          </div>

          <div class="customer-actions">
            <NButton size="small" type="primary" secondary @click="openAdjustModal(c)">
              <template #icon>
                <CashOutline />
              </template>
              Adjust Balance
            </NButton>
          </div>
        </div>
      </div>

      <div v-else class="empty-wrap">
        <NEmpty description="No customers matching search" />
      </div>
    </NSpin>

    <!-- Balance Adjustment Modal -->
    <NModal
      v-model:show="showAdjustModal"
      preset="card"
      title="Adjust Customer Wallet Balance"
      style="max-width: 440px;"
    >
      <div v-if="selectedCustomer" style="margin-bottom: 16px;">
        <span style="color: #94a3b8; font-size: 13px;">Target Chat ID: </span>
        <span class="font-mono" style="color: #f8fafc; font-weight: 600;">
          {{ selectedCustomer.chat_id }}
        </span>
        <br />
        <span style="color: #94a3b8; font-size: 13px;">Current Balance: </span>
        <span class="font-mono text-emerald" style="font-weight: 600;">
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
          <NInputNumber v-model:value="adjustForm.amount_ks" :step="1000" :min="100" />
        </NFormItem>

        <NFormItem label="Reason">
          <NInput v-model:value="adjustForm.reason" placeholder="e.g. Compensation bonus" />
        </NFormItem>

        <div style="display: flex; justify-content: flex-end; gap: 10px; margin-top: 16px;">
          <NButton @click="showAdjustModal = false">Cancel</NButton>
          <NButton type="primary" :loading="adjustLoading" @click="handleAdjustBalance">
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
}

.view-header {
  margin-bottom: 20px;
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

.filter-card {
  margin-bottom: 20px;
  background: #0f172a;
}

.customers-grid {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.customer-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 10px;
  padding: 16px;
  display: flex;
  justify-content: space-between;
  align-items: center;
  flex-wrap: wrap;
  gap: 16px;
}

.customer-main {
  display: flex;
  align-items: center;
  gap: 24px;
  flex-wrap: wrap;
}

.chat-id-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
}

.user-label {
  color: #94a3b8;
  font-size: 13px;
}

.user-val {
  color: #f8fafc;
  font-weight: 600;
  font-size: 14px;
}

.wallet-wrap {
  display: flex;
  align-items: center;
  gap: 8px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.2);
  padding: 4px 10px;
  border-radius: 6px;
}

.wallet-icon {
  width: 16px;
  height: 16px;
  color: #10b981;
}

.balance-val {
  color: #10b981;
  font-weight: 700;
  font-size: 14px;
}

.font-mono {
  font-family: 'JetBrains Mono', monospace;
}

.text-emerald {
  color: #10b981;
}

.empty-wrap {
  padding: 48px 0;
  display: flex;
  justify-content: center;
}
</style>
