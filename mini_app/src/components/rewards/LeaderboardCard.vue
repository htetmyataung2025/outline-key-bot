<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

const props = withDefaults(defineProps<{ interactive?: boolean; inDialog?: boolean }>(), {
  interactive: true,
  inDialog: false,
})
const { state, openDialog } = useMiniApp()

const allRows = computed(() => state.leaderboard.rows || [])
const totalPlayers = computed(() => state.leaderboard.total_players || allRows.value.length)
const hasLiveRows = computed(() => allRows.value.length > 0)

const displayRows = computed(() => {
  return props.inDialog ? allRows.value : allRows.value.slice(0, 5)
})

const myStanding = computed(() => {
  const row = allRows.value.find(r => r.is_you)
  if (row) return row
  if (state.leaderboard.me) {
    return {
      rank: state.leaderboard.me.rank,
      name: state.leaderboard.me.name || state.user.name,
      points: state.leaderboard.me.points,
      is_you: true,
    }
  }
  return {
    rank: null as number | null,
    name: state.user.name,
    points: state.points,
    is_you: true,
  }
})
</script>

<template>
  <section :id="inDialog ? undefined : 'leaderboard-section'" :class="inDialog ? 'leaderboard-dialog-wrap' : 'leaderboard leaderboard-card card'">
    <div v-if="!inDialog" class="list-head">
      <strong>
        <SvgIcon name="medal" />
        Top customers
        <span v-if="totalPlayers > 0" class="section-count-pill">{{ totalPlayers }} ဦး</span>
      </strong>
      <button v-if="interactive && hasLiveRows" class="section-link" data-action="leaderboard" @click="openDialog({ kind: 'leaderboard' })">
        Leaderboard<SvgIcon name="arrow-right" />
      </button>
    </div>

    <!-- Pinned Summary Banner inside Full Modal -->
    <div v-if="inDialog && hasLiveRows" class="modal-sticky-bar">
      <div class="leaderboard-summary-bar">
        <div class="leader-summary-meta">
          <span>7-Day Ranking</span>
          <b>{{ totalPlayers }} ဦး ပါဝင်သည်</b>
        </div>
        <div class="leader-summary-you">
          <span>သင့်အဆင့်</span>
          <b>{{ myStanding.rank ? `#${myStanding.rank}` : '—' }} · {{ formatNumber(myStanding.points) }} pts</b>
        </div>
      </div>
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
      <div :class="inDialog ? 'modal-list-scroll' : 'leaderboard-list'">
        <div v-for="row in displayRows" :key="`${row.rank}-${row.name}`" class="leader-row" :class="{ you: row.is_you }">
          <span class="rank" :class="{ gold: row.rank === 1, silver: row.rank === 2, bronze: row.rank === 3, self: row.is_you }">
            {{ row.rank < 10 ? `0${row.rank}` : row.rank }}
          </span>
          <span class="leader-avatar" :class="{ gold: row.rank === 1, silver: row.rank === 2, bronze: row.rank === 3, violet: row.is_you }">
            {{ row.name.slice(0, 2).toUpperCase() }}
          </span>
          <span class="leader-name">
            {{ row.name }}
            <small>{{ row.is_you ? `Your rank · #${row.rank}` : (row.rank <= 3 ? `Top #${row.rank} Leader` : 'VIP Member') }}</small>
          </span>
          <span class="leader-score">{{ formatNumber(row.points) }} pts</span>
        </div>
      </div>

      <!-- Ensure user row always visible in preview even if not in Top 5 -->
      <div v-if="!inDialog && !displayRows.some(r => r.is_you)" class="leader-row you">
        <span class="rank self">{{ myStanding.rank ? `#${myStanding.rank}` : '—' }}</span>
        <span class="leader-avatar violet">{{ state.user.initials }}</span>
        <span class="leader-name">{{ myStanding.name }}<small>{{ myStanding.rank ? `Your rank · #${myStanding.rank}` : 'Your rank' }}</small></span>
        <span class="leader-score">{{ formatNumber(myStanding.points) }} pts</span>
      </div>

      <button
        v-if="!inDialog && interactive && totalPlayers > 5"
        type="button"
        class="list-more-foot"
        @click="openDialog({ kind: 'leaderboard' })"
      >
        <span>Top {{ Math.min(totalPlayers, 50) }} စာရင်းအပြည့်အစုံ ကြည့်ရန်</span>
        <SvgIcon name="arrow-right" />
      </button>
    </template>

    <!-- User has points but no other rankings yet -->
    <template v-else-if="state.points > 0">
      <div class="leader-row you">
        <span class="rank self">01</span>
        <span class="leader-avatar violet">{{ state.user.initials }}</span>
        <span class="leader-name">{{ state.user.name }}<small>လက်ရှိရမှတ်</small></span>
        <span class="leader-score">{{ formatNumber(state.points) }} pts</span>
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
