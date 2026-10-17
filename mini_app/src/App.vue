<script setup lang="ts">
import { computed, nextTick, onScopeDispose, ref, watch } from 'vue'
import type { Component } from 'vue'
import IconSprite from './components/ui/IconSprite.vue'
import AppIntro from './components/layout/AppIntro.vue'
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
const { state, setTab, showToast, openDialog } = app
useTelegram(app)
const reduced = useReducedMotion()
const screen = ref<HTMLElement | null>(null)
const views: Record<TabId, Component> = { overview: OverviewView, keys: KeysView, shop: ShopView, history: RewardsView }
const screenLabel = computed(() => tabs.find(tab => tab.id === state.tab)?.title ?? 'Overview')
let entryAnimation: Animation | undefined
watch(() => state.tab, async () => {
  const fromNavigation = document.activeElement?.matches('.nav-item, .index-item')
  await nextTick()
  if (screen.value) {
    screen.value.scrollTop = 0
    entryAnimation?.cancel()
    if (!reduced.value) entryAnimation = screen.value.animate([{ opacity: .4, transform: 'translateY(6px)' }, { opacity: 1, transform: 'translateY(0)' }], { duration: 240, easing: 'ease' })
    if (!fromNavigation) screen.value.focus({ preventScroll: true })
  }
})
function selectTab(tab: TabId) { if (tab === state.tab) screen.value?.scrollTo({ top: 0, behavior: reduced.value ? 'auto' : 'smooth' }); else setTab(tab) }
onScopeDispose(() => entryAnimation?.cancel())
</script>
<template>
  <IconSprite />
  <main class="showcase">
    <AppIntro :active="state.tab" :inert="state.dialog !== null" @select="selectTab" />
    <section class="device-wrap" aria-label="Interactive Mini App preview"><div class="device-glow" aria-hidden="true" />
      <div class="app-frame">
        <AppHeader :user="state.user" :inert="state.dialog !== null" @notifications="showToast('အသိပေးချက်အသစ် မရှိသေးပါ', 'bell')" @profile="openDialog({ kind: 'profile' })" />
        <div id="screen-content" ref="screen" class="screen-content" role="region" :aria-label="screenLabel" tabindex="-1" :inert="state.dialog !== null"><component :is="views[state.tab]" :key="state.tab" /></div>
        <BottomNavigation :active="state.tab" :inert="state.dialog !== null" @select="selectTab" />
        <ToastNotification :toast="state.toast" /><AppDialogs />
      </div>
    </section>
  </main>
</template>
