<script setup lang="ts">
import { computed, ref } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber } from '../../utils/format'

const props = withDefaults(defineProps<{ interactive?: boolean; inDialog?: boolean }>(), {
  interactive: true,
  inDialog: false,
})
const { state, openDialog, setTab } = useMiniApp()

type HistoryFilter = 'all' | 'purchases' | 'slips'
const activeFilter = ref<HistoryFilter>('all')

interface HistoryEntry {
  kind: 'slip' | 'purchase'
  key: string
  title: string
  subtitle: string
  amountText: string
  amountTone: 'positive' | 'negative'
  badgeText: string
  badgeTone: 'approved' | 'rejected' | 'pending' | 'active' | 'expired'
  sortTime: number
  order: number
}

const METHOD_LABELS: Record<string, string> = {
  KBZ: 'KBZPay',
  WAVE: 'WavePay',
  AYA: 'AYA Pay',
  UAB: 'uab pay',
  CB: 'CB Pay',
}

function formatMethodLabel(method?: string): string {
  const code = (method || 'KBZ').trim().toUpperCase()
  return METHOD_LABELS[code] || code
}

function formatSlipStatus(status?: string): string {
  const s = (status || 'PENDING').toUpperCase()
  if (s === 'APPROVED') return 'အတည်ပြုပြီး'
  if (s === 'REJECTED') return 'ပယ်ဖျက်ပြီး'
  return 'စစ်ဆေးနေဆဲ'
}

function parseTimestamp(raw?: string): number {
  if (!raw) return 0
  const s = raw.trim()
  // "YYYY-MM-DD HH:MM:SS"
  const isoMatch = s.match(/^(\d{4})-(\d{2})-(\d{2})\s+(\d{2}):(\d{2})(?::(\d{2}))?/)
  if (isoMatch) {
    const [, y, m, d, hh, mm, ss = '0'] = isoMatch
    return new Date(Number(y), Number(m) - 1, Number(d), Number(hh), Number(mm), Number(ss)).getTime()
  }
  // "DD/MM/YYYY (hh:mm AM/PM)"
  const dmyMatch = s.match(/^(\d{2})\/(\d{2})\/(\d{4})\s*\((\d{1,2}):(\d{2})\s*(AM|PM)\)/i)
  if (dmyMatch) {
    const [, d, m, y, hStr, mm, ap] = dmyMatch
    let hh = Number(hStr) % 12
    if ((ap || '').toUpperCase() === 'PM') hh += 12
    return new Date(Number(y), Number(m) - 1, Number(d), hh, Number(mm)).getTime()
  }
  const parsed = Date.parse(s)
  return Number.isNaN(parsed) ? 0 : parsed
}

const slipsCount = computed(() => (state.history.slips || []).length)
const purchasesCount = computed(() => (state.history.purchases || []).length)
const totalCount = computed(() => slipsCount.value + purchasesCount.value)
const hasLiveRecords = computed(() => totalCount.value > 0)

const allEntries = computed<HistoryEntry[]>(() => {
  const slips = (state.history.slips || []).map((slip, idx): HistoryEntry => {
    const status = (slip.status || 'PENDING').toUpperCase()
    const badgeTone = status === 'APPROVED' ? 'approved' : status === 'REJECTED' ? 'rejected' : 'pending'
    return {
      kind: 'slip',
      key: slip.slip_id ? `slip-${slip.slip_id}` : `slip-${idx}`,
      title: `Top-Up · ${formatMethodLabel(slip.method)}`,
      subtitle: `${slip.submitted_at || 'Recent'} · ${formatSlipStatus(status)}`,
      amountText: `+${formatNumber(slip.amount)} Ks`,
      amountTone: 'positive',
      badgeText: status,
      badgeTone,
      sortTime: parseTimestamp(slip.submitted_at),
      order: idx,
    }
  })

  const purchases = (state.history.purchases || []).map((item, idx): HistoryEntry => {
    const status = item.status || 'Active'
    const isExpired = status.toLowerCase() === 'expired'
    return {
      kind: 'purchase',
      key: item.order_id && item.order_id !== 'N/A' ? `pur-${item.order_id}-${idx}` : `pur-${idx}`,
      title: `${item.plan_name}${item.disp_gb ? ` · ${item.disp_gb}` : ''}`,
      subtitle: `${item.order_id} · ${item.date || 'Recent'}`,
      amountText: `− ${item.price || '—'}`,
      amountTone: 'negative',
      badgeText: status,
      badgeTone: isExpired ? 'expired' : 'active',
      sortTime: parseTimestamp(item.date),
      order: slips.length + idx,
    }
  })

  return [...slips, ...purchases].sort((a, b) => {
    if (a.sortTime !== b.sortTime) return b.sortTime - a.sortTime
    return a.order - b.order
  })
})

