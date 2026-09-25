<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { triggerHaptic } from '@/api'
import { useSidebar } from '@/composables/useSidebar'
import { NTag, NTooltip } from 'naive-ui'
import {
  MenuOutline,
  RefreshOutline,
  TimeOutline,
  ShieldCheckmarkOutline,
  LogOutOutline,
  KeyOutline,
} from '@vicons/ionicons5'

const emit = defineEmits(['refresh', 'logout'])
const { isCollapsed, toggle: toggleSidebar } = useSidebar()

const yangonTime = ref('')
const isRefreshing = ref(false)
let timer: any = null

function updateClock() {
  const now = new Date()
  yangonTime.value = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Yangon',
    hour: '2-digit',
    minute: '2-digit',
    second: '2-digit',
    hour12: true,
  }).format(now)
}

function handleRefresh() {
  triggerHaptic('light')
  isRefreshing.value = true
  emit('refresh')
  setTimeout(() => {
    isRefreshing.value = false
  }, 600)
}

function handleLogout() {
  triggerHaptic('light')
  emit('logout')
}

function handleToggleSidebar() {
  triggerHaptic('light')
  toggleSidebar()
}

onMounted(() => {
  updateClock()
  timer = setInterval(updateClock, 1000)
})

onUnmounted(() => {
  if (timer) clearInterval(timer)
})
</script>

<template>
  <header class="app-header">
    <div class="header-left">
      <!-- Sidebar Toggle Button (Desktop & Mobile) -->
      <NTooltip trigger="hover">
        <template #trigger>
          <button class="sidebar-toggle-btn" @click="handleToggleSidebar">
            <MenuOutline class="toggle-icon" />
          </button>
        </template>
        {{ isCollapsed ? 'Expand Sidebar' : 'Collapse Sidebar' }}
      </NTooltip>

      <div class="brand">
        <div class="logo-badge">
          <KeyOutline class="brand-key-icon" />
        </div>
        <div class="brand-text">
          <div class="title-row">
            <span class="app-title">Outline Control Center</span>
            <span class="version-tag">v2.1</span>
          </div>
          <span class="app-subtitle">H & E Premium VPN Infrastructure</span>
        </div>
      </div>
    </div>

    <div class="header-actions">
      <!-- Live Indicator -->
      <div class="status-pill">
        <span class="pulse-dot"></span>
        <span class="status-label">CLUSTER LIVE</span>
      </div>

      <!-- Yangon Clock -->
      <div class="clock-badge">
        <TimeOutline class="clock-icon" />
        <span class="time-text">{{ yangonTime }}</span>
        <span class="tz-label">MMT</span>
      </div>

      <!-- Admin Tag -->
      <NTag type="success" size="small" round :bordered="false" class="admin-badge">
        <template #icon>
          <ShieldCheckmarkOutline />
        </template>
        NOC Admin
      </NTag>

      <!-- Refresh Button -->
      <NTooltip trigger="hover">
        <template #trigger>
          <button
            class="action-icon-btn"
            :class="{ spinning: isRefreshing }"
            @click="handleRefresh"
          >
            <RefreshOutline class="btn-icon" />
          </button>
        </template>
        Quick Refresh
      </NTooltip>

      <!-- Logout / Switch PIN -->
      <NTooltip trigger="hover">
        <template #trigger>
          <button class="action-icon-btn danger" @click="handleLogout">
            <LogOutOutline class="btn-icon" />
          </button>
        </template>
        Lock / Change PIN
      </NTooltip>
    </div>
  </header>
</template>

<style scoped>
.app-header {
  height: 64px;
  background: rgba(13, 19, 34, 0.85);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 18px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 12px;
}

.sidebar-toggle-btn {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sidebar-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
  border-color: rgba(255, 255, 255, 0.15);
}

.toggle-icon {
  width: 20px;
  height: 20px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-badge {
  width: 38px;
  height: 38px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(6, 182, 212, 0.15) 100%);
  border: 1px solid rgba(16, 185, 129, 0.35);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 0 15px rgba(16, 185, 129, 0.15);
}

.brand-key-icon {
  width: 20px;
  height: 20px;
  color: #10b981;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 8px;
}

.app-title {
  font-size: 15px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: -0.2px;
}

.version-tag {
  font-size: 10px;
  font-weight: 700;
  color: #10b981;
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.25);
  padding: 1px 5px;
  border-radius: 4px;
}

.app-subtitle {
  font-size: 11px;
  color: #64748b;
  font-weight: 500;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 7px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.25);
  padding: 4px 10px;
  border-radius: 20px;
}

.pulse-dot {
  width: 7px;
  height: 7px;
  background-color: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 8px #10b981;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 5px rgba(16, 185, 129, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.status-label {
  font-size: 11px;
  font-weight: 700;
  color: #10b981;
  letter-spacing: 0.5px;
}

.clock-badge {
  display: none;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 5px 10px;
  border-radius: 8px;
  font-size: 12px;
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
}

@media (min-width: 820px) {
  .clock-badge {
    display: flex;
  }
}

.clock-icon {
  width: 13px;
  height: 13px;
  color: #94a3b8;
}

.tz-label {
  font-size: 10px;
  color: #64748b;
  font-weight: 600;
}

.action-icon-btn {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: #94a3b8;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-icon-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: #f8fafc;
  border-color: rgba(255, 255, 255, 0.15);
}

.action-icon-btn.danger:hover {
  background: rgba(239, 68, 68, 0.15);
  color: #f87171;
  border-color: rgba(239, 68, 68, 0.3);
}

.btn-icon {
  width: 17px;
  height: 17px;
}

.spinning .btn-icon {
  animation: spin 0.6s linear;
}

@keyframes spin {
  100% { transform: rotate(360deg); }
}
</style>
