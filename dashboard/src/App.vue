<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
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
import { KeyOutline, LockClosedOutline, PersonOutline } from '@vicons/ionicons5'
import { themeOverrides } from '@/theme'
import AppHeader from '@/components/layout/AppHeader.vue'
import AppSidebar from '@/components/layout/AppSidebar.vue'
import MobileNav from '@/components/layout/MobileNav.vue'
import { adminLogin, fetchSlips, fetchDataVersion, openVersionStream } from '@/api'

const pendingSlipsCount = ref(0)
const currentViewRef = ref<any>(null)
const isAuthenticated = ref(false)

// Auth Modal — Admin ID + password, identical in the browser and the
// Telegram Mini App (the Mini App no longer auto-logs in via initData).
const showLoginModal = ref(false)
const adminId = ref('')
const adminPassword = ref('')
const loginLoading = ref(false)

const loginError = ref('')

function loginErrorMessage(err: any): string {
  const status = err?.response?.status
  if (status === 401) return 'Admin Password မှားနေပါသည်။'
  if (status === 403) {
    const detail = err?.response?.data?.error || ''
    if (detail.includes('not enabled')) {
      return 'Admin login ကို စနစ်တွင် ဖွင့်ထားခြင်း မရှိသေးပါ။ (.env — ADMIN_SECRET_KEY)'
    }
    return 'ဒီ Admin ID ကို ဝင်ရောက်ခွင့် မရှိပါ။'
  }
  if (status === 400) return err?.response?.data?.error || 'Admin ID နှင့် Password နှစ်ခုလုံး ဖြည့်သွင်းပါ။'
  if (status === 429) return 'Login ကြိုးစားမှု များပြားနေပါသည်။ အချိန်အနည်းငယ် စောင့်ဆိုင်းပြီး ထပ်မံ ကြိုးစားပါ။'
  return err?.response?.data?.error || 'ဝင်ရောက်မှု မအောင်မြင်ပါ။ ထပ်မံ ကြိုးစားကြည့်ပါ။'
}

function clearCredentials() {
  localStorage.removeItem('admin_id')
  localStorage.removeItem('admin_token')
}

async function refreshPendingCount() {
  if (!isAuthenticated.value) return
  try {
    const slips = await fetchSlips('PENDING')
    pendingSlipsCount.value = slips.length
  } catch (e: any) {
    const status = e?.response?.status
    if (status !== 401 && status !== 403) return
    // Session no longer valid (secret rotated / ID removed from admins):
    // back to the login form with the server's reason.
    isAuthenticated.value = false
    clearCredentials()
    loginError.value = e?.response?.data?.error || ''
    showLoginModal.value = true
  }
}

const globalRefreshing = ref(false)

async function handleGlobalRefresh() {
  if (globalRefreshing.value) return
  globalRefreshing.value = true
  try {
    await Promise.all([
      refreshPendingCount(),
      currentViewRef.value?.loadData?.({ force: true }),
    ])
  } finally {
    globalRefreshing.value = false
  }
}

async function handleLogin() {
  const id = adminId.value.trim()
  const pw = adminPassword.value
  if (!id || !pw) {
    loginError.value = 'Admin ID နှင့် Password နှစ်ခုလုံး ဖြည့်သွင်းပါ။'
    return
  }
  loginLoading.value = true
  loginError.value = ''
  try {
    await adminLogin(id, pw)
    localStorage.setItem('admin_id', id)
    localStorage.setItem('admin_token', pw)
    isAuthenticated.value = true
    showLoginModal.value = false
    handleGlobalRefresh()
  } catch (err: any) {
    isAuthenticated.value = false
    clearCredentials()
    loginError.value = loginErrorMessage(err)
  } finally {
    loginLoading.value = false
  }
}

function handleLogout() {
  clearCredentials()
  adminId.value = ''
  adminPassword.value = ''
  loginError.value = ''
  isAuthenticated.value = false
  stopFallbackPoll()
  liveMode.value = 'off'
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

  // Both entry points (browser + Mini App) require an explicit Admin ID +
  // password login; there is no initData auto-login anymore.
  const hasCredentials = Boolean(localStorage.getItem('admin_token') && localStorage.getItem('admin_id'))
  if (!hasCredentials) {
    isAuthenticated.value = false
    showLoginModal.value = true
  } else {
    isAuthenticated.value = true
    refreshPendingCount()
  }

  document.addEventListener('visibilitychange', onVisibilityChange)
  startLiveSync()
})

