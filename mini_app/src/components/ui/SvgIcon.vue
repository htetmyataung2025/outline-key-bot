<script setup lang="ts">
import type { IconName } from '../../types/icons'
defineProps<{ name: IconName }>()
</script>

<template>
  <svg class="icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false">
    <use :href="`#i-${name}`" />
  </svg>
</template>
