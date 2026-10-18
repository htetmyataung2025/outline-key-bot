<script setup lang="ts">
import { computed } from 'vue'
import DialogShell from './ui/DialogShell.vue'
import DemoQr from './ui/DemoQr.vue'
import SvgIcon from './ui/SvgIcon.vue'
import PurchaseHistory from './rewards/PurchaseHistory.vue'
import LeaderboardCard from './rewards/LeaderboardCard.vue'
import ReceiptUpload from './shop/ReceiptUpload.vue'
import { useMiniApp } from '../composables/useMiniApp'
import { formatNumber, percentUsed } from '../utils/format'

const {
  state,
  closeDialog,
  setTab,
  updateKeyUsage,
  purchasePlan,
  submitTopUp,
  requestKeyReplace,
  copyKey,
} = useMiniApp()

const activeKey = computed(() => {
  const dialog = state.dialog
  return dialog && 'keyId' in dialog ? state.keys.find(key => key.id === dialog.keyId) : undefined
})

const activePlan = computed(() => {
  const dialog = state.dialog
  if (dialog && dialog.kind === 'purchase') {
    return state.plans.find(p => p.name === dialog.plan)
  }
  return undefined
})

function selectServer(sid: string) {
  if (state.selectedServerId !== sid) {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    state.selectedServerId = sid
  }
}

const title = computed(() => {
  const d = state.dialog
  if (!d) return ''
  switch (d.kind) {
    case 'usage': return activeKey.value ? `${activeKey.value.plan} Plan · ${activeKey.value.location}` : 'Key details'
    case 'connect': return 'Outline နဲ့ ချိတ်ဆက်ရန်'
    case 'replace': return 'Key အသစ်လဲမလား?'
    case 'key-qr': return 'Key QR Code'
    case 'purchase': return `${d.plan} Plan`
    case 'payment': return `${d.method === 'kbz' ? 'KBZPay' : 'WavePay'} · ${formatNumber(d.amount)} Ks`
    case 'manual-copy': return 'Outline Key'
    case 'profile': return state.user.name
    case 'leaderboard': return 'Leaderboard'
    case 'history': return 'Purchase history'
  }
})

function setUsage(percent: number) {
  const key = activeKey.value
  if (key) {
    closeDialog()
    updateKeyUsage(key.id, (key.quota * percent) / 100)
  }
}

function openOutline() {
  const key = activeKey.value?.key
  if (key) {
    const accessUrl = key.startsWith('ss://') ? key : `ss://${key}`
    copyKey(accessUrl)
    try {
      window.location.href = accessUrl
    } catch {
      // Fallback
    }
  }
  closeDialog()
}

async function handleConfirmPurchase() {
  const plan = activePlan.value
  if (!plan) return
  await purchasePlan(plan.name, state.selectedServerId)
}

function selectField(event: MouseEvent) {
  if (event.target instanceof HTMLInputElement) event.target.select()
}

const currentPaymentInfo = computed(() => {
  if (state.dialog?.kind === 'payment') {
    return state.paymentMethods[state.dialog.method] || {
      name: state.dialog.method === 'kbz' ? 'KBZPay' : 'WavePay',
      account_name: 'Htet Myat Aung',
      phone: '09699970092',
      type: 'Direct Transfer / QR',
    }
  }
  return null
})
</script>