const displayEntries = computed(() => {
  if (!props.inDialog && props.interactive) {
    return allEntries.value.slice(0, 5)
  }
  if (activeFilter.value === 'purchases') {
    return allEntries.value.filter(e => e.kind === 'purchase')
  }
  if (activeFilter.value === 'slips') {
    return allEntries.value.filter(e => e.kind === 'slip')
  }
  return allEntries.value
})
</script>

<template>
  <section :class="inDialog ? 'history-dialog-wrap' : 'history-card card'">
    <div v-if="!inDialog" class="list-head">
      <strong>
        Purchase history
        <span v-if="totalCount > 0" class="section-count-pill">{{ totalCount }}</span>
      </strong>
      <button v-if="interactive && hasLiveRecords" class="section-link" data-action="all-history" @click="openDialog({ kind: 'history' })">
        အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" />
      </button>
    </div>

    <!-- Filter Chips inside Full Modal -->
    <div v-if="inDialog && hasLiveRecords" class="modal-sticky-bar">
      <div class="filter-row compact-filters" role="tablist" aria-label="Filter history">
        <button
          type="button"
          class="filter-chip"
          :class="{ active: activeFilter === 'all' }"
          data-history-filter="all"
          @click="activeFilter = 'all'"
        >
          All · {{ totalCount }}
        </button>
        <button
          type="button"
          class="filter-chip"
          :class="{ active: activeFilter === 'purchases' }"
          data-history-filter="purchases"
          @click="activeFilter = 'purchases'"
        >
          Plans · {{ purchasesCount }}
        </button>
        <button
          type="button"
          class="filter-chip"
          :class="{ active: activeFilter === 'slips' }"
          data-history-filter="slips"
          @click="activeFilter = 'slips'"
        >
          Top-Ups · {{ slipsCount }}
        </button>
      </div>
    </div>

    <!-- Skeleton Loading State -->
    <template v-if="state.isHistoryLoading && !hasLiveRecords">
      <div v-for="i in 3" :key="`skel-history-${i}`" class="history-row skeleton-row-wrap">
        <span class="history-icon skeleton-shimmer" style="width: 36px; height: 36px; border-radius: 11px;"></span>
        <span class="history-meta" style="flex: 1; display: flex; flex-direction: column; gap: 6px;">
          <span class="skeleton-shimmer" style="width: 60%; height: 13px; border-radius: 4px;"></span>
          <span class="skeleton-shimmer" style="width: 38%; height: 10px; border-radius: 4px;"></span>
        </span>
        <span class="history-amount" style="display: flex; flex-direction: column; align-items: flex-end; gap: 6px;">
          <span class="skeleton-shimmer" style="width: 52px; height: 13px; border-radius: 4px;"></span>
          <span class="skeleton-shimmer" style="width: 32px; height: 10px; border-radius: 4px;"></span>
        </span>
      </div>
    </template>

    <!-- Live Records Mode -->
    <template v-else-if="hasLiveRecords">
      <TransitionGroup name="list-glide" tag="div" :class="inDialog ? 'modal-list-scroll' : 'history-list'">
        <div v-if="displayEntries.length === 0" key="empty-filtered" class="empty-state compact-empty">
          ရွေးချယ်ထားသော အမျိုးအစားတွင် မှတ်တမ်းမရှိသေးပါခင်ဗျာ။
        </div>
        <div v-for="entry in displayEntries" :key="entry.key" class="history-row">
          <span
            class="history-icon"
            :class="{
              violet: entry.kind === 'purchase',
              amber: entry.badgeTone === 'pending',
              negative: entry.badgeTone === 'rejected' || entry.badgeTone === 'expired',
            }"
          >
            <SvgIcon
              :name="
                entry.kind === 'purchase'
                  ? 'key'
                  : entry.badgeTone === 'approved'
                    ? 'check'
                    : entry.badgeTone === 'pending'
                      ? 'clock'
                      : 'info'
              "
            />
          </span>
          <span class="history-meta">
            <strong>{{ entry.title }}</strong>
            <small>{{ entry.subtitle }}</small>
          </span>
          <span class="history-amount" :class="entry.amountTone === 'positive' ? 'positive' : 'negative'">
            {{ entry.amountText }}
            <span class="history-status-pill" :class="`is-${entry.badgeTone}`">{{ entry.badgeText }}</span>
          </span>
        </div>
      </TransitionGroup>

      <button
        v-if="!inDialog && interactive && totalCount > 5"
        type="button"
        class="list-more-foot"
        @click="openDialog({ kind: 'history' })"
      >
        <span>ကျန်ရှိသော မှတ်တမ်း {{ totalCount - 5 }} ခုအား ကြည့်ရှုရန်</span>
        <SvgIcon name="arrow-right" />
      </button>
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
