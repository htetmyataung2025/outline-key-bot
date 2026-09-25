import axios from 'axios'

// Define Telegram WebApp interface
declare global {
  interface Window {
    Telegram?: {
      WebApp?: {
        initData: string
        initDataUnsafe?: any
        ready: () => void
        expand: () => void
        close: () => void
        BackButton?: {
          show: () => void
          hide: () => void
          onClick: (cb: () => void) => void
          offClick: (cb: () => void) => void
        }
        HapticFeedback?: {
          impactOccurred: (style: 'light' | 'medium' | 'heavy' | 'rigid' | 'soft') => void
          notificationOccurred: (type: 'error' | 'success' | 'warning') => void
          selectionChanged: () => void
        }
      }
    }
  }
}

export function triggerHaptic(style: 'light' | 'medium' | 'heavy' = 'medium') {
  try {
    window.Telegram?.WebApp?.HapticFeedback?.impactOccurred(style)
  } catch (e) {
    // Non-TMA environment safe
  }
}

export function triggerHapticNotification(type: 'success' | 'warning' | 'error') {
  try {
    window.Telegram?.WebApp?.HapticFeedback?.notificationOccurred(type)
  } catch (e) {
    // Non-TMA environment safe
  }
}

const api = axios.create({
  baseURL: '/api/admin',
  timeout: 10000,
})

api.interceptors.request.use((config) => {
  // 1. Try Telegram Mini App initData
  const tgInitData = window.Telegram?.WebApp?.initData
  if (tgInitData) {
    config.headers['X-Telegram-Init-Data'] = tgInitData
  }

  // 2. Try desktop bearer token fallback
  const desktopToken = localStorage.getItem('admin_token')
  if (desktopToken && !config.headers['X-Telegram-Init-Data']) {
    config.headers['Authorization'] = `Bearer ${desktopToken}`
  }

  return config
})

export default api

// API functions
export const fetchOverview = () => api.get('/overview').then((r) => r.data)
export const fetchSlips = (status = 'PENDING') => api.get(`/slips?status=${status}`).then((r) => r.data)
export const reviewSlip = (slipId: string, action: 'APPROVE' | 'REJECT', reason = '') =>
  api.post(`/slips/${slipId}/review`, { action, reason }).then((r) => r.data)

export const fetchKeys = (params?: { server_id?: string; search?: string; page?: number; page_size?: number }) =>
  api.get('/keys', { params }).then((r) => r.data)

export const createKey = (payload: { server_id: string; name: string; data_limit_gb?: number; valid_days?: number; assign_to_user_id?: string | number }) =>
  api.post('/keys', payload).then((r) => r.data)

export const extendKey = (keyId: string, addDays: number) =>
  api.post(`/keys/${keyId}/extend`, { add_days: addDays }).then((r) => r.data)

export const fetchRedeems = () => api.get('/redeems').then((r) => r.data)
export const createRedeemBatch = (payload: { amount_ks: number; mode: 'single' | 'shared'; valid_days: number; count: number }) =>
  api.post('/redeems/batch', payload).then((r) => r.data)

export const fetchCustomers = () => api.get('/customers').then((r) => r.data)
export const adjustBalance = (chatId: string, payload: { adjustment_type: 'TOPUP' | 'DEDUCT'; amount_ks: number; reason?: string }) =>
  api.post(`/customers/${chatId}/balance`, payload).then((r) => r.data)
