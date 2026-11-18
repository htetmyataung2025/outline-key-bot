<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import UsageBar from '../ui/UsageBar.vue'
import { useMiniApp } from '../../composables/useMiniApp'
import { formatNumber, percentUsed } from '../../utils/format'
import type { VpnKey } from '../../types'
const props = defineProps<{ entry: VpnKey }>()
const { copyKey, openDialog, setTab } = useMiniApp()
const percent = computed(() => percentUsed(props.entry))
const label = computed(() => ({ active: 'Active', expiring: 'Expiring', expired: 'Expired' })[props.entry.status])
</script>
<template>
  <article class="key-card card" :data-key-card="entry.status">
    <div class="key-card-top"><div class="server-info"><div class="server-flag" aria-hidden="true"><SvgIcon name="globe" /></div><div><div class="server-name">{{ entry.server }}<span class="section-caption"> · {{ entry.country }}</span></div><div class="server-sub">{{ entry.location }} · Multi-VPN compatible</div></div></div><span class="status-pill" :class="entry.status"><span class="status-dot" />{{ label }}</span></div>
    <div class="key-plan-line"><div><div class="plan-name">{{ entry.plan }} Plan</div><div class="plan-quota">{{ entry.quota > 0 ? `${entry.quota} GB data pack` : 'Unlimited data pack' }}</div></div><div class="expiry-date">{{ entry.expires }}<small>{{ entry.left }}</small></div></div>
    <div class="key-usage-label"><span>Data usage</span><b>{{ formatNumber(entry.used) }} GB used <span>/ {{ entry.quota > 0 ? `${entry.quota} GB` : 'Unlimited' }}</span></b></div><UsageBar kind="key" :percent="percent" :label="`${entry.server} data used`" />
    <div v-if="entry.status === 'expired'" class="key-footnote"><span>ဤ key သက်တမ်းကုန်ဆုံးသွားပါပြီ</span><button class="section-link" @click="setTab('shop')">Plan အသစ်ဝယ်ရန်<SvgIcon name="arrow-right" /></button></div>
    <div v-else class="key-actions">
      <button class="key-action" data-action="copy" :aria-label="`Copy ${entry.server} key`" @click="copyKey(entry.key)"><SvgIcon name="copy" /><span>Copy Key</span></button>
      <button class="key-action" data-action="connect" @click="openDialog({ kind: 'connect', keyId: entry.id })"><SvgIcon name="zap" /><span>Available VPN</span></button>
      <button class="key-action" data-action="replace" @click="openDialog({ kind: 'replace', keyId: entry.id })"><SvgIcon name="refresh" /><span>Key လဲရန်</span></button>
    </div>
  </article>
</template>
