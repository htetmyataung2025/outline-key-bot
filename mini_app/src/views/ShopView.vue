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

const { state, amountLabel, openDialog, showPayment } = useMiniApp()
const amounts: TopUpAmount[] = [1000, 2000, 5000, 'custom']
const customInput = ref<HTMLInputElement | null>(null)

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
  state.customAmount = (event.target as HTMLInputElement).value
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

    <section class="topup-card card">
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
        type="number"
        min="500"
        max="10000000"
        step="1"
        inputmode="numeric"
        :value="state.customAmount"
        aria-label="Custom top-up amount in Ks"
        placeholder="ငွေပမာဏထည့်ပါ (Ks)"
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
          <span class="method-name">KBZPay<small>QR Payment</small></span>
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
          <span class="method-name">WavePay<small>QR Payment</small></span>
          <SvgIcon v-if="state.paymentMethod === 'wave'" name="check-circle" class="method-check" />
        </button>
      </div>

      <div class="qr-preview">
        <div class="qr-copy">
          <strong>Payment QR ကို ကြည့်ရှုရန်</strong>
          <span>ရွေးထားသော ပမာဏ: <b id="selected-amount-label">{{ amountLabel }} Ks</b><br />KBZPay သို့မဟုတ် WavePay သို့ တိုက်ရိုက်လွှဲနိုင်ပါသည်။</span>
        </div>
        <div class="qr-placeholder" aria-label="Illustrative QR icon">
          <SvgIcon name="qr" />
          <span>PAY</span>
        </div>
      </div>

      <ReceiptUpload />
      <button class="soft-btn topup-submit" data-action="show-payment" @click="pay">
        <SvgIcon name="qr" />QR ကြည့်ရန် / ငွေလွှဲရန်<SvgIcon name="arrow-right" />
      </button>
      <p class="small-hint">
        <SvgIcon name="shield" />
        <span>ငွေလွှဲပြေစာ Screenshot တင်ပြီးပါက စနစ်မှ အလိုအလျောက် စစ်ဆေးအတည်ပြုပေးပါမည်။</span>
      </p>
    </section>
  </div>
</template>
