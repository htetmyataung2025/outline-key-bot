<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

const { state, claimReward, redeemPoints, cooldownFormatted } = useMiniApp()

// Real streak count from backend
const streak = computed(() => Math.max(0, state.streakDays || (state.claimedToday ? 1 : 0)))

// Days completed in current 7-day cycle: e.g. streak 1 => completedDays 1
const completedDays = computed(() => {
  if (streak.value <= 0) return 0
  const rem = streak.value % 7
  return rem === 0 ? 7 : rem
})

// 7-day streak cycle labels: Day 1 through Day 7
const days = ['D1', 'D2', 'D3', 'D4', 'D5', 'D6', 'D7']

const claimButtonText = computed(() => {
  if (state.isClaiming) {
    return 'Points ဆုမဲ ဖွင့်လှစ်နေပါသည်...'
  }
  if (!state.claimedToday) {
    if (completedDays.value === 6) {
      return 'Day 7 Jackpot Points ရယူမည် 🎁'
    }
    return 'Daily Points ရယူမည်'
  }
  if (cooldownFormatted.value) {
    return `နောက် Claim ရန်: ${cooldownFormatted.value}`
  }
  return `${state.cooldownHours} နာရီ Cooldown စောင့်ဆိုင်းနေပါသည်`
})
</script>
<template>
  <section class="reward-banner">
    <SvgIcon name="gift" class="reward-art" />
    <div class="reward-top">
      <span class="reward-label">Points Check-in</span>
      <span class="streak-pill"><SvgIcon name="flame" />{{ streak }} day streak</span>
    </div>
    <div class="reward-points">{{ formatNumber(state.points) }} <small>PTS</small></div>
    <p>{{ state.cooldownHours }} နာရီတစ်ကြိမ် ဝင်ရောက်ပြီး points စုဆောင်းပါ (၇ ရက်ပြည့်ပါက အပိုဆု ရရှိပါမည်)</p>
    <div class="checkin-days" aria-label="Daily check-in progress">
      <div
        v-for="(day, index) in days"
        :key="index"
        class="day-box"
        :class="{ done: index < completedDays, today: index === completedDays && !state.claimedToday, jackpot: index === 6 }"
        :aria-label="`Day ${index + 1}${index < completedDays ? ', completed' : ''}`"
      >
        {{ day }}
        <span><SvgIcon :name="index < completedDays ? 'check' : (index === 6 ? 'gift' : 'plus')" /></span>
      </div>
    </div>
    <button
      class="primary-btn"
      data-action="claim"
      :disabled="state.claimedToday || state.isClaiming"
      :class="{ 'is-cooldown': state.claimedToday && !state.isClaiming }"
      @click="claimReward"
    >
      <SvgIcon :name="state.isClaiming ? 'refresh' : (state.claimedToday ? 'clock' : 'gift')" :class="{ 'spin-inline': state.isClaiming }" />
      {{ claimButtonText }}
    </button>

    <!-- Starter Plan Points Redemption -->
    <div class="card" style="margin-top: 14px; padding: 12px; background: rgba(255, 255, 255, 0.04); border: 1px solid rgba(255, 255, 255, 0.08); border-radius: 12px;">
      <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
        <span style="font-weight: 600; font-size: 14px; color: #f8fafc;">🎫 Starter Plan (25 GB / 30 ရက်)</span>
        <span style="font-size: 13px; color: #2aefbd; font-weight: 600;">{{ formatNumber(state.points) }} / {{ formatNumber(state.starterCost) }} PTS</span>
      </div>
      <div style="width: 100%; height: 6px; background: rgba(255, 255, 255, 0.1); border-radius: 999px; overflow: hidden; margin-bottom: 8px;">
        <div
          style="height: 100%; background: linear-gradient(90deg, #10b981, #2aefbd); border-radius: 999px; transition: width 0.3s;"
          :style="{ width: `${Math.min(100, Math.round((state.points / (state.starterCost || 5000)) * 100))}%` }"
        />
      </div>
      <p v-if="!state.hasToppedUp" style="font-size: 12px; color: #f87171; margin: 0 0 8px 0;">
        🔒 Points ဖြင့် လဲယူရန် အနည်းဆုံး တစ်ကြိမ် ငွေဖြည့်ထားရန် လိုအပ်ပါသည်။
      </p>
      <button
        class="soft-btn"
        style="width: 100%; justify-content: center; font-size: 13px;"
        :disabled="state.isSubmitting || state.points < state.starterCost || !state.hasToppedUp"
        @click="redeemPoints"
      >
        <SvgIcon name="gift" />
        {{ state.isSubmitting ? 'လဲယူနေပါသည်...' : 'Points ဖြင့် Starter Plan လဲယူမည်' }}
      </button>
    </div>
  </section>
</template>
