<script setup lang="ts">
import KeyCard from '../components/keys/KeyCard.vue'
import ScreenHeading from '../components/ui/ScreenHeading.vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import { useMiniApp } from '../composables/useMiniApp'
import type { KeyFilter } from '../types'
const { state, visibleKeys, setTab, showToast, bootstrap } = useMiniApp()
const filters: { id: KeyFilter; label: string }[] = [{ id: 'all', label: 'All keys' }, { id: 'active', label: 'Active' }, { id: 'expiring', label: 'Expiring' }, { id: 'expired', label: 'Expired' }]

function selectFilter(filterId: KeyFilter) {
  if (state.filter !== filterId) {
    window.Telegram?.WebApp?.HapticFeedback?.selectionChanged?.()
    state.filter = filterId
  }
}

async function handleRefresh() {
  window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
  showToast('Key အချက်အလက်များ ရယူနေပါသည်...', 'refresh')
  await bootstrap()
}
</script>
<template>
  <div>
    <ScreenHeading kicker="Your connections" title="My Keys" description="VPN key တွေနဲ့ data အသုံးပြုမှုကို စီမံပါ" icon="key" />
    <div class="toolbar-row">
      <div class="filter-row" aria-label="Filter keys">
        <button
          v-for="filter in filters"
          :key="filter.id"
          class="filter-chip"
          :class="{ active: state.filter === filter.id }"
          :data-filter="filter.id"
          :aria-pressed="state.filter === filter.id"
          @click="selectFilter(filter.id)"
        >
          {{ filter.label }}{{ filter.id === 'all' ? ` · ${state.keys.length}` : '' }}
        </button>
      </div>
      <button class="icon-button" aria-label="Refresh keys" @click="handleRefresh">
        <SvgIcon name="refresh" />
      </button>
    </div>
    <KeyCard v-for="entry in visibleKeys" :key="entry.id" :entry="entry" />
    <div v-if="!visibleKeys.length" class="empty-state">
      <div class="empty-icon"><SvgIcon name="key" /></div>
      {{ state.keys.length === 0 ? 'VPN Key မရှိသေးပါခင်ဗျာ။' : 'ဒီအမျိုးအစားထဲမှာ key မရှိသေးပါ။' }}<br />
      <button class="section-link" style="margin-top: 6px;" @click="setTab('shop')">
        Plan များ ကြည့်ရှုမည်<SvgIcon name="arrow-right" />
      </button>
    </div>
    <button class="soft-btn new-key-btn" @click="setTab('shop')"><SvgIcon name="plus" />Key အသစ်ရယူရန်</button>
  </div>
</template>
