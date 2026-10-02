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

defineProps<{
  refreshing?: boolean
  /** Push-channel health: 'stream' = SSE live, 'poll' = fallback polling, 'off' = down. */
  liveMode?: 'stream' | 'poll' | 'off'
}>()
const emit = defineEmits(['refresh', 'logout'])
const { isCollapsed, toggle: toggleSidebar } = useSidebar()

const yangonTime = ref('')
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
  emit('refresh')
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
      <!-- Sidebar Toggle: DESKTOP ONLY (Hidden on mobile) -->
      <NTooltip trigger="hover">
        <template #trigger>
          <button class="sidebar-toggle-btn desktop-only" @click="handleToggleSidebar">
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
            <span class="app-title">Control Center</span>
            <span class="version-tag desktop-only">v2.1</span>
          </div>
          <span class="app-subtitle desktop-only">H &amp; E Premium VPN</span>
        </div>
      </div>
    </div>

    <div class="header-actions">
      <!-- Live Indicator: reflects the actual push-channel state -->
      <NTooltip trigger="hover">
        <template #trigger>
          <div class="status-pill" :class="`mode-${liveMode || 'off'}`">
            <span class="pulse-dot"></span>
            <span class="status-label desktop-only">{{ liveMode === 'poll' ? 'POLL' : liveMode === 'stream' ? 'LIVE' : 'OFF' }}</span>
            <span class="status-label mobile-only">{{ liveMode === 'poll' ? 'POLL' : liveMode === 'stream' ? 'LIVE' : 'OFF' }}</span>
          </div>
        </template>
        {{
          liveMode === 'stream'
            ? 'Live push connected — updates arrive instantly'
            : liveMode === 'poll'
              ? 'Push unavailable — checking for changes every 30s'
              : 'Live sync offline'
        }}
      </NTooltip>

      <!-- Yangon Clock: Large Screen only -->
      <div class="clock-badge">
        <TimeOutline class="clock-icon" />
        <span class="time-text">{{ yangonTime }}</span>
        <span class="tz-label">MMT</span>
      </div>

      <!-- Admin Tag: Desktop only -->
      <NTag type="success" size="small" round :bordered="false" class="admin-badge desktop-only">
        <template #icon>
          <ShieldCheckmarkOutline />
        </template>
        Admin
      </NTag>

      <!-- Refresh Button -->
      <NTooltip trigger="hover">
        <template #trigger>
          <button
            class="action-icon-btn"
            :disabled="refreshing"
            :aria-busy="refreshing"
            @click="handleRefresh"
          >
            <span v-if="refreshing" class="btn-spinner" />
            <RefreshOutline v-else class="btn-icon" />
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
  height: 60px;
  background: rgba(13, 19, 34, 0.92);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  border-bottom: 1px solid rgba(255, 255, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 16px;
  position: sticky;
  top: 0;
  z-index: 100;
}

@media (max-width: 767px) {
  .app-header {
    height: 52px;
    padding: 0 12px;
    /* Solid background: the translucent + blurred header lets scrolling
       cards bleed through, which reads as a hazy navbar on mobile. */
    background: #0d1322;
    backdrop-filter: none;
    -webkit-backdrop-filter: none;
  }
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* Sidebar Toggle: Desktop only */
.sidebar-toggle-btn {
  width: 34px;
  height: 34px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-3);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.sidebar-toggle-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-1);
  border-color: rgba(255, 255, 255, 0.15);
}

.toggle-icon {
  width: 18px;
  height: 18px;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-badge {
  width: 32px;
  height: 32px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.25) 0%, rgba(6, 182, 212, 0.15) 100%);
  border: 1px solid rgba(16, 185, 129, 0.35);
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.brand-key-icon {
  width: 17px;
  height: 17px;
  color: var(--accent);
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 6px;
}

.app-title {
  font-size: 14.5px;
  font-weight: 700;
  color: var(--text-1);
  letter-spacing: -0.2px;
  white-space: nowrap;
}

