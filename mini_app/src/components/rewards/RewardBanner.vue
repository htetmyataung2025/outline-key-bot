<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'

const { state, claimReward, cooldownFormatted } = useMiniApp()

// Real streak count from backend
const streak = computed(() => Math.max(0, state.streakDays || (state.claimedToday ? 1 : 0)))

// Days completed in current 7-day cycle: e.g. streak 1 => completedDays 1
const completedDays = computed(() => {
  if (streak.value <= 0) return 0
  const rem = streak.value % 7
  return rem === 0 ? 7 : rem
})

const days = ['M', 'T', 'W', 'T', 'F', 'S', 'S']

const claimButtonText = computed(() => {
  if (!state.claimedToday) return 'Claim လုပ်ရန် · +10 Pts'
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
    <div class="reward-points">{{ state.points }} <small>PTS</small></div>
    <p>{{ state.cooldownHours }} နာရီတစ်ကြိမ် ဝင်ရောက်ပြီး points စုဆောင်းပါ</p>
    <div class="checkin-days" aria-label="Daily check-in progress">
      <div
        v-for="(day, index) in days"
        :key="index"
        class="day-box"
        :class="{ done: index < completedDays, today: index === completedDays && !state.claimedToday }"
        :aria-label="`Day ${index + 1}${index < completedDays ? ', completed' : ''}`"
      >
        {{ day }}
        <span><SvgIcon :name="index < completedDays ? 'check' : 'plus'" /></span>
      </div>
    </div>
    <button
      class="primary-btn"
      data-action="claim"
      :disabled="state.claimedToday"
      :class="{ 'is-cooldown': state.claimedToday }"
      @click="claimReward"
    >
      <SvgIcon :name="state.claimedToday ? 'clock' : 'gift'" />
      {{ claimButtonText }}
    </button>
  </section>
</template>
