<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import ScreenHeading from '../components/ui/ScreenHeading.vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import PaymentLogo from '../components/ui/PaymentLogo.vue'
import PlanCard from '../components/shop/PlanCard.vue'
import ReceiptUpload from '../components/shop/ReceiptUpload.vue'
import { useMiniApp } from '../composables/useMiniApp'
import { plans as defaultPlans } from '../data/demo'
import { formatNumber } from '../utils/format'
import type { PaymentMethod, PlanName, TopUpAmount } from '../types'

const { state, amountLabel, openDialog, showPayment, submitTopUp, redeemCode, copyKey } = useMiniApp()
const amounts: TopUpAmount[] = [1000, 2000, 5000, 'custom']
const paymentOptions: Array<{ id: PaymentMethod; label: string }> = [
  { id: 'kbz', label: 'KBZPay' },
  { id: 'wave', label: 'WavePay' },
  { id: 'aya', label: 'AYA Pay' },
  { id: 'uab', label: 'uab pay' },
  { id: 'cb', label: 'CB Pay' },
]
const customInput = ref<HTMLInputElement | null>(null)
const promoCodeInput = ref('')

const currentPayment = computed(() => {
  const fallbackLabel = paymentOptions.find(p => p.id === state.paymentMethod)?.label || 'KBZPay'
  return state.paymentMethods[state.paymentMethod] || {
    name: fallbackLabel,
    account_name: 'Htet Myat Aung',
    phone: state.paymentMethods.kbz?.phone || '09699970092',
    type: 'Direct Transfer',
  }
})

async function handleRedeemCode() {
  const code = promoCodeInput.value.trim()
  if (!code) return
  const ok = await redeemCode(code)
  if (ok) {
    promoCodeInput.value = ''
  }
}

const activePlans = computed(() => {
  return state.plans && state.plans.length > 0 ? state.plans : defaultPlans
})

const plansExpanded = ref(false)
const hasExtraPlans = computed(() => activePlans.value.length > 6)
const hiddenPlans = computed(() => activePlans.value.slice(6))
const basePlans = computed(() => (hasExtraPlans.value ? activePlans.value.slice(0, 6) : activePlans.value))
const extraPlans = computed(() => (hasExtraPlans.value ? activePlans.value.slice(6) : []))

const plansToggleLabel = computed(() => {
  if (plansExpanded.value) return 'Plan များ ပြန်သိမ်းရန်'
  const firstHidden = hiddenPlans.value[0]
  if (hiddenPlans.value.length === 1 && firstHidden) {
    const quotaText = firstHidden.quotaLabel || (firstHidden.quota ? `${firstHidden.quota} GB` : 'Unlimited')
    return `နောက်ထပ် Plan · ${firstHidden.name} (${quotaText})`
  }
  return `နောက်ထပ် Plan ${hiddenPlans.value.length} ခု ထပ်ကြည့်ရန်`
})

function togglePlansExpand() {
  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  plansExpanded.value = !plansExpanded.value
}