// ── Live sync: server push (SSE) in dev, version-poll in production ────────
// Dev path (localhost): the Flask server streams every data-version change
// over Server-Sent Events the instant any shared state is written (slip
// arrives via Telegram, approve/reject, key/balance/settings edit).
// Production path: on serverless hosting (Vercel) a held-open stream is
// billed as provisioned memory-hours, so api.ts skips SSE and this poll runs
// instead — a lightweight "did the version move?" request every 30s
// (tunable via VITE_VERSION_POLL_INTERVAL_MS at build time).
const knownVersion = ref<number | null>(null)
const liveMode = ref<'stream' | 'poll' | 'off'>('off')
const VERSION_POLL_INTERVAL_MS = Number(import.meta.env.VITE_VERSION_POLL_INTERVAL_MS) || 30000
let fallbackTimer: ReturnType<typeof setInterval> | null = null
let closeStream: (() => void) | null = null

async function applyExternalChange(version: number) {
  knownVersion.value = version
  // Don't fetch for a hidden tab; the visibility handler catches up.
  if (document.hidden) return
  await Promise.all([
    refreshPendingCount(),
    currentViewRef.value?.loadData?.({ silent: true }),
  ])
}

function startFallbackPoll() {
  if (fallbackTimer) return
  fallbackTimer = setInterval(async () => {
    if (!isAuthenticated.value || document.hidden) return
    try {
      const version = await fetchDataVersion()
      if (knownVersion.value === null) {
        knownVersion.value = version
        return
      }
      if (version !== knownVersion.value) await applyExternalChange(version)
    } catch {
      // Transient poll failures are fine; next tick retries. 401 handled in refreshPendingCount.
    }
  }, VERSION_POLL_INTERVAL_MS)
}

function stopFallbackPoll() {
  if (fallbackTimer) {
    clearInterval(fallbackTimer)
    fallbackTimer = null
  }
}

function startLiveSync() {
  if (closeStream) return
  closeStream = openVersionStream({
    onState: (up) => {
      liveMode.value = up ? 'stream' : isAuthenticated.value ? 'poll' : 'off'
      if (up) stopFallbackPoll()
      else if (isAuthenticated.value) startFallbackPoll()
    },
    onVersion: (version) => {
      // First event (or reconnect baseline) just primes the counter; a
      // baseline ahead of what we last saw covers writes missed offline.
      if (knownVersion.value === null) {
        knownVersion.value = version
        return
      }
      if (version !== knownVersion.value) applyExternalChange(version)
    },
  })
}

function onVisibilityChange() {
  if (!document.hidden && isAuthenticated.value && currentViewRef.value) {
    // Catch up on anything pushed (or missed) while the tab was hidden.
    refreshPendingCount()
    currentViewRef.value?.loadData?.({ silent: true })
  }
}

onUnmounted(() => {
  document.removeEventListener('visibilitychange', onVisibilityChange)
  stopFallbackPoll()
  closeStream?.()
  closeStream = null
})
</script>

