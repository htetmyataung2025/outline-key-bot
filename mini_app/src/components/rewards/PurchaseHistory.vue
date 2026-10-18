<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

const props = withDefaults(defineProps<{ interactive?: boolean }>(), { interactive: true })
const { state, openDialog } = useMiniApp()

const hasLiveRecords = computed(() => {
  return (state.history.purchases && state.history.purchases.length > 0) ||
         (state.history.slips && state.history.slips.length > 0)
})

const displayPurchases = computed(() => {
  const p = state.history.purchases || []
  return props.interactive ? p.slice(0, 5) : p
})

const displaySlips = computed(() => {
  const s = state.history.slips || []
  return props.interactive ? s.slice(0, 3) : s
})
</script>

<template>
  <section class="history-card card">
    <div class="list-head">
      <strong>Purchase history</strong>
      <button v-if="interactive" class="section-link" data-action="all-history" @click="openDialog({ kind: 'history' })">
        အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" />
      </button>
    </div>

    <!-- Live Records Mode -->
    <template v-if="hasLiveRecords">
      <div v-for="(slip, idx) in displaySlips" :key="`slip-${idx}`" class="history-row">
        <span class="history-icon" :class="{ amber: slip.status === 'PENDING', negative: slip.status === 'REJECTED' }">
          <SvgIcon :name="slip.status === 'APPROVED' ? 'check' : (slip.status === 'PENDING' ? 'clock' : 'info')" />
        </span>
        <span class="history-meta">
          <strong>Top-Up · {{ (slip.method || 'KBZ').toUpperCase() }}</strong>
          <small>{{ slip.submitted_at || 'Recent' }} · {{ slip.status }}</small>
        </span>
        <span class="history-amount" :class="slip.status === 'APPROVED' ? 'positive' : ''">
          +{{ formatNumber(slip.amount) }} Ks
          <small>{{ slip.status }}</small>
        </span>
      </div>

      <div v-for="(item, idx) in displayPurchases" :key="`pur-${idx}`" class="history-row">
        <span class="history-icon violet"><SvgIcon name="key" /></span>
        <span class="history-meta">
          <strong>{{ item.plan_name }}</strong>
          <small>{{ item.order_id }} · {{ item.date || 'Recent' }}</small>
        </span>
        <span class="history-amount negative">
          − {{ item.price || '—' }}
          <small>{{ item.status || 'Active' }}</small>
        </span>
      </div>
    </template>

    <!-- Default / Fallback Records -->
    <template v-else>
      <div class="history-row">
        <span class="history-icon"><SvgIcon name="arrow-up-right" /></span>
        <span class="history-meta">
          <strong>Wallet Top-Up</strong>
          <small>#ORD-241017 · 17 Oct 2026</small>
        </span>
        <span class="history-amount positive">+5,000 Ks<small>Completed</small></span>
      </div>
      <div class="history-row">
        <span class="history-icon violet"><SvgIcon name="key" /></span>
        <span class="history-meta">
          <strong>VIP Plan · 150 GB</strong>
          <small>#ORD-241005 · 05 Oct 2026</small>
        </span>
        <span class="history-amount negative">− — Ks<small>Completed</small></span>
      </div>
      <div class="history-row">
        <span class="history-icon amber"><SvgIcon name="gift" /></span>
        <span class="history-meta">
          <strong>Daily check-in reward</strong>
          <small>{{ state.claimedToday ? '17 Oct 2026' : '16 Oct 2026' }} · Points</small>
        </span>
        <span class="history-amount positive">+10 Pts<small>Claimed</small></span>
      </div>
    </template>
  </section>
</template>
