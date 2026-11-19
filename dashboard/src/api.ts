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
  // Authenticated as a logged-in admin: shared secret + the Admin ID it was
  // issued to (minted by POST /login). The Mini App signs in the same way as
  // the desktop browser — no initData auto-login.
  const adminId = localStorage.getItem('admin_id')
  if (adminId) {
    config.headers['X-Admin-ID'] = adminId
  }
  const adminToken = localStorage.getItem('admin_token')
  if (adminToken) {
    config.headers['Authorization'] = `Bearer ${adminToken}`
  }
  return config
})

export default api

// ── Authentication ─────────────────────────────────────────────────────────
export const adminLogin = (adminId: string, password: string) =>
  api.post('/login', { admin_id: adminId, password }, { timeout: 8000 }).then((r) => r.data)

// API functions
// Overview probes live VPN servers on a cold cache, so give it a longer ceiling
// than the default 10s to avoid a spurious timeout on the first load.
export const fetchOverview = (force = false) =>
  api
    .get('/overview', { params: force ? { refresh: 1 } : {}, timeout: 20000 })
    .then((r) => r.data)
export const fetchSlips = (status = 'PENDING') => api.get(`/slips?status=${status}`).then((r) => r.data)
// Slip ids contain "#" (e.g. #AU27OA) — an unencoded "#" is treated as a URL
// fragment by the browser and truncates the path, so ids must be escaped.
export const reviewSlip = (slipId: string, action: 'APPROVE' | 'REJECT', reason = '') =>
  api.post(`/slips/${encodeURIComponent(slipId)}/review`, { action, reason }).then((r) => r.data)

// Live-refresh: cheap monotonic counter bumped server-side on every
// shared-state write (new slip, review, balance/key/settings change).
export const fetchDataVersion = () => api.get('/version', { timeout: 8000 }).then((r) => r.data.version as number)

// ── Push channel (SSE) ────────────────────────────────────────────────────
// EventSource cannot attach auth headers, so the stream authenticates with
// a one-time short-lived ticket exchanged over the normal authed channel.
export const createSseTicket = () => api.post('/sse-ticket', {}, { timeout: 8000 }).then((r) => r.data.ticket as string)

export interface VersionStreamHandlers {
  onVersion: (version: number) => void
  /** Connection state of the push channel (true = streaming). */
  onState: (up: boolean) => void
}

/**
 * Open the server-push version stream. Reconnects automatically with
 * backoff (each attempt needs a fresh one-time ticket). Returns a close()
 * that stops the stream and any pending reconnect.
 *
 * SSE holds a serverless function open for the whole stream duration, which
 * Vercel bills as provisioned memory-hours — the dashboard's biggest usage
 * item by far. Production builds therefore skip the stream entirely and the
 * caller falls back to the cheap version-poll; dev (localhost) keeps true
 * push. Set VITE_SSE_ENABLED=1 in a production build to re-enable.
 */
const sseEnabled = import.meta.env.DEV || import.meta.env.VITE_SSE_ENABLED === '1'

export function openVersionStream(handlers: VersionStreamHandlers): () => void {
  if (!sseEnabled) {
    // Report "no push channel" synchronously so the caller starts its poll.
    handlers.onState(false)
    return () => {}
  }
  let closed = false
  let source: EventSource | null = null
  let reconnectTimer: ReturnType<typeof setTimeout> | null = null
  let attempt = 0

  const backoffMs = () => Math.min(1500 * 2 ** Math.min(attempt, 3), 10000)

  async function connect() {
    if (closed) return
    let ticket: string
    try {
      ticket = await createSseTicket()
    } catch {
      if (!closed) {
        attempt += 1
        handlers.onState(false)
        reconnectTimer = setTimeout(connect, backoffMs())
      }
      return
    }
    if (closed) return

    source = new EventSource(`/api/admin/events?ticket=${encodeURIComponent(ticket)}`)
    source.onopen = () => {
      attempt = 0
      handlers.onState(true)
    }
    source.onmessage = (e) => {
      try {
        handlers.onVersion(JSON.parse(e.data).version)
      } catch {
        // Malformed frame — ignore, next event carries a full version.
      }
    }
    source.onerror = () => {
      source?.close()
      source = null
      handlers.onState(false)
      if (!closed) {
        attempt += 1
        reconnectTimer = setTimeout(connect, backoffMs())
      }
    }
  }

  connect()
  return () => {
    closed = true
    if (reconnectTimer) clearTimeout(reconnectTimer)
    source?.close()
  }
}

