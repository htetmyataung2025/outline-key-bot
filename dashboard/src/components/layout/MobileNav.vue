<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { triggerHaptic } from '@/api'
import { NBadge } from 'naive-ui'
import {
  SpeedometerOutline,
  ReceiptOutline,
  CartOutline,
  KeyOutline,
  GiftOutline,
  PeopleOutline,
  SettingsOutline,
} from '@vicons/ionicons5'

const props = defineProps<{
  pendingSlipsCount: number
}>()

const route = useRoute()
const router = useRouter()

const navItems = computed(() => [
  { path: '/overview', label: 'Overview', icon: SpeedometerOutline },
  { path: '/slips', label: 'Slips', icon: ReceiptOutline, badge: props.pendingSlipsCount },
  { path: '/purchases', label: 'Sales', icon: CartOutline },
  { path: '/keys', label: 'Keys', icon: KeyOutline },
  { path: '/redeems', label: 'Redeem', icon: GiftOutline },
  { path: '/customers', label: 'Users', icon: PeopleOutline },
  { path: '/settings', label: 'Config', icon: SettingsOutline },
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
  height: 56px;
  background: rgba(13, 19, 31, 0.95);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-top: 1px solid rgba(255, 255, 255, 0.08);
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
  color: var(--text-4);
  gap: 3px;
  padding: 6px 8px;
  cursor: pointer;
  transition: all 0.15s ease;
  flex: 1;
}

.mobile-nav-item.active {
  color: var(--accent);
}

.icon-wrap {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
}

.mobile-icon {
  width: 19px;
  height: 19px;
  transition: transform 0.15s ease;
}

.mobile-nav-item.active .mobile-icon {
  transform: translateY(-1px);
}

.badge-dot {
  position: absolute;
  top: -2px;
  right: -5px;
}

.item-label {
  font-size: 11px;
  font-weight: 600;
}
</style>
