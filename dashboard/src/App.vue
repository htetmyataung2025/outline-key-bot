<script setup lang="ts">
import { ref, onMounted } from 'vue'
import {
  NConfigProvider,
  NMessageProvider,
  NDialogProvider,
  NModal,
  NCard,
  NInput,
  NButton,
  darkTheme,
} from 'naive-ui'
import { KeyOutline, LockClosedOutline } from '@vicons/ionicons5'
import { themeOverrides } from '@/theme'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import MobileNav from '@/components/layout/MobileNav.vue'
import { fetchOverview, fetchSlips } from '@/api'

const pendingSlipsCount = ref(0)
const currentViewRef = ref<any>(null)

// Desktop Auth Modal
const showLoginModal = ref(false)
const adminPin = ref('admin12345')
const loginLoading = ref(false)
const loginError = ref('')

async function refreshPendingCount() {
  try {
    const slips = await fetchSlips('PENDING')
    pendingSlipsCount.value = slips.length
  } catch (e: any) {
    if (e?.response?.status === 401 && !window.Telegram?.WebApp?.initData) {
      showLoginModal.value = true
    }
  }
}

function handleGlobalRefresh() {
  refreshPendingCount()
  if (currentViewRef.value?.loadData) {
    currentViewRef.value.loadData()
  }
}

async function handleLogin() {
  if (!adminPin.value.trim()) {
    loginError.value = 'Please enter an Admin Secret PIN'
    return
  }
  loginLoading.value = true
  loginError.value = ''
  try {
    localStorage.setItem('admin_token', adminPin.value.trim())
    await fetchOverview()
    showLoginModal.value = false
    handleGlobalRefresh()
  } catch (err: any) {
    localStorage.removeItem('admin_token')
    loginError.value = err?.response?.data?.error || 'Invalid Admin Secret PIN. Check .env (ADMIN_SECRET_KEY)'
  } finally {
    loginLoading.value = false
  }
}

function handleLogout() {
  localStorage.removeItem('admin_token')
  showLoginModal.value = true
}

onMounted(() => {
  // Initialize Telegram WebApp SDK if running inside Telegram
  try {
    if (window.Telegram?.WebApp) {
      window.Telegram.WebApp.ready()
      window.Telegram.WebApp.expand()
    }
  } catch (e) {
    // Non-Telegram environment
  }

  const isTMA = Boolean(window.Telegram?.WebApp?.initData)
  const hasDesktopToken = Boolean(localStorage.getItem('admin_token'))

  if (!isTMA && !hasDesktopToken) {
    showLoginModal.value = true
  } else {
    refreshPendingCount()
  }

  setInterval(refreshPendingCount, 15000)
})
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <div class="app-layout">
          <AppHeader @refresh="handleGlobalRefresh" @logout="handleLogout" />

          <div class="layout-main">
            <!-- Desktop Sidebar -->
            <AppSidebar
              class="desktop-only"
              :pending-slips-count="pendingSlipsCount"
            />

            <!-- Router View Content Container -->
            <main class="page-content">
              <router-view v-slot="{ Component }">
                <component :is="Component" ref="currentViewRef" />
              </router-view>
            </main>
          </div>

          <!-- Mobile / Telegram Mini App Bottom Navigation -->
          <MobileNav
            class="mobile-only"
            :pending-slips-count="pendingSlipsCount"
          />

          <!-- Desktop PIN Login Modal -->
          <NModal v-model:show="showLoginModal" :mask-closable="false" :close-on-esc="false">
            <NCard
              style="width: 90vw; max-width: 420px; background: #0f172a; border: 1px solid #334155; border-radius: 12px;"
              title="Admin Authentication"
              :bordered="false"
              size="huge"
            >
              <div style="display: flex; flex-direction: column; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <div style="width: 44px; height: 44px; border-radius: 10px; background: rgba(16, 185, 129, 0.15); display: flex; align-items: center; justify-content: center; color: #10b981;">
                    <LockClosedOutline style="width: 22px; height: 22px;" />
                  </div>
                  <div>
                    <span style="font-size: 14px; font-weight: 600; color: #f8fafc;">Control Center Access</span>
                    <br />
                    <span style="font-size: 12px; color: #94a3b8;">Enter Desktop Admin Secret PIN</span>
                  </div>
                </div>

                <div style="display: flex; flex-direction: column; gap: 6px;">
                  <NInput
                    v-model:value="adminPin"
                    type="password"
                    show-password-on="click"
                    placeholder="Enter Admin PIN / Secret Key"
                    size="large"
                    @keyup.enter="handleLogin"
                  >
                    <template #prefix>
                      <KeyOutline style="width: 16px; height: 16px; color: #94a3b8;" />
                    </template>
                  </NInput>
                  <span style="font-size: 11px; color: #64748b;">
                    Default local PIN: <code style="color: #10b981;">admin12345</code> (Configured in .env)
                  </span>
                </div>

                <div v-if="loginError" style="color: #ef4444; font-size: 12px; background: rgba(239, 68, 68, 0.1); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.2);">
                  {{ loginError }}
                </div>

                <NButton
                  type="primary"
                  block
                  size="large"
                  :loading="loginLoading"
                  @click="handleLogin"
                >
                  Authorize Access
                </NButton>
              </div>
            </NCard>
          </NModal>
        </div>
      </NDialogProvider>
    </NMessageProvider>
  </NConfigProvider>
</template>

<style>
/* Global CSS resets */
* {
  box-sizing: border-box;
}

body {
  margin: 0;
  padding: 0;
  background-color: #0b1120;
  color: #f8fafc;
  font-family: 'Inter', system-ui, -apple-system, sans-serif;
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}

/* Custom scrollbars */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: #0b1120;
}
::-webkit-scrollbar-thumb {
  background: #334155;
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: #475569;
}
</style>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: #0b1120;
}

.layout-main {
  display: flex;
  flex: 1;
}

.page-content {
  flex: 1;
  max-width: 1400px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 80px; /* Space for mobile bottom nav */
}

@media (min-width: 768px) {
  .page-content {
    padding-bottom: 24px;
  }
}

.desktop-only {
  display: none;
}

.mobile-only {
  display: flex;
}

@media (min-width: 768px) {
  .desktop-only {
    display: flex;
  }
  .mobile-only {
    display: none;
  }
}
</style>