// Receipt images are stored as Telegram file_ids and proxied through the
// authenticated /image endpoint; <img> tags cannot send auth headers, so
// we fetch them as blobs and cache object URLs per slip id.
const slipImageCache = new Map<string, string>()
export async function fetchSlipImage(slipId: string): Promise<string> {
  const cached = slipImageCache.get(slipId)
  if (cached) return cached
  try {
    const r = await api.get(`/slips/${encodeURIComponent(slipId)}/image`, { responseType: 'blob', timeout: 20000 })
    const url = URL.createObjectURL(r.data)
    slipImageCache.set(slipId, url)
    return url
  } catch (e) {
    return ''
  }
}

export const fetchKeys = (params?: { server_id?: string; search?: string; page?: number; page_size?: number }) =>
  api.get('/keys', { params }).then((r) => r.data)

export const createKey = (payload: { server_id: string; name: string; data_limit_gb?: number; valid_days?: number; assign_to_user_id?: string | number }) =>
  api.post('/keys', payload).then((r) => r.data)

export const extendKey = (keyId: string, addDays: number, addGb: number = 0) =>
  api.post(`/keys/${keyId}/extend`, { add_days: addDays, add_gb: addGb }).then((r) => r.data)

export const deleteKey = (serverId: string | number, keyId: string | number) =>
  api.delete(`/keys/${serverId}/${keyId}`).then((r) => r.data)

export const deleteExpiredKeys = () =>
  api.post('/keys/delete-expired').then((r) => r.data)

export const fetchRedeems = () => api.get('/redeems').then((r) => r.data)
export const createRedeemBatch = (payload: { amount_ks: number; mode: 'single' | 'shared'; valid_days: number; count: number }) =>
  api.post('/redeems/batch', payload).then((r) => r.data)
export const deleteRedeem = (code: string) =>
  api.delete(`/redeems/${encodeURIComponent(code)}`).then((r) => r.data)
export const deleteRedeemsBulk = (codes: string[]) =>
  api.post('/redeems/delete', { codes }).then((r) => r.data)

export const fetchCustomers = () => api.get('/customers').then((r) => r.data)
export const fetchCustomerDetail = (chatId: string) =>
  api.get(`/customers/${encodeURIComponent(chatId)}`).then((r) => r.data)
// Unified purchase feed (merges sales_history + per-user purchase records).
export const fetchPurchases = (params?: { days?: number; server?: string; q?: string; limit?: number }) =>
  api.get('/purchases', { params }).then((r) => r.data)
export const adjustBalance = (chatId: string, payload: { adjustment_type: 'TOPUP' | 'DEDUCT'; amount_ks: number; reason?: string }) =>
  api.post(`/customers/${chatId}/balance`, payload).then((r) => r.data)
export const adjustPoints = (chatId: string, payload: { adjustment_type: 'GRANT' | 'DEDUCT'; amount: number; reason?: string }) =>
  api.post(`/customers/${chatId}/points`, payload).then((r) => r.data)

export const fetchSettings = () => api.get('/settings').then((r) => r.data)
export const updateSettings = (payload: any) => api.post('/settings', payload).then((r) => r.data)
export const testOutlineServer = (apiUrl: string) => api.post('/settings/test-server', { api_url: apiUrl }).then((r) => r.data)
// Configured Outline servers (id + name) — the only ones UI dropdowns may offer.
export const fetchServers = () => api.get('/servers').then((r) => r.data)

