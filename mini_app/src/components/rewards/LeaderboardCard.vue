<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
withDefaults(defineProps<{ interactive?: boolean }>(), { interactive: true })
const { state, openDialog } = useMiniApp()
</script>
<template>
  <section class="leaderboard card"><div class="list-head"><strong><SvgIcon name="medal" />Top customers</strong><button v-if="interactive" class="section-link" data-action="leaderboard" @click="openDialog({ kind: 'leaderboard' })">Leaderboard<SvgIcon name="arrow-right" /></button></div>
    <div class="leader-row"><span class="rank gold">01</span><span class="leader-avatar gold">TH</span><span class="leader-name">Thiri H.<small>VIP Member</small></span><span class="leader-score">2,480 pts</span></div>
    <div class="leader-row"><span class="rank silver">02</span><span class="leader-avatar silver">MK</span><span class="leader-name">Min Khant<small>VIP Member</small></span><span class="leader-score">1,960 pts</span></div>
    <div class="leader-row you"><span class="rank self">12</span><span class="leader-avatar violet">{{ state.user.initials }}</span><span class="leader-name">{{ state.user.name }}<small>Your rank · #12</small></span><span class="leader-score">{{ state.points }} pts</span></div>
  </section>
</template>
