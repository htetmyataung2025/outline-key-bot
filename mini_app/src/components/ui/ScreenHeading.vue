<script setup lang="ts">
import SvgIcon from './SvgIcon.vue'
import type { IconName } from '../../types/icons'
defineProps<{ kicker: string; title: string; description: string; icon: IconName }>()
</script>
<template>
  <div class="screen-head">
    <p class="kicker">{{ kicker }}</p>
    <div class="heading-line"><h2>{{ title }}</h2><span class="heading-icon"><SvgIcon :name="icon" /></span></div>
    <p>{{ description }}</p>
  </div>
</template>
