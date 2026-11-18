<script setup lang="ts">
import { computed, nextTick, onMounted, onScopeDispose, ref, watch } from 'vue'
import type { Component } from 'vue'
import IconSprite from './components/ui/IconSprite.vue'
import AppHeader from './components/layout/AppHeader.vue'
import BottomNavigation from './components/layout/BottomNavigation.vue'
import ToastNotification from './components/ui/ToastNotification.vue'
import AppDialogs from './components/AppDialogs.vue'
import OverviewView from './views/OverviewView.vue'
import KeysView from './views/KeysView.vue'
import ShopView from './views/ShopView.vue'
import RewardsView from './views/RewardsView.vue'
import { provideMiniApp } from './composables/useMiniApp'
import { useReducedMotion } from './composables/useReducedMotion'
import { useTelegram } from './composables/useTelegram'
import { tabs } from './data/demo'
import type { TabId } from './types'

const TAB_ORDER: Record<TabId, number> = { overview: 0, keys: 1, shop: 2, history: 3 }

const app = provideMiniApp()
const { state, setTab, openDialog, refresh } = app
useTelegram(app)
const reduced = useReducedMotion()
const screen = ref<HTMLElement | null>(null)
const views: Record<TabId, Component> = { overview: OverviewView, keys: KeysView, shop: ShopView, history: RewardsView }
const screenLabel = computed(() => tabs.find(tab => tab.id === state.tab)?.title ?? 'Overview')

const tabDirection = ref<'forward' | 'backward'>('forward')
const tabTransitionName = computed(() => (reduced.value ? 'tab-reduced' : `tab-${tabDirection.value}`))
let pendingLeaveScrollTop = 0

watch(
  () => state.tab,
  async (nextTab, prevTab) => {
    if (prevTab && nextTab !== prevTab) {
      tabDirection.value = TAB_ORDER[nextTab] >= TAB_ORDER[prevTab] ? 'forward' : 'backward'
    }
    pendingLeaveScrollTop = screen.value?.scrollTop ?? 0
    const fromNavigation = document.activeElement?.matches('.nav-item, .index-item')
    await nextTick()
    if (screen.value && screen.value.scrollTop > 0) {
      screen.value.scrollTop = 0
    }
    if (screen.value && !fromNavigation) {
      screen.value.focus({ preventScroll: true })
    }
  },
  { flush: 'pre' },
)

function onBeforeTabLeave(el: Element) {
  if (el instanceof HTMLElement && pendingLeaveScrollTop > 0) {
    el.style.top = `${-pendingLeaveScrollTop}px`
  }
}

function onAfterTabLeave(el: Element) {
  if (el instanceof HTMLElement) {
    el.style.removeProperty('top')
  }
  pendingLeaveScrollTop = 0
}

const isDocHidden = ref(typeof document !== 'undefined' ? document.visibilityState !== 'visible' : false)
function syncDocVisibility() {
  isDocHidden.value = document.visibilityState !== 'visible'
}
onMounted(() => {
  if (typeof document !== 'undefined') {
    document.addEventListener('visibilitychange', syncDocVisibility)
  }
})
onScopeDispose(() => {
  if (typeof document !== 'undefined') {
    document.removeEventListener('visibilitychange', syncDocVisibility)
  }
})

function selectTab(tab: TabId) {
  if (tab === state.tab) screen.value?.scrollTo({ top: 0, behavior: reduced.value ? 'auto' : 'smooth' })
  else setTab(tab)
}
</script>
<template>
  <IconSprite />
  <div class="tma-shell">
    <main class="app-frame" :class="{ 'has-modal': state.dialog !== null, 'is-bg-paused': isDocHidden }" role="main">
      <AppHeader
        :user="state.user"
        :loading="state.isManualRefreshing"
        :inert="state.dialog !== null"
        @refresh="refresh"
        @profile="openDialog({ kind: 'profile' })"
      />
      <div id="screen-content" ref="screen" class="screen-content" role="region" :aria-label="screenLabel" tabindex="-1" :inert="state.dialog !== null">
        <div class="screen-stage">
          <Transition
            :name="tabTransitionName"
            @before-leave="onBeforeTabLeave"
            @after-leave="onAfterTabLeave"
            @leave-cancelled="onAfterTabLeave"
          >
            <KeepAlive>
              <component :is="views[state.tab]" :key="state.tab" />
            </KeepAlive>
          </Transition>
        </div>
      </div>
      <BottomNavigation :active="state.tab" :inert="state.dialog !== null" @select="selectTab" />
      <ToastNotification :toast="state.toast" />
      <AppDialogs />
    </main>
  </div>
</template>
