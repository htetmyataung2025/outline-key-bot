<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
withDefaults(defineProps<{ interactive?: boolean }>(), { interactive: true })
const { state, openDialog } = useMiniApp()
</script>
<template>
  <section class="history-card card"><div class="list-head"><strong>Purchase history</strong><button v-if="interactive" class="section-link" data-action="all-history" @click="openDialog({ kind: 'history' })">အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" /></button></div>
    <div class="history-row"><span class="history-icon"><SvgIcon name="arrow-up-right" /></span><span class="history-meta"><strong>Wallet Top-Up</strong><small>#ORD-241017 · 17 Oct 2026</small></span><span class="history-amount positive">+5,000 Ks<small>Completed</small></span></div>
    <div class="history-row"><span class="history-icon violet"><SvgIcon name="key" /></span><span class="history-meta"><strong>VIP Plan · 150 GB</strong><small>#ORD-241005 · 05 Oct 2026</small></span><span class="history-amount negative">− — Ks<small>Completed</small></span></div>
    <div class="history-row"><span class="history-icon amber"><SvgIcon name="gift" /></span><span class="history-meta"><strong>Daily check-in reward</strong><small>{{ state.claimedToday ? '17 Oct 2026' : '16 Oct 2026' }} · Points</small></span><span class="history-amount positive">+10 Pts<small>Claimed</small></span></div>
  </section>
</template>
