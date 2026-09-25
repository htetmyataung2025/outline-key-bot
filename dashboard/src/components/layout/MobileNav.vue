<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { triggerHaptic } from '@/api'
import { NBadge } from 'naive-ui'
import {
  SpeedometerOutline,
  ReceiptOutline,
  KeyOutline,
  GiftOutline,
  PeopleOutline,
} from '@vicons/ionicons5'

const props = defineProps<{
  pendingSlipsCount: number
}>()

const route = useRoute()
const router = useRouter()

const navItems = computed(() => [
  { path: '/overview', label: 'Overview', icon: SpeedometerOutline },
  { path: '/slips', label: 'Slips', icon: ReceiptOutline, badge: props.pendingSlipsCount },
  { path: '/keys', label: 'Keys', icon: KeyOutline },
  { path: '/redeems', label: 'Redeem', icon: GiftOutline },
  { path: '/customers', label: 'Users', icon: PeopleOutline },
])

function navigate(path: string) {
  triggerHaptic('light')
  router.push(path)
}
</script>

<template>
  <nav class="mobile-nav">
    <button
      v-for="item in navItems"
      :key="item.path"
      class="mobile-nav-item"
      :class="{ active: route.path.startsWith(item.path) }"
      @click="navigate(item.path)"
    >
      <div class="icon-wrap">
        <component :is="item.icon" class="mobile-icon" />
        <NBadge
          v-if="item.badge && item.badge > 0"
          :value="item.badge"
          type="warning"
          class="badge-dot"
          :dot="true"
        />
      </div>
      <span class="item-label">{{ item.label }}</span>
    </button>
  </nav>
</template>

<style scoped>
.mobile-nav {
  position: fixed;
  bottom: 0;
  left: 0;
  right: 0;
  height: 60px;
  background-color: #0f172a;
  border-top: 1px solid #334155;
  display: flex;
  align-items: center;
  justify-content: space-around;
  z-index: 1000;
  padding-bottom: env(safe-area-inset-bottom, 0px);
}

.mobile-nav-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: transparent;
  border: none;
  color: #64748b;
  gap: 4px;
  padding: 6px 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  flex: 1;
}

.mobile-nav-item.active {
  color: #10b981;
}

.icon-wrap {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mobile-icon {
  width: 20px;
  height: 20px;
}

.badge-dot {
  position: absolute;
  top: -2px;
  right: -6px;
}

.item-label {
  font-size: 10px;
  font-weight: 500;
}
</style>