<template>
  <NConfigProvider :theme="darkTheme" :theme-overrides="themeOverrides">
    <NMessageProvider>
      <NDialogProvider>
        <div class="app-layout">
          <AppHeader
            :refreshing="globalRefreshing"
            :live-mode="liveMode"
            @refresh="handleGlobalRefresh"
            @logout="handleLogout"
          />

          <div class="layout-main">
            <!-- Desktop Sidebar -->
            <AppSidebar
              class="desktop-only"
              :pending-slips-count="pendingSlipsCount"
            />

            <!-- Router View Content Container -->
            <main class="page-content">
              <router-view v-if="isAuthenticated" v-slot="{ Component, route }">
                <Transition name="admin-page" mode="out-in">
                  <component :is="Component" :key="route.path" ref="currentViewRef" />
                </Transition>
              </router-view>
            </main>
          </div>

          <!-- Mobile / Telegram Mini App Bottom Navigation -->
          <MobileNav
            class="mobile-only"
            :pending-slips-count="pendingSlipsCount"
          />

          <!-- Admin Login Modal (browser + Telegram Mini App) -->
          <NModal v-model:show="showLoginModal" :mask-closable="false" :close-on-esc="false">
            <NCard
              style="width: 90vw; max-width: 420px; background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);"
              title="Admin Authentication"
              :bordered="false"
              size="huge"
            >
              <div style="display: flex; flex-direction: column; gap: 16px;">
                <div style="display: flex; align-items: center; gap: 12px;">
                  <div style="width: 44px; height: 44px; border-radius: 10px; background: var(--accent-soft); display: flex; align-items: center; justify-content: center; color: var(--accent);">
                    <LockClosedOutline style="width: 22px; height: 22px;" />
                  </div>
                  <div>
                    <span style="font-size: 14px; font-weight: 600; color: var(--text-1);">Control Center Access</span>
                    <br />
                    <span style="font-size: 12px; color: var(--text-3);">Admin ID နှင့် Password ဖြင့် ဝင်ရောက်ပါ</span>
                  </div>
                </div>

                <div style="display: flex; flex-direction: column; gap: 10px;">
                  <NInput
                    v-model:value="adminId"
                    inputmode="numeric"
                    placeholder="Admin ID (Telegram User ID)"
                    size="large"
                    @keyup.enter="handleLogin"
                  >
                    <template #prefix>
                      <PersonOutline style="width: 16px; height: 16px; color: var(--text-3);" />
                    </template>
                  </NInput>
                  <NInput
                    v-model:value="adminPassword"
                    type="password"
                    show-password-on="click"
                    placeholder="Admin Password"
                    size="large"
                    @keyup.enter="handleLogin"
                  >
                    <template #prefix>
                      <KeyOutline style="width: 16px; height: 16px; color: var(--text-3);" />
                    </template>
                  </NInput>
                  <span style="font-size: 12px; color: var(--text-4);">
                    Admin ID သည် <code>ADMIN_CHAT_IDS</code> ထဲမှ တစ်ခု ဖြစ်ရမည် · Password မှာ <code>ADMIN_SECRET_KEY</code> ဖြစ်သည်
                  </span>
                </div>

                <div v-if="loginError" style="color: var(--danger); font-size: 12px; background: rgba(239, 68, 68, 0.1); padding: 8px 12px; border-radius: 6px; border: 1px solid rgba(239, 68, 68, 0.2);">
                  {{ loginError }}
                </div>

                <NButton
                  type="primary"
                  block
                  size="large"
                  :loading="loginLoading"
                  @click="handleLogin"
                >
                  ဝင်ရောက်မည်
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
  background-color: var(--bg);
  color: var(--text-1);
  font-family: var(--font-sans);
  overflow-x: hidden;
  -webkit-font-smoothing: antialiased;
}

/* Custom scrollbars */
::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}
::-webkit-scrollbar-track {
  background: var(--bg);
}
::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 4px;
}
::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.2);
}
</style>

<style scoped>
.app-layout {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
  background-color: var(--bg);
  background-image:
    radial-gradient(at 15% 15%, rgba(16, 185, 129, 0.04) 0px, transparent 45%),
    radial-gradient(at 85% 85%, rgba(14, 165, 233, 0.04) 0px, transparent 45%);
}

.layout-main {
  display: flex;
  flex: 1;
  min-height: calc(100vh - 64px);
}

.page-content {
  flex: 1;
  max-width: 1440px;
  margin: 0 auto;
  width: 100%;
  padding-bottom: 80px; /* Space for mobile bottom nav */
}

.admin-page-enter-active {
  transition: opacity 0.2s cubic-bezier(0.22, 1, 0.36, 1), transform 0.2s cubic-bezier(0.22, 1, 0.36, 1);
}
.admin-page-leave-active {
  transition: opacity 0.14s ease, transform 0.14s ease;
}
.admin-page-enter-from {
  opacity: 0;
  transform: translate3d(0, 8px, 0);
}
.admin-page-leave-to {
  opacity: 0;
  transform: translate3d(0, -4px, 0);
}

@media (prefers-reduced-motion: reduce) {
  .admin-page-enter-active,
  .admin-page-leave-active {
    transition: opacity 0.1s ease;
  }
  .admin-page-enter-from,
  .admin-page-leave-to {
    transform: none;
  }
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
