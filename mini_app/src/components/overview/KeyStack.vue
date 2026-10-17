<script setup lang="ts">
import { computed } from 'vue'
import type { ComponentPublicInstance, CSSProperties } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import SnapshotCard from './SnapshotCard.vue'
import { paletteAt } from '../../data/demo'
import { useKeyStack } from '../../composables/useKeyStack'
import { useMiniApp } from '../../composables/useMiniApp'
import { twoDigits } from '../../utils/format'
import type { VpnKey } from '../../types'
const props = defineProps<{ keys: readonly VpnKey[] }>()
const selectedId = defineModel<string | null>({ required: true })
const keys = computed<readonly VpnKey[]>(() => props.keys)
const { setTab } = useMiniApp()
const { stage, isDragging, announcement, selectedIndex, depth, setCardRef, select, onPointerDown, onPointerMove, onPointerUp, onWheel, onKeydown } = useKeyStack(keys, selectedId)
function setStage(node: Element | ComponentPublicInstance | null) { stage.value = node instanceof HTMLElement ? node : null }
function paletteStyle(index: number): CSSProperties {
  const p = paletteAt(index)
  return { '--key-accent': p.accent, '--key-accent-2': p.second, '--key-rgb': p.rgb, '--fluid-top': p.top, '--fluid-bottom': p.bottom, '--key-bg': p.bg }
}
</script>
<template>
  <section class="snapshot-section" aria-labelledby="snapshot-title" :data-key-count="keys.length" :style="{ '--active-dot': paletteAt(selectedIndex).accent }">
    <div class="section-title-row"><span id="snapshot-title" class="section-title">Active key snapshot<span v-if="keys.length" class="snapshot-total">{{ keys.length }}</span></span><button class="section-link" @click="setTab('keys')">အားလုံးကြည့်ရန်<SvgIcon name="arrow-right" /></button></div>
    <template v-if="keys.length">
      <div class="snapshot-stack" role="region" aria-roledescription="carousel" aria-label="Active VPN keys">
        <div :ref="setStage" class="snapshot-stage" :class="{ 'is-dragging': isDragging }" tabindex="0" :aria-label="keys.length > 1 ? 'Swipe up for next key, down for previous key. Arrow Up and Arrow Down also work.' : 'Active VPN key'" aria-describedby="stack-instructions" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="onPointerUp" @wheel="onWheel" @keydown="onKeydown">
          <article v-for="(entry, index) in keys" :key="entry.id" :ref="node => setCardRef(entry.id, node)" class="hero-key card snapshot-card" :data-key-id="entry.id" :data-slide-index="index" :data-depth="depth(index)" :style="paletteStyle(index)" role="group" aria-roledescription="slide" :aria-label="`Key ${index + 1} of ${keys.length}: ${entry.plan} · ${entry.location}`" :aria-hidden="depth(index) !== 0" :inert="depth(index) !== 0"><SnapshotCard :entry="entry" :active="depth(index) === 0" /></article>
        </div>
        <div v-if="keys.length > 1" class="stack-pagination" aria-label="Choose active key"><button v-for="(entry, index) in keys" :key="entry.id" class="stack-dot" :class="{ active: index === selectedIndex }" :data-snapshot-index="index" :aria-label="`Key ${index + 1}: ${entry.plan} · ${entry.location}`" :aria-current="index === selectedIndex ? 'true' : undefined" @click="select(index)"><span /></button></div>
      </div>
      <div v-if="keys.length > 1" id="stack-instructions" class="stack-footer"><span class="stack-swipe-hint"><SvgIcon name="swipe" />အပေါ် / အောက် ဆွဲကြည့်ပါ</span><span class="stack-counter"><b id="snapshot-current">{{ twoDigits(selectedIndex + 1) }}</b><span>/ {{ twoDigits(keys.length) }}</span></span></div><span v-else id="stack-instructions" class="sr-only">One active key</span>
      <div class="sr-only" aria-live="polite" aria-atomic="true">{{ announcement }}</div>
    </template>
    <div v-else class="empty-state"><div class="empty-icon"><SvgIcon name="key" /></div>Active ဖြစ်နေသော key မရှိသေးပါ။<br /><button class="section-link" @click="setTab('shop')">Plan များကြည့်ရန်<SvgIcon name="arrow-right" /></button></div>
  </section>
</template>
