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
  { path: '/slips', label: 'Slips Queue', icon: ReceiptOutline, badge: props.pendingSlipsCount },
  { path: '/keys', label: 'Access Keys', icon: KeyOutline },
  { path: '/redeems', label: 'Redeem Codes', icon: GiftOutline },
  { path: '/customers', label: 'Customers', icon: PeopleOutline },
])

function navigate(path: string) {
  triggerHaptic('light')
  router.push(path)
}
</script>

<template>
  <aside class="app-sidebar">
    <div class="nav-menu">
      <button
        v-for="item in navItems"
        :key="item.path"
        class="nav-item"
        :class="{ active: route.path.startsWith(item.path) }"
        @click="navigate(item.path)"
      >
        <div class="nav-icon-wrap">
          <component :is="item.icon" class="nav-icon" />
        </div>
        <span class="nav-label">{{ item.label }}</span>

        <NBadge
          v-if="item.badge && item.badge > 0"
          :value="item.badge"
          type="warning"
          class="nav-badge"
        />
      </button>
    </div>

    <div class="sidebar-footer">
      <div class="footer-card">
        <span class="footer-title">Outline API</span>
        <span class="footer-desc">SG-1, SG-2 & VIP Live Sync</span>
      </div>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: 240px;
  background-color: #0f172a;
  border-right: 1px solid #334155;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px 12px;
  height: calc(100vh - 64px);
  position: sticky;
  top: 64px;
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 8px;
  background: transparent;
  border: none;
  color: #94a3b8;
  font-size: 14px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s ease-in-out;
  text-align: left;
  width: 100%;
}

.nav-item:hover {
  background: rgba(51, 65, 85, 0.4);
  color: #f8fafc;
}

.nav-item.active {
  background: rgba(16, 185, 129, 0.15);
  color: #10b981;
  font-weight: 600;
  border-left: 3px solid #10b981;
}

.nav-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
}

.nav-icon {
  width: 18px;
  height: 18px;
}

.nav-label {
  flex: 1;
}

.nav-badge {
  margin-left: auto;
}

.sidebar-footer {
  padding-top: 16px;
}

.footer-card {
  background: #1e293b;
  border: 1px solid #334155;
  border-radius: 8px;
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.footer-title {
  font-size: 12px;
  font-weight: 600;
  color: #cbd5e1;
}

.footer-desc {
  font-size: 11px;
  color: #64748b;
}
</style>
