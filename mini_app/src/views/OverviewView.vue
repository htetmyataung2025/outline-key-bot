<script setup lang="ts">
import WalletCard from '../components/overview/WalletCard.vue'
import KeyStack from '../components/overview/KeyStack.vue'
import QuickAccess from '../components/overview/QuickAccess.vue'
import { useMiniApp } from '../composables/useMiniApp'
const { state, activeKeys } = useMiniApp()
</script>
<template>
  <div class="min-w-0"><WalletCard /><KeyStack v-model="state.selectedKeyId" :keys="activeKeys" /><QuickAccess /></div>
</template>
