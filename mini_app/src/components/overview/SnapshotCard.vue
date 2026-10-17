<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import UsageBar from '../ui/UsageBar.vue'
import LiquidGauge from './LiquidGauge.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber, percentUsed } from '../../utils/format'
import type { VpnKey } from '../../types'
const props = defineProps<{ entry: VpnKey; active: boolean }>()
const { openDialog, copyKey } = useMiniApp()
const percent = computed(() => percentUsed(props.entry))
const status = computed(() => props.entry.connected ? 'Connected' : props.entry.status === 'expiring' ? 'Expiring' : 'Active')
</script>
<template>
  <div class="snapshot-card-content">
    <div class="hero-key-head"><span class="status-pill" :class="{ expiring: entry.status === 'expiring' }"><span class="status-dot" />{{ status }}</span><span class="server-mini"><SvgIcon name="globe" />{{ entry.country }} · {{ entry.location }}</span><button class="more-btn" data-action="key-preview" :data-key-id="entry.id" :aria-label="`${entry.plan} key details and animation preview`" @click="openDialog({ kind: 'usage', keyId: entry.id })"><SvgIcon name="more" /></button></div>
    <div class="hero-key-body">
      <LiquidGauge :percent="percent" :label="`${entry.plan} plan data used`" :active="active" />
      <div class="usage-info"><div class="usage-plan">{{ entry.plan }} Plan · {{ entry.quota }} GB</div><div class="usage-value"><b data-used-number>{{ formatNumber(entry.used) }} GB</b> <span>/ {{ entry.quota }} GB</span></div><UsageBar :percent="percent" :label="`${entry.plan} data used`" :active="active" /><div class="expiry-row"><SvgIcon name="clock" /><span>သက်တမ်းကျန်</span><span class="expiry-tag">{{ entry.left }}</span></div></div>
    </div>
    <div class="hero-actions"><button class="action-btn" data-action="copy" :data-key="entry.key" :aria-label="`Copy ${entry.plan} ${entry.location} key`" @click="copyKey(entry.key)"><SvgIcon name="copy" />Copy Key</button><button class="action-btn primary-lite" data-action="connect" :data-key-id="entry.id" @click="openDialog({ kind: 'connect', keyId: entry.id })"><SvgIcon name="zap" />Open in Outline</button></div>
  </div>
</template>
