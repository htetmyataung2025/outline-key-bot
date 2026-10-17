<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
const { state, claimReward } = useMiniApp()
const completedDays = computed(() => state.claimedToday ? 5 : 4)
const days = ['M', 'T', 'W', 'T', 'F', 'S', 'S']
</script>
<template>
  <section class="reward-banner"><SvgIcon name="gift" class="reward-art" /><div class="reward-top"><span class="reward-label">Daily check-in</span><span class="streak-pill"><SvgIcon name="flame" />{{ completedDays }} day streak</span></div><div class="reward-points">{{ state.points }} <small>PTS</small></div><p>နေ့စဉ်ဝင်ရောက်ပြီး points စုဆောင်းပါ</p>
    <div class="checkin-days" aria-label="Daily check-in progress"><div v-for="(day, index) in days" :key="index" class="day-box" :class="{ done: index < completedDays, today: index === completedDays && !state.claimedToday }" :aria-label="`Day ${index + 1}${index < completedDays ? ', completed' : ''}`">{{ day }}<span><SvgIcon :name="index < completedDays ? 'check' : 'plus'" /></span></div></div>
    <button class="primary-btn" data-action="claim" :disabled="state.claimedToday" @click="claimReward"><SvgIcon :name="state.claimedToday ? 'check-circle' : 'gift'" />{{ state.claimedToday ? 'ဒီနေ့ Claim လုပ်ပြီးပါပြီ · +10 Pts' : 'ဒီနေ့ Claim လုပ်ရန် · +10 Pts' }}</button>
  </section>
</template>
