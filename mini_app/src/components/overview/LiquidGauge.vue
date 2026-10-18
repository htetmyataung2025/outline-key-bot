<script setup lang="ts">
import { computed, onMounted, onScopeDispose, ref, watch } from 'vue'
import { clamp } from '../../utils/format'
import { useReducedMotion } from '../../composables/useReducedMotion'
const props = withDefaults(defineProps<{ percent: number; label: string; active?: boolean }>(), { active: true })
const reduced = useReducedMotion()
const target = computed(() => clamp(Math.round(props.percent)))
const shown = ref(0)
const offset = ref('112%')
let initialized = false, mounted = false
let numberFrame = 0, firstFrame = 0, secondFrame = 0
const wavePath = 'M0 10 C12.5 1 37.5 1 50 10 S87.5 19 100 10 S137.5 1 150 10 S187.5 19 200 10 V32 H0Z'
function update() {
  if (!props.active && !initialized) return
  initialized = true
  cancelAnimationFrame(numberFrame)
  const finish = target.value, start = shown.value
  offset.value = `${finish === 0 ? 112 : finish === 100 ? -12 : 100 - finish}%`
  if (reduced.value || start === finish) { shown.value = finish; return }
  const started = performance.now()
  const tick = (now: number) => {
    const t = Math.min(1, (now - started) / 1250)
    shown.value = Math.round(start + (finish - start) * (1 - Math.pow(1 - t, 3)))
    if (t < 1) numberFrame = requestAnimationFrame(tick)
  }
  numberFrame = requestAnimationFrame(tick)
}
onMounted(() => { mounted = true; firstFrame = requestAnimationFrame(() => { secondFrame = requestAnimationFrame(update) }) })
watch(() => [props.percent, props.active, reduced.value], () => { if (mounted) update() }, { flush: 'post' })
onScopeDispose(() => { cancelAnimationFrame(numberFrame); cancelAnimationFrame(firstFrame); cancelAnimationFrame(secondFrame) })
</script>
<template>
  <div class="liquid-gauge" :class="{ 'is-full': target === 100, 'is-empty': target === 0 }" role="progressbar" :aria-label="label" :aria-valuemin="0" :aria-valuemax="100" :aria-valuenow="target" :data-target="target" :style="{ '--liquid-offset': offset }">
    <div class="liquid-vessel" aria-hidden="true">
      <div class="liquid-level"><div class="liquid-body" />
        <svg class="liquid-wave wave-back" viewBox="0 0 200 20" preserveAspectRatio="none"><path :d="wavePath" /></svg>
        <svg class="liquid-wave wave-front" viewBox="0 0 200 20" preserveAspectRatio="none"><path :d="wavePath" /></svg>
        <span class="liquid-bubble bubble-one" /><span class="liquid-bubble bubble-two" />
      </div><div class="liquid-glass" />
    </div>
    <div class="liquid-readout" aria-hidden="true"><strong><span data-percent-number>{{ shown }}</span><small>%</small></strong><span class="liquid-used-label">USED</span></div>
  </div>
</template>
