<script setup lang="ts">
import { computed, onScopeDispose, ref, watch } from 'vue'
import DialogShell from './ui/DialogShell.vue'
import SvgIcon from './ui/SvgIcon.vue'
import VpnAppLogo from './ui/VpnAppLogo.vue'
import PurchaseHistory from './rewards/PurchaseHistory.vue'
import LeaderboardCard from './rewards/LeaderboardCard.vue'
import ReceiptUpload from './shop/ReceiptUpload.vue'
import { useMiniApp } from '../composables/useMiniApp'
import { formatNumber } from '../utils/format'
import type { VpnAppId, VpnKey } from '../types'

const {
  state,
  openDialog,
  closeDialog,
  setTab,
  purchasePlan,
  submitTopUp,
  requestKeyReplace,
  copyKey,
  openVpnApp,
} = useMiniApp()

const VPN_APPS: Array<{ id: VpnAppId; name: string; badge: string; hint: string }> = [
  { id: 'outline', name: 'Outline', badge: 'Official', hint: 'ss:// Key ကို တိုက်ရိုက် ချိတ်ဆက်မည်' },
  { id: 'v2box', name: 'V2Box', badge: 'iOS · Android', hint: 'V2Box App ထဲသို့ Auto Import ထည့်မည်' },
  { id: 'incy', name: 'INCY', badge: 'Multi-Client', hint: 'INCY App ထဲသို့ Auto Import ထည့်မည်' },
]

const activeKey = computed(() => {
  const dialog = state.dialog
  return dialog && 'keyId' in dialog ? state.keys.find(key => key.id === dialog.keyId) : undefined
})

const activePlan = computed(() => {
  const dialog = state.dialog
  if (dialog && dialog.kind === 'purchase') {
    const target = dialog.plan
    return state.plans.find(p =>
      p.name === target ||
      (p.code && p.code.toLowerCase() === target.toLowerCase()) ||
      p.name.toLowerCase().startsWith(target.toLowerCase())
    )
  }
  return undefined
})

function selectServer(sid: string) {
  if (state.selectedServerId !== sid) {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    state.selectedServerId = sid
  }
}

const PAYMENT_NAMES: Record<string, string> = {
  kbz: 'KBZPay',
  wave: 'WavePay',
  aya: 'AYA Pay',
  uab: 'uab pay',
  cb: 'CB Pay',
}

const title = computed(() => {
  const d = state.dialog
  if (!d) return ''
  switch (d.kind) {
    case 'usage': return activeKey.value ? `${activeKey.value.plan} Plan · ${activeKey.value.location}` : 'Key details'
    case 'connect': return 'ကိုယ်နဲ့ အဆင်ပြေတဲ့ VPN နဲ့ ချိတ်ဆက်ရန်'
    case 'replace': return 'Key အသစ်လဲမလား?'
    case 'key-qr': return 'ကိုယ်နဲ့ အဆင်ပြေတဲ့ VPN နဲ့ ချိတ်ဆက်ရန်'
    case 'purchase': return d.plan.toLowerCase().includes('plan') ? d.plan : `${d.plan} Plan`
    case 'payment': return `${state.paymentMethods[d.method]?.name || PAYMENT_NAMES[d.method] || 'KBZPay'} · ${formatNumber(d.amount)} Ks`
    case 'claim-reward': return d.status === 'loading' ? 'Daily Points Claim' : '🎉 ဆုလက်ဆောင် ရရှိပါသည်!'
    case 'manual-copy': return 'VPN Access Key'
    case 'profile': return state.user.name
    case 'leaderboard': return 'Leaderboard'
    case 'history': return 'Purchase history'
  }
})

function handleOpenVpnApp(appId: VpnAppId, keyObj?: VpnKey) {
  openVpnApp(appId, keyObj?.key, keyObj?.go_url)
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
    const m = state.dialog.method
    return state.paymentMethods[m] || {
      name: PAYMENT_NAMES[m] || 'KBZPay',
      account_name: 'Htet Myat Aung',
      phone: state.paymentMethods.kbz?.phone || '09699970092',
      type: 'Direct Transfer / QR',
    }
  }
  return null
})

