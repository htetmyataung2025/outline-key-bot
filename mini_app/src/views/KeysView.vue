<script setup lang="ts">
import { onActivated, onDeactivated, ref } from 'vue'
import KeyCard from '../components/keys/KeyCard.vue'
import ScreenHeading from '../components/ui/ScreenHeading.vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import { useMiniApp } from '../composables/useMiniApp'
import type { KeyFilter } from '../types'
const { state, visibleKeys, setTab, showToast, refresh } = useMiniApp()
const isTabInactive = ref(false)
onActivated(() => { isTabInactive.value = false })
onDeactivated(() => { isTabInactive.value = true })
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
  await refresh()
}
</script>
<template>
  <div :class="{ 'is-tab-inactive': isTabInactive }">
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
      <button class="icon-button" :class="{ 'is-spinning': state.isManualRefreshing }" aria-label="Refresh keys" @click="handleRefresh">
        <SvgIcon name="refresh" />
      </button>
    </div>

    <!-- Skeleton Loading State -->
    <template v-if="state.isInitialLoading && state.keys.length === 0">
      <div v-for="i in 2" :key="`skel-key-${i}`" class="card skeleton-card" style="margin-bottom: 14px;">
        <div class="skeleton-header">
          <span class="skeleton-pill"></span>
          <span class="skeleton-pill"></span>
        </div>
        <div class="skeleton-body">
          <div class="skeleton-gauge"></div>
          <div class="skeleton-lines">
            <div class="skeleton-line" style="width: 50%;"></div>
            <div class="skeleton-line" style="width: 80%; height: 18px;"></div>
            <div class="skeleton-line" style="width: 100%; height: 6px;"></div>
            <div class="skeleton-line" style="width: 40%;"></div>
          </div>
        </div>
        <div class="skeleton-actions">
          <div class="skeleton-btn"></div>
          <div class="skeleton-btn"></div>
        </div>
      </div>
    </template>

    <template v-else-if="visibleKeys.length > 0">
      <TransitionGroup name="list-glide" tag="div" class="keys-list-wrap">
        <KeyCard v-for="entry in visibleKeys" :key="entry.id" :entry="entry" />
      </TransitionGroup>
    </template>

    <div v-else class="empty-state">
      <div class="empty-icon"><SvgIcon name="key" /></div>
      {{ state.keys.length === 0 ? 'VPN Key မရှိသေးပါခင်ဗျာ။' : 'ဒီအမျိုးအစားထဲမှာ key မရှိသေးပါ။' }}<br />
      <button class="section-link" style="margin-top: 6px;" @click="setTab('shop')">
        Plan များ ကြည့်ရှုမည်<SvgIcon name="arrow-right" />
      </button>
    </div>
    <button class="soft-btn new-key-btn" @click="setTab('shop')"><SvgIcon name="plus" />Key အသစ်ရယူရန်</button>
  </div>
</template>
