<script setup lang="ts">
import { computed } from 'vue'
import SvgIcon from '../ui/SvgIcon.vue'
import { tabs } from '../../data/demo'
import type { TabId } from '../../types'

const props = defineProps<{ active: TabId }>()
const emit = defineEmits<{ select: [tab: TabId] }>()

const activeIndex = computed(() => Math.max(0, tabs.findIndex(t => t.id === props.active)))
</script>
<template>
  <nav id="bottom-nav" class="bottom-nav" aria-label="Main navigation">
    <div class="bottom-nav-track" :style="{ '--active-idx': activeIndex }">
      <span class="nav-active-glider" aria-hidden="true" />
      <button
        v-for="tab in tabs"
        :key="tab.id"
        class="nav-item"
        :class="{ active: active === tab.id }"
        :data-tab="tab.id"
        :aria-label="tab.title"
        :aria-current="active === tab.id ? 'page' : undefined"
        @click="emit('select', tab.id)"
      >
        <SvgIcon :name="tab.icon" />
        <span>{{ tab.shortTitle }}</span>
      </button>
    </div>
  </nav>
</template>
