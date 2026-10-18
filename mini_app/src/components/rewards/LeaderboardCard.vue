<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

withDefaults(defineProps<{ interactive?: boolean }>(), { interactive: true })
const { state, openDialog } = useMiniApp()

const hasLiveRows = computed(() => {
  return state.leaderboard.rows && state.leaderboard.rows.length > 0
})

const topRows = computed(() => {
  return (state.leaderboard.rows || []).slice(0, 5)
})
</script>

<template>
  <section class="leaderboard card">
    <div class="list-head">
      <strong><SvgIcon name="medal" />Top customers</strong>
      <button v-if="interactive" class="section-link" data-action="leaderboard" @click="openDialog({ kind: 'leaderboard' })">
        Leaderboard<SvgIcon name="arrow-right" />
      </button>
    </div>

    <!-- Live Leaderboard Rows -->
    <template v-if="hasLiveRows">
      <div v-for="row in topRows" :key="row.rank" class="leader-row" :class="{ you: row.is_you }">
        <span class="rank" :class="{ gold: row.rank === 1, silver: row.rank === 2, bronze: row.rank === 3, self: row.is_you }">
          {{ row.rank < 10 ? `0${row.rank}` : row.rank }}
        </span>
        <span class="leader-avatar" :class="{ gold: row.rank === 1, silver: row.rank === 2, violet: row.is_you }">
          {{ row.name.slice(0, 2).toUpperCase() }}
        </span>
        <span class="leader-name">
          {{ row.name }}
          <small>{{ row.is_you ? `Your rank · #${row.rank}` : 'VIP Member' }}</small>
        </span>
        <span class="leader-score">{{ formatNumber(row.points) }} pts</span>
      </div>

      <!-- Ensure user row always rendered if not in top 5 -->
      <div v-if="!topRows.some(r => r.is_you)" class="leader-row you">
        <span class="rank self">—</span>
        <span class="leader-avatar violet">{{ state.user.initials }}</span>
        <span class="leader-name">{{ state.user.name }}<small>Your rank</small></span>
        <span class="leader-score">{{ state.points }} pts</span>
      </div>
    </template>

    <!-- Fallback / Demo Rows -->
    <template v-else>
      <div class="leader-row">
        <span class="rank gold">01</span>
        <span class="leader-avatar gold">TH</span>
        <span class="leader-name">Thiri H.<small>VIP Member</small></span>
        <span class="leader-score">2,480 pts</span>
      </div>
      <div class="leader-row">
        <span class="rank silver">02</span>
        <span class="leader-avatar silver">MK</span>
        <span class="leader-name">Min Khant<small>VIP Member</small></span>
        <span class="leader-score">1,960 pts</span>
      </div>
      <div class="leader-row you">
        <span class="rank self">12</span>
        <span class="leader-avatar violet">{{ state.user.initials }}</span>
        <span class="leader-name">{{ state.user.name }}<small>Your rank · #12</small></span>
        <span class="leader-score">{{ state.points }} pts</span>
      </div>
    </template>
  </section>
</template>