// Smooth count-up for the Daily Reward reveal modal
const shownAward = ref(0)
let awardFrame = 0
watch(
  () => (state.dialog?.kind === 'claim-reward' ? `${state.dialog.status}:${state.dialog.awarded ?? 0}` : ''),
  () => {
    cancelAnimationFrame(awardFrame)
    if (state.dialog?.kind !== 'claim-reward' || state.dialog.status !== 'success') {
      shownAward.value = 0
      return
    }
    const target = state.dialog.awarded ?? 0
    const prefersReduced = typeof window !== 'undefined' && window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (prefersReduced || target <= 0) {
      shownAward.value = target
      return
    }
    const started = performance.now()
    const tick = (now: number) => {
      const t = Math.min(1, (now - started) / 600)
      shownAward.value = Math.round(target * (1 - Math.pow(1 - t, 3)))
      if (t < 1) awardFrame = requestAnimationFrame(tick)
      else shownAward.value = target
    }
    awardFrame = requestAnimationFrame(tick)
  },
)
onScopeDispose(() => cancelAnimationFrame(awardFrame))
</script>

<template>
  <DialogShell :open="state.dialog !== null" :title="title" @close="closeDialog">
    <!-- 1. Key Usage Details Modal -->
    <template v-if="state.dialog?.kind === 'usage' && activeKey">
      <span class="badge-pill">{{ activeKey.plan }} Plan · {{ activeKey.location }}</span>
      <p>အသုံးပြုခွင့် Data ပမာဏနှင့် သက်တမ်းကုန်ဆုံးမည့် အချက်အလက်များ။</p>
      <div class="checkout-summary card" style="padding: 12px; margin-bottom: 12px; background: rgba(255,255,255,0.03); font-size: 13px;">
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
          <span style="color: #94a3b8;">ဆာဗာ:</span>
          <b>{{ activeKey.server }} ({{ activeKey.location }})</b>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
          <span style="color: #94a3b8;">စုစုပေါင်း Data:</span>
          <b>{{ activeKey.quota > 0 ? `${activeKey.quota} GB` : 'Unlimited' }}</b>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
          <span style="color: #94a3b8;">အသုံးပြုပြီး:</span>
          <b style="color: #2aefbd;">{{ formatNumber(activeKey.used) }} GB</b>
        </div>
        <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
          <span style="color: #94a3b8;">လက်ကျန် Data:</span>
          <b>{{ activeKey.quota > 0 ? `${formatNumber(Math.max(0, activeKey.quota - activeKey.used))} GB` : 'Unlimited' }}</b>
        </div>
        <div style="display: flex; justify-content: space-between;">
          <span style="color: #94a3b8;">သက်တမ်း:</span>
          <b>{{ activeKey.expires }} ({{ activeKey.left }})</b>
        </div>
      </div>
      <div style="display: flex; gap: 8px; margin-top: 10px;">
        <button class="soft-btn" style="flex: 1;" @click="copyKey(activeKey.key)">
          <SvgIcon name="copy" />Key ကူးယူမည်
        </button>
        <button class="primary-btn" style="flex: 1;" @click="openDialog({ kind: 'connect', keyId: activeKey.id })">
          <SvgIcon name="zap" />Available VPN
        </button>
      </div>
      <button class="soft-btn modal-full-btn" style="margin-top: 8px;" @click="closeDialog(); setTab('keys')">
        <SvgIcon name="key" />Key အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" />
      </button>
    </template>

    <!-- 2. Multi-VPN Available Apps Connect Modal -->
    <template v-else-if="state.dialog?.kind === 'connect' || state.dialog?.kind === 'key-qr'">
      <span v-if="activeKey" class="badge-pill">{{ activeKey.plan }} Plan · {{ activeKey.server }}</span>
      <p>အောက်ပါ VPN App များထဲမှ မိမိနှင့် အဆင်ပြေရာ App ကို နှိပ်၍ Key ကို အလိုအလျောက် ထည့်သွင်းချိတ်ဆက်နိုင်ပါသည်ခင်ဗျာ။</p>
      <div v-if="activeKey?.key" class="connect-key-row">
        <input class="manual-key" :value="activeKey.key" readonly aria-label="VPN Access Key" @click="selectField" />
        <button type="button" class="soft-btn connect-copy-btn" @click="copyKey(activeKey.key)">
          <SvgIcon name="copy" />Copy
        </button>
      </div>
      <div class="vpn-app-list">
        <button
          v-for="app in VPN_APPS"
          :key="app.id"
          type="button"
          class="vpn-app-card"
          :class="`is-${app.id}`"
          :data-vpn-app="app.id"
          @click="handleOpenVpnApp(app.id, activeKey)"
        >
          <VpnAppLogo :app="app.id" />
          <span class="vpn-app-info">
            <span class="vpn-app-head">
              <strong>{{ app.name }}</strong>
              <span class="vpn-app-tag">{{ app.badge }}</span>
            </span>
            <small>{{ app.hint }}</small>
          </span>
          <span class="vpn-app-go">
            <span>ဖွင့်ရန်</span>
            <SvgIcon name="arrow-up-right" />
          </span>
        </button>
      </div>
      <div class="modal-footer">
        <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
      </div>
    </template>

    <!-- 3. Key Replace Confirmation Modal -->
    <template v-else-if="state.dialog?.kind === 'replace'">
      <span class="badge-pill">KEY REPLACEMENT</span>
      <p>လက်ရှိ key အဆင်မပြေပါက ဆာဗာမှ key အသစ် ပြန်လည်လဲလှယ်ထုတ်ယူရန် တင်ပြတောင်းဆိုနိုင်ပါသည်ခင်ဗျာ။</p>
      <div class="modal-actions">
        <button class="soft-btn" :disabled="state.isSubmitting" @click="closeDialog">မလုပ်တော့ပါ</button>
        <button class="primary-btn" :disabled="state.isSubmitting" @click="activeKey && requestKeyReplace(activeKey.id)">
          <SvgIcon name="refresh" />{{ state.isSubmitting ? 'ဆောင်ရွက်နေပါသည်...' : 'ဆက်လုပ်မည်' }}
        </button>
      </div>
    </template>

    <!-- 5. 1-Click Plan Purchase Modal -->
    <template v-else-if="state.dialog?.kind === 'purchase'">
      <!-- Live Checkout Flow (when price is configured) -->
      <template v-if="activePlan && activePlan.price !== null">
        <div class="checkout-summary card" style="padding: 12px; margin-bottom: 14px; background: rgba(255,255,255,0.03);">
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>ရွေးချယ်ထားသော Plan:</span>
            <b>{{ activePlan.name }} ({{ activePlan.quotaLabel || (activePlan.quota ? `${activePlan.quota} GB` : 'Unlimited') }})</b>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>Plan ဈေးနှုန်း:</span>
            <b style="color: #2aefbd;">{{ formatNumber(activePlan.price) }} Ks</b>
          </div>
          <div style="display: flex; justify-content: space-between; margin-bottom: 8px;">
            <span>သင့် Wallet လက်ကျန်:</span>
            <b>{{ state.walletUnlimited ? 'Unlimited' : formatNumber(state.walletBalance) + ' Ks' }}</b>
          </div>
        </div>

        <!-- Manual Custom 5-Device Notice or Server Selector -->
        <div v-if="activePlan.manual" class="card" style="padding: 12px; margin-bottom: 14px; background: rgba(59, 130, 246, 0.1); border: 1px solid rgba(59, 130, 246, 0.3); font-size: 13px;">
          <p style="margin: 0; color: #93c5fd;">
            💡 ဤ Plan သည် စိတ်ကြိုက်သုံး 5 Device Plan ဖြစ်သဖြင့် ဝယ်ယူပြီးပါက Admin မှ ခေတ္တအတွင်း Key အား ပြင်ဆင်၍ Telegram Chat တွင် ပို့ဆောင်ပေးပါမည်ခင်ဗျာ။
          </p>
        </div>
        <div v-else style="margin-bottom: 14px;">
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
        <template v-if="state.walletUnlimited || state.walletBalance >= activePlan.price">
          <button
            class="primary-btn modal-full-btn"
            :disabled="state.isSubmitting"
            @click="handleConfirmPurchase"
          >
            <SvgIcon name="zap" />{{ state.isSubmitting ? 'ဝယ်ယူနေပါသည်...' : (activePlan.manual ? 'အတည်ပြုပြီး မှာယူမည်' : 'အတည်ပြုပြီး ဝယ်ယူမည်') }}
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
        <span class="badge-pill">WALLET · {{ state.walletUnlimited ? 'Unlimited' : formatNumber(state.walletBalance) + ' Ks' }}</span>
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
            <SvgIcon name="copy" />Copy Number
          </button>
        </div>
      </div>
      <p class="text-center" style="margin-top: 4px; font-size: 12px; color: #94a3b8;">အထက်ပါ ဖုန်းနံပါတ်သို့ တိုက်ရိုက် ငွေလွှဲပေးပါရန်။ ငွေလွှဲပြီးပါက Screenshot ပြေစာကို အောက်တွင် တင်ပေးပါခင်ဗျာ။</p>
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

    <!-- 7. Daily Reward Suspense & Reveal Modal -->
    <template v-else-if="state.dialog?.kind === 'claim-reward'">
      <div v-if="state.dialog.status === 'loading'" class="claim-modal-stage" data-claim-stage="loading">
        <div class="claim-spinner-wrap">
          <progress aria-label="Points ဆုလက်ဆောင် ဖွင့်လှစ်နေပါသည်" class="claim-spinner" />
          <span class="claim-spinner-icon" aria-hidden="true"><SvgIcon name="gift" /></span>
        </div>
        <div class="claim-stage-title">Points ဆုမဲ ဖွင့်လှစ်နေပါသည်...</div>
        <p class="claim-stage-sub">သင့်အတွက် ယနေ့ Points ဆုလက်ဆောင်ကို တွက်ချက်နေပါသည်</p>
      </div>
      <div v-else class="claim-modal-stage is-revealed" data-claim-stage="success">
        <div class="claim-reveal-badge">
          <SvgIcon :name="state.dialog.isStreakBonus ? 'flame' : 'sparkles'" />
          <span>{{ state.dialog.isStreakBonus ? `Day ${state.dialog.streakDays} Streak Bonus!` : `${state.dialog.streakDays || 1} Day Streak` }}</span>
        </div>
        <div class="claim-reveal-points">+{{ formatNumber(shownAward) }} <small>PTS</small></div>
        <p class="claim-stage-sub">{{ state.dialog.message || 'နေ့စဉ် Points ဆုလက်ဆောင် ရရှိပြီးပါပြီ!' }}</p>
        <div class="claim-summary-box">
          <div>
            <span>စုစုပေါင်း Points</span>
            <b>{{ formatNumber(state.dialog.newBalance ?? state.points) }} PTS</b>
          </div>
          <div>
            <span>နောက် Claim</span>
            <b>{{ state.dialog.cooldownHours ?? state.cooldownHours }} နာရီတစ်ကြိမ်</b>
          </div>
        </div>
        <button class="primary-btn modal-full-btn" @click="closeDialog">
          <SvgIcon name="check" />သိမ်းဆည်းမည်
        </button>
      </div>
    </template>

    <!-- 8. Manual Copy Modal -->
    <template v-else-if="state.dialog?.kind === 'manual-copy'">
      <p>VPN Access Key ကို copy ပြုလုပ်ရန်:</p>
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
      <p>Wallet Balance: <b>{{ state.walletUnlimited ? 'Unlimited' : formatNumber(state.walletBalance) + ' Ks' }}</b> · Points: <b>{{ state.points }} PTS</b></p>
      <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
    </template>

    <!-- 9. Leaderboard Modal -->
    <template v-else-if="state.dialog?.kind === 'leaderboard'">
      <LeaderboardCard :interactive="false" :in-dialog="true" />
      <div class="modal-footer">
        <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
      </div>
    </template>

    <!-- 10. History Modal -->
    <template v-else-if="state.dialog?.kind === 'history'">
      <PurchaseHistory :interactive="false" :in-dialog="true" />
      <div class="modal-footer">
        <button class="soft-btn modal-full-btn" @click="closeDialog">ပိတ်ရန်</button>
      </div>
    </template>
  </DialogShell>
</template>
