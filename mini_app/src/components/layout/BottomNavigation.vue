<script setup lang="ts">
import SvgIcon from '../ui/SvgIcon.vue'
import { tabs } from '../../data/demo'
import type { TabId } from '../../types'
defineProps<{ active: TabId }>()
const emit = defineEmits<{ select: [tab: TabId] }>()
</script>
<template>
  <nav id="bottom-nav" class="bottom-nav" aria-label="Main navigation"><button v-for="tab in tabs" :key="tab.id" class="nav-item" :class="{ active: active === tab.id }" :data-tab="tab.id" :aria-label="tab.title" :aria-current="active === tab.id ? 'page' : undefined" @click="emit('select', tab.id)"><SvgIcon :name="tab.icon" /><span>{{ tab.shortTitle }}</span></button></nav>
</template>
