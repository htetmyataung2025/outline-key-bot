<script setup lang="ts">
import SvgIcon from './SvgIcon.vue'
import type { Toast } from '../../types'
defineProps<{ toast: Toast }>()
</script>
<template>
  <div id="toast" class="toast" :class="{ show: toast.visible }" role="status" aria-live="polite" aria-atomic="true"><SvgIcon :name="toast.icon" /><span>{{ toast.message }}</span></div>
</template>
