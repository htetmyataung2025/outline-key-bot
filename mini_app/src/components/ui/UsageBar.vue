<script setup lang="ts">
import { onMounted, onScopeDispose, ref, watch } from 'vue'
import { clamp } from '../../utils/format'
const props = withDefaults(defineProps<{ percent: number; label: string; kind?: 'snapshot' | 'key'; active?: boolean }>(), { kind: 'snapshot', active: true })
const width = ref(0)
let initialized = false
let mounted = false
let firstFrame = 0, secondFrame = 0
function update() { if (props.active || initialized) { width.value = clamp(props.percent); initialized = true } }
onMounted(() => { mounted = true; firstFrame = requestAnimationFrame(() => { secondFrame = requestAnimationFrame(update) }) })
watch(() => [props.percent, props.active], () => { if (mounted) update() }, { flush: 'post' })
onScopeDispose(() => { cancelAnimationFrame(firstFrame); cancelAnimationFrame(secondFrame) })
</script>
<template>
  <div :class="kind === 'key' ? 'key-progress' : 'usage-progress'" role="progressbar" :aria-label="label" :aria-valuenow="clamp(percent)" :aria-valuemin="0" :aria-valuemax="100">
    <span data-usage-fill :data-target="clamp(percent)" :style="{ width: `${width}%` }" />
  </div>
</template>
