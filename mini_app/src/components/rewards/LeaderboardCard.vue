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
  <section id="leaderboard-section" class="leaderboard leaderboard-card card">
    <div class="list-head">
      <strong><SvgIcon name="medal" />Top customers</strong>
      <button v-if="interactive && hasLiveRows" class="section-link" data-action="leaderboard" @click="openDialog({ kind: 'leaderboard' })">
        Leaderboard<SvgIcon name="arrow-right" />
      </button>
    </div>

    <!-- Skeleton Loading State -->
    <template v-if="state.isLeaderboardLoading && !hasLiveRows">
      <div v-for="i in 3" :key="`skel-ld-${i}`" class="leader-row skeleton-row-wrap">
        <span class="rank skeleton-shimmer" style="width: 20px; height: 16px; border-radius: 4px;"></span>
        <span class="leader-avatar skeleton-shimmer" style="width: 32px; height: 32px; border-radius: 10px;"></span>
        <span class="leader-name" style="flex: 1; display: flex; flex-direction: column; gap: 5px;">
          <span class="skeleton-shimmer" style="width: 50%; height: 13px; border-radius: 4px;"></span>
          <span class="skeleton-shimmer" style="width: 30%; height: 9px; border-radius: 4px;"></span>
        </span>
        <span class="leader-score skeleton-shimmer" style="width: 48px; height: 14px; border-radius: 4px;"></span>
      </div>
    </template>

    <!-- Live Leaderboard Rows -->
    <template v-else-if="hasLiveRows">
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

    <!-- User has points but no other rankings yet -->
    <template v-else-if="state.points > 0">
      <div class="leader-row you">
        <span class="rank self">01</span>
        <span class="leader-avatar violet">{{ state.user.initials }}</span>
        <span class="leader-name">{{ state.user.name }}<small>လက်ရှိရမှတ်</small></span>
        <span class="leader-score">{{ state.points }} pts</span>
      </div>
    </template>

    <!-- Clean, Honest Empty State -->
    <div v-else class="empty-state" style="padding: 24px 12px; text-align: center;">
      <div class="empty-icon"><SvgIcon name="medal" /></div>
      ဦးဆောင်သူစာရင်း မရှိသေးပါခင်ဗျာ။<br />
      <small style="color: #8993ad;">နေ့စဉ် Points စုဆောင်းပြီး Leaderboard တွင် ပါဝင်နိုင်ပါသည်</small>
    </div>
  </section>
</template>
