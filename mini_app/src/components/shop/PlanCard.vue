<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import type { Plan, PlanName } from '../../types'
import { formatNumber } from '../../utils/format'
defineProps<{ plan: Plan; selected: boolean }>()
const emit = defineEmits<{ select: [name: PlanName] }>()
</script>
<template>
  <article class="plan-card" :class="{ featured: plan.name === 'Basic', selected }" :data-plan="plan.name" @click="emit('select', plan.name)">
    <span v-if="plan.name === 'Basic'" class="plan-popular">MOST POPULAR</span><div class="plan-header"><span class="plan-symbol"><SvgIcon :name="plan.icon" /></span><span class="selection-dot"><SvgIcon v-if="selected" name="check" /></span></div>
    <div class="plan-title">{{ plan.name }}</div><div class="plan-data">{{ plan.quota }} GB</div><div class="plan-price">{{ plan.price === null ? '—' : formatNumber(plan.price) }} <small>Ks</small></div><p class="plan-description">{{ plan.description }}</p>
    <button class="plan-select" :data-plan="plan.name" :aria-pressed="selected"><SvgIcon v-if="selected" name="check" />{{ selected ? 'ရွေးထားသည်' : 'ရွေးချယ်ရန်' }}</button>
  </article>
</template>