<template>
  <DialogShell :open="state.dialog !== null" :title="title" @close="closeDialog">
    <!-- 1. Key Usage Presets Modal -->
    <template v-if="state.dialog?.kind === 'usage' && activeKey">
      <span class="demo-label">USAGE DETAILS</span>
      <p>ရေမျက်နှာပြင်နဲ့ usage bar အသုံးပြုမှုအခြေအနေ။</p>
      <div class="usage-presets">
        <button
          v-for="n in [0, 29, 65, 100]"
          :key="n"
          class="usage-preset"
          :class="{ active: percentUsed(activeKey) === n }"
          :data-usage-preset="n"
          :aria-pressed="percentUsed(activeKey) === n"
          @click="setUsage(n)"
        >
          {{ n }}%
        </button>
      </div>
      <p class="small-hint">
        <SvgIcon name="info" />လက်ရှိအသုံးပြုမှု · {{ formatNumber(activeKey.used) }} / {{ activeKey.quota }} GB
      </p>
      <button class="soft-btn modal-full-btn" @click="setTab('keys')">
        <SvgIcon name="key" />Key အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" />
      </button>
    </template>

    <!-- 2. Outline Connect Modal -->
    <template v-else-if="state.dialog?.kind === 'connect'">
      <span v-if="activeKey" class="demo-label">{{ activeKey.plan }} Plan · {{ activeKey.server }}</span>
      <p>VPN Key ကို Outline App ထဲသို့ တိုက်ရိုက် Import ပြုလုပ်ပြီး ချိတ်ဆက်နိုင်ပါသည်ခင်ဗျာ။</p>
      <div v-if="activeKey?.key" class="manual-key-box" style="margin-bottom: 12px;">
        <input class="manual-key" :value="activeKey.key" readonly @click="selectField" />
      </div>
      <div class="modal-actions">
        <button class="soft-btn" @click="copyKey(activeKey?.key || '')">
          <SvgIcon name="copy" />Key ကူးယူမည်
        </button>
        <button class="primary-btn" @click="openOutline">
          Outline ဖွင့်ရန်<SvgIcon name="arrow-up-right" />
        </button>
      </div>
    </template>

    <!-- 3. Key Replace Confirmation Modal -->
    <template v-else-if="state.dialog?.kind === 'replace'">
      <span class="demo-label">KEY REPLACEMENT</span>
      <p>လက်ရှိ key အဆင်မပြေပါက ဆာဗာမှ key အသစ် ပြန်လည်လဲလှယ်ထုတ်ယူရန် တင်ပြတောင်းဆိုနိုင်ပါသည်ခင်ဗျာ။</p>
      <div class="modal-actions">
        <button class="soft-btn" :disabled="state.isSubmitting" @click="closeDialog">မလုပ်တော့ပါ</button>
        <button class="primary-btn" :disabled="state.isSubmitting" @click="activeKey && requestKeyReplace(activeKey.id)">
          <SvgIcon name="refresh" />{{ state.isSubmitting ? 'ဆောင်ရွက်နေပါသည်...' : 'ဆက်လုပ်မည်' }}
        </button>
      </div>
    </template>

    <!-- 4. Key QR Code Modal -->
    <template v-else-if="state.dialog?.kind === 'key-qr'">
      <p>အခြားဖုန်း (သို့မဟုတ်) စက်တစ်လုံးမှ Outline App ဖြင့် Scan ဖတ်ပြီး အသုံးပြုနိုင်ပါသည်။</p>
      <DemoQr />
      <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
    </template>

    <!-- 5. 1-Click Plan Purchase Modal -->
    <template v-else-if="state.dialog?.kind === 'purchase'">
      <!-- Live Checkout Flow (when price is configured) -->
      <template v-if="activePlan && activePlan.price !== null">
        <div class="checkout-summary card" style="padding: 12px; margin-bottom: 14px; background: rgba(255,255,255,0.03);">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>ရွေးချယ်ထားသော Plan:</span>
            <b>{{ activePlan.name }} ({{ activePlan.quota }} GB)</b>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>Plan ဈေးနှုန်း:</span>
            <b style="color: #2aefbd;">{{ formatNumber(activePlan.price) }} Ks</b>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>သင့် Wallet လက်ကျန်:</span>
            <b>{{ formatNumber(state.walletBalance) }} Ks</b>
          </div>
        </div>

        <!-- Server Selector -->
        <div style="margin-bottom: 14px;">
          <span class="form-label" style="display: block; margin-bottom: 6px;">ချိတ်ဆက်မည့် Server ရွေးရန်:</span>
          <div style="display: flex; gap: 8px; flex-wrap: wrap;">
            <button
              v-for="srv in state.servers"
              :key="srv.id"
              class="amount-chip"
              :class="{ active: state.selectedServerId === srv.id }"
              type="button"
              @click="selectServer(srv.id)"
            >
              {{ srv.flag }} {{ srv.name }}
            </button>
          </div>
        </div>

        <!-- Sufficient balance -->
        <template v-if="state.walletBalance >= activePlan.price">
          <button
            class="primary-btn modal-full-btn"
            :disabled="state.isSubmitting"
            @click="handleConfirmPurchase"
          >
            <SvgIcon name="zap" />{{ state.isSubmitting ? 'ဝယ်ယူနေပါသည်...' : 'အတည်ပြုပြီး ဝယ်ယူမည်' }}
          </button>
        </template>
        <!-- Insufficient balance -->
        <template v-else>
          <p class="small-hint" style="color: #f87171; margin-bottom: 10px;">
            <SvgIcon name="info" />Wallet လက်ကျန်ငွေ မလုံလောက်ပါခင်ဗျာ (လိုအပ်ငွေ: {{ formatNumber(activePlan.price - state.walletBalance) }} Ks)
          </p>
          <button class="primary-btn modal-full-btn" @click="closeDialog(); setTab('shop')">
            <SvgIcon name="plus" />Wallet သို့ ငွေဖြည့်ရန်
          </button>
        </template>
      </template>

      <!-- Offline / No Price Fallback -->
      <template v-else>
        <span class="demo-label">WALLET · {{ formatNumber(state.walletBalance) }} Ks</span>
        <p>ရွေးချယ်ထားသော Plan အတွက် ဈေးနှုန်း အချက်အလက် မရရှိနိုင်သေးသောကြောင့် ဝယ်ယူ၍မရသေးပါ။ ကျေးဇူးပြု၍ အခြား Plan တစ်ခုကို ရွေးချယ်ပေးပါခင်ဗျာ။</p>
        <button class="primary-btn modal-full-btn" @click="closeDialog">နားလည်ပါပြီ</button>
      </template>
    </template>

    <!-- 6. Payment & Top-Up Modal -->
    <template v-else-if="state.dialog?.kind === 'payment'">
      <div v-if="currentPaymentInfo" class="payment-info-box card" style="padding: 12px; margin-bottom: 12px; text-align: left;">
        <div style="font-size: 13px; color: #94a3b8; margin-bottom: 4px;">{{ currentPaymentInfo.name }} အကောင့်အချက်အလက်:</div>
        <div style="font-size: 16px; font-weight: 700; color: #fff;">{{ currentPaymentInfo.account_name }}</div>
        <div style="display: flex; justify-content: space-between; align-items: center; margin-top: 6px;">
          <span style="font-size: 18px; font-weight: 800; color: #2aefbd;">{{ currentPaymentInfo.phone }}</span>
          <button class="soft-btn" style="padding: 4px 10px; font-size: 12px;" @click="copyKey(currentPaymentInfo.phone)">
            <SvgIcon name="copy" />Copy
          </button>
        </div>
      </div>
      <DemoQr />
      <p class="text-center" style="margin-top: 8px;">ငွေလွှဲပြီးပါက Screenshot ပြေစာကို အောက်တွင် တင်ပေးပါခင်ဗျာ။</p>
      <ReceiptUpload />
      <div class="modal-actions" style="margin-top: 12px;">
        <button class="soft-btn" @click="closeDialog">နောက်မှ</button>
        <button
          class="primary-btn"
          :disabled="!state.receipt || state.isSubmitting"
          @click="submitTopUp"
        >
          <SvgIcon name="upload" />{{ state.isSubmitting ? 'ပေးပို့နေပါသည်...' : 'ပြေစာ တင်မည်' }}
        </button>
      </div>
    </template>

    <!-- 7. Manual Copy Modal -->
    <template v-else-if="state.dialog?.kind === 'manual-copy'">
      <p>Outline Access Key ကို copy ပြုလုပ်ရန်:</p>
      <input class="manual-key" :value="state.dialog.value" readonly aria-label="Key to copy" @click="selectField" />
      <button class="primary-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
    </template>

    <!-- 8. Profile Modal -->
    <template v-else-if="state.dialog?.kind === 'profile'">
      <div class="identity-card card">
        <div class="avatar">{{ state.user.initials }}</div>
        <div class="identity-text">
          <div class="identity-name">{{ state.user.name }}</div>
          <div class="identity-id">Telegram ID · {{ state.user.id }}</div>
        </div>
        <SvgIcon name="diamond" />
      </div>
      <p>Wallet Balance: <b>{{ formatNumber(state.walletBalance) }} Ks</b> · Points: <b>{{ state.points }} PTS</b></p>
      <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
    </template>

    <!-- 9. Leaderboard Modal -->
    <template v-else-if="state.dialog?.kind === 'leaderboard'">
      <LeaderboardCard :interactive="false" />
      <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
    </template>

    <!-- 10. History Modal -->
    <template v-else-if="state.dialog?.kind === 'history'">
      <PurchaseHistory :interactive="false" />
      <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
    </template>
  </DialogShell>
</template>
