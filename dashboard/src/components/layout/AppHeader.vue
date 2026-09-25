<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { triggerHaptic } from '@/api'
import { NButton, NTag, NTooltip } from 'naive-ui'
import { RefreshOutline, TimeOutline, ShieldCheckmarkOutline, LogOutOutline } from '@vicons/ionicons5'

const emit = defineEmits(['refresh', 'logout'])

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
    <div class="brand">
      <div class="logo-badge">
        <span class="logo-icon">🔑</span>
      </div>
      <div class="brand-text">
        <span class="app-title">Outline Control Center</span>
        <span class="app-subtitle">H & E Premium VPN Admin</span>
      </div>
    </div>

    <div class="header-actions">
      <!-- Live Indicator -->
      <div class="status-pill">
        <span class="pulse-dot"></span>
        <span class="status-label">LIVE</span>
      </div>

      <!-- Yangon Clock -->
      <div class="clock-badge">
        <TimeOutline class="icon" />
        <span class="time-text">{{ yangonTime }} (MMT)</span>
      </div>

      <!-- Admin Tag -->
      <NTag type="success" size="small" round :bordered="false" class="admin-badge">
        <template #icon>
          <ShieldCheckmarkOutline />
        </template>
        Admin
      </NTag>

      <!-- Refresh Button -->
      <NTooltip trigger="hover">
        <template #trigger>
          <NButton circle quaternary size="medium" @click="handleRefresh">
            <template #icon>
              <RefreshOutline />
            </template>
          </NButton>
        </template>
        Quick Refresh
      </NTooltip>

      <!-- Logout / Switch PIN -->
      <NTooltip trigger="hover">
        <template #trigger>
          <NButton circle quaternary size="medium" @click="handleLogout">
            <template #icon>
              <LogOutOutline />
            </template>
          </NButton>
        </template>
        Lock / Change PIN
      </NTooltip>
    </div>
  </header>
</template>


<style scoped>
.app-header {
  height: 64px;
  background-color: #0f172a;
  border-bottom: 1px solid #334155;
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  position: sticky;
  top: 0;
  z-index: 100;
}

.brand {
  display: flex;
  align-items: center;
  gap: 12px;
}

.logo-badge {
  width: 40px;
  height: 40px;
  background: linear-gradient(135deg, rgba(16, 185, 129, 0.2), rgba(14, 165, 233, 0.2));
  border: 1px solid rgba(16, 185, 129, 0.3);
  border-radius: 10px;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
}

.brand-text {
  display: flex;
  flex-direction: column;
}

.app-title {
  font-size: 15px;
  font-weight: 700;
  color: #f8fafc;
  letter-spacing: -0.2px;
}

.app-subtitle {
  font-size: 11px;
  color: #94a3b8;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.status-pill {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(16, 185, 129, 0.1);
  border: 1px solid rgba(16, 185, 129, 0.25);
  padding: 4px 10px;
  border-radius: 20px;
}

.pulse-dot {
  width: 8px;
  height: 8px;
  background-color: #10b981;
  border-radius: 50%;
  box-shadow: 0 0 8px #10b981;
  animation: pulse 2s infinite;
}

@keyframes pulse {
  0% { transform: scale(0.95); box-shadow: 0 0 0 0 rgba(16, 185, 129, 0.7); }
  70% { transform: scale(1); box-shadow: 0 0 0 6px rgba(16, 185, 129, 0); }
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
  background-color: #1e293b;
  border: 1px solid #334155;
  padding: 5px 12px;
  border-radius: 8px;
  font-size: 12px;
  color: #cbd5e1;
  font-family: 'JetBrains Mono', monospace;
}

@media (min-width: 768px) {
  .clock-badge {
    display: flex;
  }
}

.icon {
  width: 14px;
  height: 14px;
  color: #94a3b8;
}
</style>
