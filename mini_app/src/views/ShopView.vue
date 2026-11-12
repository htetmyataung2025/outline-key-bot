<script setup lang="ts">
import { computed, nextTick, ref } from 'vue'
import ScreenHeading from '../components/ui/ScreenHeading.vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import PlanCard from '../components/shop/PlanCard.vue'
import ReceiptUpload from '../components/shop/ReceiptUpload.vue'
import { useMiniApp } from '../composables/useMiniApp'
import { plans as defaultPlans } from '../data/demo'
import { formatNumber } from '../utils/format'
import type { PlanName, TopUpAmount } from '../types'

const { state, amountLabel, openDialog, showPayment, submitTopUp, redeemCode, copyKey } = useMiniApp()
const amounts: TopUpAmount[] = [1000, 2000, 5000, 'custom']
const customInput = ref<HTMLInputElement | null>(null)
const promoCodeInput = ref('')

const currentPayment = computed(() => {
  return state.paymentMethods[state.paymentMethod] || {
    name: state.paymentMethod === 'kbz' ? 'KBZPay' : 'WavePay',
    account_name: 'Htet Myat Aung',
    phone: '09699970092',
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
  setTimeout(() => {
    el.scrollIntoView({ block: 'center', behavior: 'smooth' })
  }, 150)
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
      <span class="section-title">VPN plans</span>
      <span class="wallet-context"><SvgIcon name="wallet" />Wallet · <b>{{ formatNumber(state.walletBalance) }} Ks</b></span>
    </div>
    <div class="plans-grid">
      <PlanCard
        v-for="plan in activePlans"
        :key="plan.name"
        :plan="plan"
        :selected="state.selectedPlan === plan.name"
        @select="choosePlan($event)"
      />
    </div>
    <button class="primary-btn purchase-btn" data-action="purchase-plan" @click="openDialog({ kind: 'purchase', plan: state.selectedPlan })">
      <SvgIcon name="zap" />Wallet ဖြင့် 1-click ဝယ်ယူရန်
    </button>
    <p class="small-hint price-hint">
      <SvgIcon name="info" />
      <span>Plan ဈေးနှုန်းအတိုင်း သင့် Wallet မှ အလိုအလျောက် ဖြတ်တောက်ပြီး Key ထုတ်ပေးပါမည်။</span>
    </p>

    <section id="wallet-topup-card" class="topup-card card">
      <div class="section-title-row topup-heading">
        <span class="section-title"><SvgIcon name="wallet" />Wallet Top-Up</span>
        <span class="section-caption">KBZPay · WavePay</span>
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

      <span id="method-label" class="form-label method-label">ငွေပေးချေမည့်နည်းလမ်း</span>
      <div class="method-row" role="group" aria-labelledby="method-label">
        <button
          class="method-card"
          :class="{ selected: state.paymentMethod === 'kbz' }"
          data-method="kbz"
          :aria-pressed="state.paymentMethod === 'kbz'"
          @click="state.paymentMethod = 'kbz'"
        >
          <span class="method-logo" aria-hidden="true">K</span>
          <span class="method-name">KBZPay<small>{{ state.paymentMethods.kbz?.phone || '09699970092' }}</small></span>
          <SvgIcon v-if="state.paymentMethod === 'kbz'" name="check-circle" class="method-check" />
        </button>
        <button
          class="method-card wave"
          :class="{ selected: state.paymentMethod === 'wave' }"
          data-method="wave"
          :aria-pressed="state.paymentMethod === 'wave'"
          @click="state.paymentMethod = 'wave'"
        >
          <span class="method-logo" aria-hidden="true">W</span>
          <span class="method-name">WavePay<small>{{ state.paymentMethods.wave?.phone || '09699970092' }}</small></span>
          <SvgIcon v-if="state.paymentMethod === 'wave'" name="check-circle" class="method-check" />
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
          class="custom-amount"
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
