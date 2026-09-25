<script setup lang="ts">
import { computed } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { triggerHaptic } from '@/api'
import { useSidebar } from '@/composables/useSidebar'
import { NBadge, NTooltip } from 'naive-ui'
import {
  SpeedometerOutline,
  ReceiptOutline,
  KeyOutline,
  GiftOutline,
  PeopleOutline,
  ChevronBackOutline,
  ChevronForwardOutline,
  CloudDoneOutline,
  SettingsOutline,
} from '@vicons/ionicons5'

const props = defineProps<{
  pendingSlipsCount: number
}>()

const route = useRoute()
const router = useRouter()
const { isCollapsed, toggle: toggleSidebar } = useSidebar()

const navItems = computed(() => [
  { path: '/overview', label: 'Overview', icon: SpeedometerOutline, hint: 'Cluster telemetry & KPIs' },
  { path: '/slips', label: 'Slips Queue', icon: ReceiptOutline, badge: props.pendingSlipsCount, hint: 'Verify payment receipts' },
  { path: '/keys', label: 'Access Keys', icon: KeyOutline, hint: 'Manage & extend Outline keys' },
  { path: '/redeems', label: 'Redeem Codes', icon: GiftOutline, hint: 'Generate voucher codes' },
  { path: '/customers', label: 'Customers', icon: PeopleOutline, hint: 'Wallets & balances' },
  { path: '/settings', label: 'Settings', icon: SettingsOutline, hint: 'Servers, Plans & Rules' },
])

function navigate(path: string) {
  triggerHaptic('light')
  router.push(path)
}
</script>

<template>
  <aside class="app-sidebar" :class="{ collapsed: isCollapsed }">
    <div class="nav-menu">
      <div v-if="!isCollapsed" class="menu-section-label">
        MANAGEMENT
      </div>

      <template v-for="item in navItems" :key="item.path">
        <!-- If collapsed, wrap with right-aligned tooltip -->
        <NTooltip v-if="isCollapsed" placement="right" trigger="hover">
          <template #trigger>
            <button
              class="nav-item"
              :class="{ active: route.path.startsWith(item.path) }"
              @click="navigate(item.path)"
            >
              <div class="nav-icon-wrap">
                <component :is="item.icon" class="nav-icon" />
              </div>
              <span v-if="item.badge && item.badge > 0" class="collapsed-badge-dot"></span>
            </button>
          </template>
          <div class="tooltip-content">
            <span class="tooltip-title">{{ item.label }}</span>
            <span v-if="item.badge && item.badge > 0" class="tooltip-badge">
              {{ item.badge }} Pending
            </span>
          </div>
        </NTooltip>

        <!-- If expanded, render normal full button -->
        <button
          v-else
          class="nav-item"
          :class="{ active: route.path.startsWith(item.path) }"
          @click="navigate(item.path)"
        >
          <div class="nav-icon-wrap">
            <component :is="item.icon" class="nav-icon" />
          </div>
          <div class="nav-text-block">
            <span class="nav-label">{{ item.label }}</span>
            <span class="nav-hint">{{ item.hint }}</span>
          </div>

          <NBadge
            v-if="item.badge && item.badge > 0"
            :value="item.badge"
            type="warning"
            class="nav-badge"
          />
        </button>
      </template>
    </div>

    <!-- Sidebar Footer -->
    <div class="sidebar-footer">
      <div v-if="!isCollapsed" class="footer-card">
        <div class="footer-status-row">
          <CloudDoneOutline class="sync-icon" />
          <span class="footer-title">Sync Online</span>
        </div>
        <span class="footer-desc">SG-1, SG-2 & VIP 3-Nodes Active</span>
      </div>

      <!-- Quick Collapse Toggle at bottom -->
      <button class="collapse-toggle-btn" @click="toggleSidebar">
        <ChevronForwardOutline v-if="isCollapsed" class="collapse-icon" />
        <template v-else>
          <ChevronBackOutline class="collapse-icon" />
          <span class="collapse-text">Collapse Menu</span>
        </template>
      </button>
    </div>
  </aside>
</template>

<style scoped>
.app-sidebar {
  width: 250px;
  background: rgba(13, 19, 34, 0.95);
  border-right: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  padding: 16px 12px;
  height: calc(100vh - 64px);
  position: sticky;
  top: 64px;
  transition: width 0.22s cubic-bezier(0.4, 0, 0.2, 1), padding 0.22s ease;
  user-select: none;
}

.app-sidebar.collapsed {
  width: 72px;
  padding: 16px 8px;
}

.nav-menu {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.menu-section-label {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.8px;
  color: #475569;
  padding: 4px 10px 8px 10px;
}

.nav-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 12px;
  border-radius: 10px;
  background: transparent;
  border: 1px solid transparent;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.18s ease;
  text-align: left;
  width: 100%;
  position: relative;
}

.collapsed .nav-item {
  justify-content: center;
  padding: 12px 0;
  gap: 0;
}

.nav-item:hover {
  background: rgba(255, 255, 255, 0.04);
  color: #f8fafc;
  border-color: rgba(255, 255, 255, 0.06);
}

.nav-item.active {
  background: linear-gradient(90deg, rgba(16, 185, 129, 0.16) 0%, rgba(16, 185, 129, 0.04) 100%);
  color: #10b981;
  border: 1px solid rgba(16, 185, 129, 0.25);
  box-shadow: 0 0 16px rgba(16, 185, 129, 0.08);
}

.nav-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  flex-shrink: 0;
}

.nav-icon {
  width: 19px;
  height: 19px;
  transition: transform 0.2s ease;
}

.nav-item:hover .nav-icon {
  transform: scale(1.08);
}

.nav-text-block {
  display: flex;
  flex-direction: column;
  flex: 1;
  min-width: 0;
}

.nav-label {
  font-size: 13.5px;
  font-weight: 600;
  color: inherit;
  line-height: 1.2;
}

.nav-hint {
  font-size: 10.5px;
  color: #64748b;
  margin-top: 2px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.nav-item.active .nav-hint {
  color: #34d399;
  opacity: 0.8;
}

.nav-badge {
  margin-left: auto;
  flex-shrink: 0;
}

.collapsed-badge-dot {
  position: absolute;
  top: 8px;
  right: 14px;
  width: 8px;
  height: 8px;
  background-color: #f59e0b;
  border-radius: 50%;
  border: 2px solid #0f172a;
}

.sidebar-footer {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-top: 12px;
  border-top: 1px solid rgba(255, 255, 255, 0.06);
}

.footer-card {
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 9px;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.footer-status-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.sync-icon {
  width: 14px;
  height: 14px;
  color: #10b981;
}

.footer-title {
  font-size: 11px;
  font-weight: 700;
  color: #10b981;
}

.footer-desc {
  font-size: 10px;
  color: #64748b;
}

.collapse-toggle-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 8px;
  background: rgba(255, 255, 255, 0.02);
  border: 1px solid rgba(255, 255, 255, 0.06);
  border-radius: 8px;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
  width: 100%;
}

.collapse-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.06);
  color: #cbd5e1;
  border-color: rgba(255, 255, 255, 0.12);
}

.collapse-icon {
  width: 15px;
  height: 15px;
}

.tooltip-content {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tooltip-title {
  font-size: 12px;
  font-weight: 600;
  color: #f8fafc;
}

.tooltip-badge {
  font-size: 10px;
  color: #f59e0b;
  font-weight: 600;
}
</style>