.version-tag {
  font-size: 11px;
  font-weight: 700;
  color: var(--accent);
  background: rgba(16, 185, 129, 0.12);
  border: 1px solid rgba(16, 185, 129, 0.25);
  padding: 1px 4px;
  border-radius: 4px;
}

.app-subtitle {
  font-size: 11.5px;
  color: var(--text-4);
  font-weight: 500;
  white-space: nowrap;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(16, 185, 129, 0.08);
  border: 1px solid rgba(16, 185, 129, 0.25);
  padding: 3px 8px;
  border-radius: 16px;
  transition: border-color 0.2s ease, background 0.2s ease;
}

/* Push stream down → poll fallback (amber) or offline (gray).
   Only the DOT gets a filled background + glow; the LABEL gets a text
   color change only — a solid background on the text renders as a big
   amber blob with unreadable text. */
.status-pill.mode-poll {
  background: rgba(245, 158, 11, 0.08);
  border-color: rgba(245, 158, 11, 0.3);
}

.status-pill.mode-poll .pulse-dot {
  color: var(--warn);
  background-color: var(--warn);
  box-shadow: 0 0 6px var(--warn);
  animation: none;
}

.status-pill.mode-poll .status-label {
  color: var(--warn);
}

.status-pill.mode-off {
  background: rgba(148, 163, 184, 0.08);
  border-color: rgba(148, 163, 184, 0.25);
}

.status-pill.mode-off .pulse-dot {
  color: var(--text-3);
  background-color: var(--text-3);
  box-shadow: none;
  animation: none;
}

.status-pill.mode-off .status-label {
  color: var(--text-3);
}

.pulse-dot {
  width: 6px;
  height: 6px;
  background-color: var(--accent);
  border-radius: 50%;
  box-shadow: 0 0 6px var(--accent);
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 4px rgba(16, 185, 129, 0); }
  100% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0); }
}

.status-label {
  font-size: 11.5px;
  font-weight: 700;
  color: var(--accent);
  letter-spacing: 0.4px;
}

.clock-badge {
  display: none;
  align-items: center;
  gap: 6px;
  background: rgba(255, 255, 255, 0.03);
  border: 1px solid rgba(255, 255, 255, 0.08);
  padding: 4px 8px;
  border-radius: 7px;
  font-size: 11.5px;
  color: var(--text-2);
  font-family: 'JetBrains Mono', monospace;
}

@media (min-width: 960px) {
  .clock-badge {
    display: flex;
  }
}

.clock-icon {
  width: 12px;
  height: 12px;
  color: var(--text-3);
}

.tz-label {
  font-size: 11px;
  color: var(--text-4);
  font-weight: 600;
}

.action-icon-btn {
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  background: rgba(255, 255, 255, 0.03);
  color: var(--text-3);
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-icon-btn:hover {
  background: rgba(255, 255, 255, 0.08);
  color: var(--text-1);
  border-color: rgba(255, 255, 255, 0.15);
}

.action-icon-btn.danger:hover {
  background: rgba(239, 68, 68, 0.15);
  color: var(--danger-soft);
  border-color: rgba(239, 68, 68, 0.3);
}

.action-icon-btn:disabled {
  opacity: 0.7;
  cursor: default;
}

.btn-icon {
  width: 15px;
  height: 15px;
}

.btn-spinner {
  width: 15px;
  height: 15px;
  border: 2px solid rgba(148, 163, 184, 0.25);
  border-top-color: currentColor;
  border-radius: 50%;
  animation: loader-rotate 0.7s linear infinite;
  flex-shrink: 0;
}

@keyframes loader-rotate {
  to { transform: rotate(360deg); }
}

/* Visibility helpers */
.desktop-only {
  display: flex;
}

.mobile-only {
  display: none;
}

@media (max-width: 767px) {
  .desktop-only {
    display: none !important;
  }
  .mobile-only {
    display: inline !important;
  }
}
</style>
