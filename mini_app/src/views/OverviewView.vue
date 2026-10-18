<script setup lang="ts">
import { ref, onMounted, onScopeDispose } from 'vue'
import WalletCard from '../components/overview/WalletCard.vue'
import KeyStack from '../components/overview/KeyStack.vue'
import QuickAccess from '../components/overview/QuickAccess.vue'
import SvgIcon from '../components/ui/SvgIcon.vue'
import { useMiniApp } from '../composables/useMiniApp'

const { state, activeKeys, refresh, setTab } = useMiniApp()

const pullY = ref(0)
const isRefreshing = ref(false)
const readyToRelease = ref(false)
let startY = 0
let tracking = false

function onTouchStart(e: TouchEvent) {
  const scrollEl = document.getElementById('screen-content')
  if (scrollEl && scrollEl.scrollTop > 5) return
  if (isRefreshing.value) return
  const touch = e.touches[0]
  if (!touch) return

  startY = touch.clientY
  tracking = true
}

function onTouchMove(e: TouchEvent) {
  if (!tracking) return
  const touch = e.touches[0]
  if (!touch) return
  const currentY = touch.clientY
  const diff = currentY - startY

  if (diff > 0) {
    pullY.value = Math.min(80, diff * 0.45)
    if (pullY.value > 52 && !readyToRelease.value) {
      readyToRelease.value = true
      window.Telegram?.WebApp?.HapticFeedback?.impactOccurred?.('light')
    } else if (pullY.value <= 52 && readyToRelease.value) {
      readyToRelease.value = false
    }
  } else {
    pullY.value = 0
    tracking = false
  }
}

async function onTouchEnd() {
  if (!tracking) return
  tracking = false

  if (readyToRelease.value && !isRefreshing.value) {
    isRefreshing.value = true
    pullY.value = 46
    try {
      await refresh()
    } finally {
      setTimeout(() => {
        isRefreshing.value = false
        pullY.value = 0
        readyToRelease.value = false
      }, 300)
    }
  } else {
    pullY.value = 0
    readyToRelease.value = false
  }
  startY = 0
}

onMounted(() => {
  const container = document.getElementById('screen-content')
  if (container) {
    container.addEventListener('touchstart', onTouchStart, { passive: true })
    container.addEventListener('touchmove', onTouchMove, { passive: true })
    container.addEventListener('touchend', onTouchEnd)
    container.addEventListener('touchcancel', onTouchEnd)
  }
})

onScopeDispose(() => {
  const container = document.getElementById('screen-content')
  if (container) {
    container.removeEventListener('touchstart', onTouchStart)
    container.removeEventListener('touchmove', onTouchMove)
    container.removeEventListener('touchend', onTouchEnd)
    container.removeEventListener('touchcancel', onTouchEnd)
  }
})
</script>

<template>
  <div class="overview-view min-w-0">
    <!-- Pull-to-Refresh Indicator -->
    <div
      class="pull-refresh-bar"
      :style="{
        height: `${pullY}px`,
        opacity: pullY > 10 ? Math.min(1, pullY / 35) : 0,
      }"
    >
      <div class="pull-refresh-inner">
        <SvgIcon
          name="refresh"
          class="pull-refresh-icon"
          :class="{ 'is-spinning': isRefreshing, 'is-ready': readyToRelease && !isRefreshing }"
        />
        <span class="pull-refresh-label">
          {{ isRefreshing ? 'အချက်အလက်များ ရယူနေပါသည်...' : readyToRelease ? 'လွှတ်ပြီး Refresh လုပ်ပါ' : 'ဆွဲချပြီး Refresh လုပ်ပါ' }}
        </span>
      </div>
    </div>

    <!-- 1. Wallet Balance Card -->
    <WalletCard />

    <!-- 2. Active Key Snapshot (Loading Skeleton / Real KeyStack / Empty State) -->
    <template v-if="(state.isInitialLoading || state.loading) && state.keys.length === 0">
      <section class="snapshot-section" aria-label="Loading key snapshot">
        <div class="section-title-row">
          <span class="section-title">Active key snapshot</span>
        </div>
        <div class="card skeleton-card">
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
      </section>
    </template>
    <template v-else-if="activeKeys.length > 0">
      <KeyStack v-model="state.selectedKeyId" :keys="activeKeys" />
    </template>
    <template v-else>
      <section class="snapshot-section" aria-label="No active keys">
        <div class="section-title-row">
          <span class="section-title">Active key snapshot</span>
        </div>
        <div class="empty-state card">
          <div class="empty-icon"><SvgIcon name="key" /></div>
          <div class="empty-title">Active ဖြစ်နေသော Key မရှိသေးပါ</div>
          <p class="empty-desc">မြန်နှုန်းမြင့် Outline VPN အသုံးပြုရန် Plan တစ်ခုကို စတင်ဝယ်ယူလိုက်ပါ</p>
          <button class="primary-btn" style="margin-top: 14px; width: 100%; justify-content: center;" @click="setTab('shop')">
            <SvgIcon name="zap" />Plan များ ကြည့်ရှုရန်
          </button>
        </div>
      </section>
    </template>

    <!-- 3. Quick Access Shortcuts -->
    <QuickAccess />
  </div>
</template>
