<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
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
const app = provideMiniApp()
const { state, setTab, openDialog, refresh } = app
useTelegram(app)
const reduced = useReducedMotion()
const screen = ref<HTMLElement | null>(null)
const views: Record<TabId, Component> = { overview: OverviewView, keys: KeysView, shop: ShopView, history: RewardsView }
const screenLabel = computed(() => tabs.find(tab => tab.id === state.tab)?.title ?? 'Overview')
watch(() => state.tab, async () => {
  const fromNavigation = document.activeElement?.matches('.nav-item, .index-item')
  await nextTick()
  if (screen.value && screen.value.scrollTop > 0) {
    screen.value.scrollTop = 0
  }
  if (screen.value && !fromNavigation) {
    screen.value.focus({ preventScroll: true })
  }
})
function selectTab(tab: TabId) { if (tab === state.tab) screen.value?.scrollTo({ top: 0, behavior: reduced.value ? 'auto' : 'smooth' }); else setTab(tab) }
</script>
<template>
  <IconSprite />
  <div class="tma-shell">
    <main class="app-frame" role="main">
      <AppHeader
        :user="state.user"
        :loading="state.isManualRefreshing"
        :inert="state.dialog !== null"
        @refresh="refresh"
        @profile="openDialog({ kind: 'profile' })"
      />
      <div id="screen-content" ref="screen" class="screen-content" role="region" :aria-label="screenLabel" tabindex="-1" :inert="state.dialog !== null">
        <Transition name="tab-fade" mode="out-in">
          <KeepAlive>
            <component :is="views[state.tab]" :key="state.tab" />
          </KeepAlive>
        </Transition>
      </div>
      <BottomNavigation :active="state.tab" :inert="state.dialog !== null" @select="selectTab" />
      <ToastNotification :toast="state.toast" />
      <AppDialogs />
    </main>
  </div>
</template>
