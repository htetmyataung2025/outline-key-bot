<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

const props = withDefaults(defineProps<{ interactive?: boolean }>(), { interactive: true })
const { state, openDialog, setTab } = useMiniApp()

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
      <button v-if="interactive && hasLiveRecords" class="section-link" data-action="all-history" @click="openDialog({ kind: 'history' })">
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
          <strong>{{ item.plan_name }} {{ item.disp_gb ? `· ${item.disp_gb}` : '' }}</strong>
          <small>{{ item.order_id }} · {{ item.date || 'Recent' }}</small>
        </span>
        <span class="history-amount negative">
          − {{ item.price || '—' }}
          <small>{{ item.status || 'Active' }}</small>
        </span>
      </div>
    </template>

    <!-- Clean, Honest Empty State -->
    <div v-else class="empty-state" style="padding: 24px 12px; text-align: center;">
      <div class="empty-icon"><SvgIcon name="bag" /></div>
      ဝယ်ယူမှုမှတ်တမ်း မရှိသေးပါခင်ဗျာ။<br />
      <button class="section-link" style="margin-top: 8px;" @click="setTab('shop')">
        Plan များ ကြည့်ရှုမည်<SvgIcon name="arrow-right" />
      </button>
    </div>
  </section>
</template>