function scrollToTopUp() {
  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  document.getElementById('wallet-topup-card')?.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

watch(() => activePlans.value.length, len => {
  if (len <= 6) plansExpanded.value = false
})

const selectedPlanObj = computed(() => {
  const target = state.selectedPlan
  return activePlans.value.find(p =>
    p.name === target ||
    (p.code && p.code.toLowerCase() === target.toLowerCase()) ||
    p.name.toLowerCase().startsWith(target.toLowerCase())
  )
})

const selectedPlanCta = computed(() => {
  const plan = selectedPlanObj.value
  if (!plan) return 'Wallet ဖြင့် 1-click ဝယ်ယူရန်'
  const label = plan.name.toLowerCase().includes('plan') ? plan.name : `${plan.name} Plan`
  return plan.price !== null ? `${label} ဝယ်ယူရန် · ${formatNumber(plan.price)} Ks` : `${label} ဝယ်ယူရန်`
})

function choosePlan(planName: PlanName) {
  if (state.selectedPlan !== planName) {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    state.selectedPlan = planName
  }
}

async function chooseAmount(amount: TopUpAmount) {
  if (state.selectedAmount !== amount) {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
  }
  state.selectedAmount = amount
  if (amount === 'custom') {
    await nextTick()
    customInput.value?.focus()
  }
}

function setCustomAmount(event: Event) {
  const input = event.target as HTMLInputElement
  // Convert Myanmar digits (၀-၉) to ASCII (0-9) and strip non-digits
  const normalized = input.value
    .replace(/[၀-၉]/g, d => String(d.charCodeAt(0) - 0x1040))
    .replace(/[^0-9]/g, '')
  if (input.value !== normalized) {
    input.value = normalized
  }
  state.customAmount = normalized
}

function onInputFocus(event: FocusEvent) {
  const el = event.target as HTMLElement | null
  if (!el) return
  // Only nudge the page when the field is not fully visible — prevents the
  // sudden "page drops down" jump when tapping Custom / Redeem Code on desktop.
  setTimeout(() => {
    // The field may already be removed (e.g. user switched back to a preset chip)
    if (!el.isConnected || document.activeElement !== el) return
    const rect = el.getBoundingClientRect()
    const vh = window.visualViewport?.height || window.innerHeight
    if (rect.bottom > vh - 8 || rect.top < 64) {
      el.scrollIntoView({ block: 'nearest', behavior: 'smooth' })
    }
  }, 250)
}

async function pay() {
  if (!showPayment()) {
    await nextTick()
    customInput.value?.focus()
  }
}
</script>

<template>
  <div>
    <ScreenHeading kicker="Plans & payments" title="Shop & Top-Up" description="သင့်လိုအပ်ချက်နဲ့ကိုက်ညီတဲ့ plan ကိုရွေးချယ်ပါ" icon="bag" />
    <div class="section-title-row">
      <span class="section-title">VPN plans <span v-if="hasExtraPlans" class="plans-count-pill">{{ activePlans.length }} Plans</span></span>
      <button type="button" class="wallet-context wallet-jump-btn" data-action="jump-topup" @click="scrollToTopUp">
        <SvgIcon name="wallet" />
        <span><b>{{ state.walletUnlimited ? 'Unlimited' : formatNumber(state.walletBalance) + ' Ks' }}</b></span>
        <span class="jump-chip">ငွေဖြည့် ↓</span>
      </button>
    </div>
    <div class="plans-shell">
      <div class="plans-grid" aria-label="VPN plans">
        <PlanCard
          v-for="plan in basePlans"
          :key="plan.code || plan.name"
          :plan="plan"
          :selected="state.selectedPlan === plan.name"
          @select="choosePlan($event)"
        />
      </div>
      <div
        v-if="hasExtraPlans"
        class="plans-extra-collapse"
        :class="{ 'is-open': plansExpanded }"
        :aria-hidden="!plansExpanded"
        :inert="!plansExpanded"
      >
        <div class="plans-extra-inner">
          <div class="plans-grid plans-grid-extra">
            <PlanCard
              v-for="(plan, index) in extraPlans"
              :key="plan.code || plan.name"
              :plan="plan"
              :selected="state.selectedPlan === plan.name"
              :wide="(activePlans.length % 3 === 1) && index === extraPlans.length - 1"
              @select="choosePlan($event)"
            />
          </div>
        </div>
      </div>
      <button
        v-if="hasExtraPlans"
        type="button"
        class="plans-toggle-btn"
        data-action="toggle-plans"
        :aria-expanded="plansExpanded"
        @click="togglePlansExpand"
      >
        <span>{{ plansToggleLabel }}</span>
        <span class="plans-toggle-arrow" aria-hidden="true">{{ plansExpanded ? '↑' : '↓' }}</span>
      </button>
    </div>
    <button class="primary-btn purchase-btn" data-action="purchase-plan" @click="openDialog({ kind: 'purchase', plan: state.selectedPlan })">
      <SvgIcon name="zap" />{{ selectedPlanCta }}
    </button>
    <p class="small-hint price-hint">
      <SvgIcon name="info" />
      <span>Plan ဈေးနှုန်းအတိုင်း သင့် Wallet မှ အလိုအလျောက် ဖြတ်တောက်ပြီး Key ထုတ်ပေးပါမည်။</span>
    </p>

    <section id="wallet-topup-card" class="topup-card card">
      <div class="section-title-row topup-heading">
        <span class="section-title"><SvgIcon name="wallet" />Wallet Top-Up</span>
        <span class="section-caption">KBZ · Wave · AYA · uab · CB</span>
      </div>
      <span id="amount-label" class="form-label">ငွေပမာဏရွေးရန် (Ks)</span>
      <div class="amount-options" role="group" aria-labelledby="amount-label">
        <button
          v-for="amount in amounts"
          :key="amount"
          class="amount-chip"
          :class="{ active: state.selectedAmount === amount }"
          :data-amount="amount"
          :aria-pressed="state.selectedAmount === amount"
          @click="chooseAmount(amount)"
        >
          {{ amount === 'custom' ? 'Custom' : `${formatNumber(amount)} Ks` }}
        </button>
      </div>
      <Transition name="custom-slot">
        <input
          v-if="state.selectedAmount === 'custom'"
          id="custom-amount"
          ref="customInput"
          class="custom-amount"
          type="text"
          inputmode="numeric"
          pattern="[0-9]*"
          autocomplete="off"
          enterkeyhint="done"
          maxlength="8"
          :value="state.customAmount"
          aria-label="Custom top-up amount in Ks"
          placeholder="ငွေပမာဏထည့်ပါ (Ks)"
          @focus="onInputFocus"
          @input="setCustomAmount"
        />
      </Transition>

      <span id="method-label" class="form-label method-label">ငွေပေးချေမည့်နည်းလမ်း</span>
      <div class="method-row" role="group" aria-labelledby="method-label">
        <button
          v-for="m in paymentOptions"
          :key="m.id"
          type="button"
          class="method-card"
          :class="[m.id, { selected: state.paymentMethod === m.id }]"
          :data-method="m.id"
          :aria-label="m.label"
          :aria-pressed="state.paymentMethod === m.id"
          @click="state.paymentMethod = m.id"
        >
          <PaymentLogo :method="m.id" />
          <span class="method-short">{{ m.label }}</span>
          <span v-if="state.paymentMethod === m.id" class="method-check-dot" aria-hidden="true">
            <SvgIcon name="check-circle" />
          </span>
        </button>
      </div>

      <div class="qr-preview">
        <div class="qr-copy" style="flex: 1; min-width: 0;">
          <strong>{{ currentPayment.name }} · {{ currentPayment.account_name }}</strong>
          <span>
            ဖုန်းနံပါတ်: <b style="color: #2aefbd;">{{ currentPayment.phone }}</b>
            · ပမာဏ: <b id="selected-amount-label">{{ amountLabel }} Ks</b>
          </span>
        </div>
        <button
          type="button"
          class="soft-btn"
          style="flex-shrink: 0; min-height: 36px; padding: 6px 10px; font-size: 11px; white-space: nowrap;"
          @click="copyKey(currentPayment.phone)"
        >
          <SvgIcon name="copy" />Copy
        </button>
      </div>

      <ReceiptUpload />
      <button
        v-if="state.receipt"
        class="primary-btn topup-submit"
        data-action="direct-submit-topup"
        :disabled="state.isSubmitting"
        @click="submitTopUp"
      >
        <SvgIcon name="upload" />{{ state.isSubmitting ? 'ပေးပို့နေပါသည်...' : 'ငွေလွှဲပြေစာ တိုက်ရိုက်ပေးပို့မည်' }}
      </button>
      <button class="soft-btn topup-submit" data-action="show-payment" @click="pay">
        <SvgIcon :name="state.receipt ? 'info' : 'upload'" />{{ state.receipt ? 'ငွေလွှဲအချက်အလက် အသေးစိတ်ကြည့်ရန်' : 'ငွေလွှဲအချက်အလက်နှင့် ပြေစာပေးပို့ရန်' }}<SvgIcon name="arrow-right" />
      </button>
      <p class="small-hint">
        <SvgIcon name="shield" />
        <span>ငွေလွှဲပြေစာ Screenshot တင်ပြီးပါက စနစ်မှ အလိုအလျောက် စစ်ဆေးအတည်ပြုပေးပါမည်။</span>
      </p>
    </section>

    <!-- Redeem Promo / Gift Code Section -->
    <section id="promo-redeem-card" class="card" style="margin-top: 14px; padding: 14px; background: rgba(255, 255, 255, 0.03); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;">
      <div class="section-title-row" style="margin-bottom: 8px;">
        <span class="section-title" style="font-size: 14px;"><SvgIcon name="gift" />Redeem Code အသုံးပြုရန်</span>
      </div>
      <p style="font-size: 12px; color: #94a3b8; margin: 0 0 10px 0;">
        Promo Code (သို့) လက်ဆောင်ကုဒ် ရှိပါက ဤနေရာတွင် ထည့်သွင်းပြီး Wallet လက်ကျန်ငွေ ရယူနိုင်ပါသည်။
      </p>
      <div style="display: flex; gap: 8px; min-width: 0;">
        <input
          v-model="promoCodeInput"
          type="text"
          class="custom-amount redeem-code-input"
          style="margin-top: 0; flex: 1; min-width: 0; text-transform: uppercase;"
          placeholder="CODE ထည့်ပါ (ဥပမာ- GIFT1000)"
          autocomplete="off"
          autocapitalize="characters"
          enterkeyhint="done"
          :disabled="state.isSubmitting"
          @focus="onInputFocus"
          @keyup.enter="handleRedeemCode"
        />
        <button
          class="primary-btn"
          style="padding: 0 14px; white-space: nowrap; flex-shrink: 0;"
          :disabled="state.isSubmitting || !promoCodeInput.trim()"
          @click="handleRedeemCode"
        >
          <SvgIcon name="zap" />{{ state.isSubmitting ? 'စစ်ဆေးနေ...' : 'ရယူမည်' }}
        </button>
      </div>
    </section>
  </div>
</template>
