<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import type { TabId } from '../../types'
import type { IconName } from '../../types/icons'
const { navigateTo } = useMiniApp()
const links: { tab: TabId; targetId?: string; icon: IconName; label: string }[] = [
  { tab: 'shop', icon: 'bag', label: 'Plan ဝယ်ရန်' },
  { tab: 'shop', targetId: 'wallet-topup-card', icon: 'wallet', label: 'ငွေဖြည့်ရန်' },
  { tab: 'keys', icon: 'refresh', label: 'Key လဲရန်' },
  { tab: 'history', targetId: 'leaderboard-section', icon: 'trophy', label: 'Leaderboard' },
]
</script>
<template>
  <div class="section-title-row"><span class="section-title">Quick access</span><span class="section-caption">တစ်ချက်နှိပ်ပြီး သွားရန်</span></div>
  <div class="quick-grid"><button v-for="link in links" :key="link.label" class="quick-link" @click="navigateTo(link.tab, link.targetId)"><span class="quick-icon"><SvgIcon :name="link.icon" /></span><span class="quick-label">{{ link.label }}</span></button></div>
</template>
