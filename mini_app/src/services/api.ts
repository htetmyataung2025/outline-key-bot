import type { BootstrapData, LeaderboardRow, PurchaseRecord, SlipRecord, VpnKey } from '../types'

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || '').replace(/\/+$/, '')

export class ApiError extends Error {
  status: number
  data?: any
  constructor(message: string, status: number, data?: any) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export function getTelegramInitData(): string {
  if (typeof window === 'undefined') return ''
  try {
    return (
      window.Telegram?.WebApp?.initData ||
      (typeof localStorage !== 'undefined' ? localStorage.getItem('dev_init_data') || '' : '')
    )
  } catch {
    return window.Telegram?.WebApp?.initData || ''
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const url = `${BASE_URL}${path}`
  const headers = new Headers(options.headers || {})

  const initData = getTelegramInitData()
  if (initData) {
    headers.set('X-Telegram-Init-Data', initData)
  }

  const response = await fetch(url, {
    ...options,
    headers,
  })

  let json: any = null
  try {
    json = await response.json()
  } catch {
    json = null
  }

  if (!response.ok) {
    const errorMsg = json?.message || json?.error || `HTTP ${response.status}: Request failed`
    throw new ApiError(errorMsg, response.status, json)
  }

  return json as T
}

export const api = {
  /** Check if running with real Telegram WebApp credentials or in local dev/sandbox mode */
  hasAuth(): boolean {
    if (typeof window !== 'undefined' && window.location.port === '5000') {
      return true
    }
    return Boolean(getTelegramInitData()) || Boolean(import.meta.env.DEV)
  },

  /** Consolidated user bootstrap */
  async getBootstrap(refresh = false): Promise<BootstrapData> {
    const query = refresh ? '?refresh=1' : ''
    return request<BootstrapData>(`/api/user/bootstrap${query}`, { method: 'GET' })
  },

  /** Claim daily loyalty points reward */
  async claimReward(): Promise<{
    success: boolean
    awarded: number
    new_balance: number
    streak_days: number
    is_streak_bonus: boolean
    next_in_s: number
    cooldown_hours: number
    message: string
  }> {
    return request('/api/user/claim', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
  },

  /** 1-Click VPN Plan purchase using wallet balance */
  async purchasePlan(planCode: string, serverId: string = '1'): Promise<{
    success: boolean
    order_id: string
    vpn_key: string
    key_details?: VpnKey | null
    new_balance?: number
    remaining_balance: number
    manual?: boolean
    message: string
  }> {
    return request('/api/user/purchase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_code: planCode, server_id: serverId }),
    })
  },

  /** Redeem loyalty points for a Starter Plan key (25GB / 30 days) */
  async redeemPoints(): Promise<{
    success: boolean
    order_id: string
    vpn_key: string
    expire_date: string
    new_points: number
    key_details: VpnKey
    message: string
  }> {
    return request('/api/user/redeem-points', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
    })
  },

  /** Redeem promo / gift wallet balance code */
  async redeemCode(code: string): Promise<{
    success: boolean
    code?: string
    awarded_amount: number
    validity_days: number
    new_balance: number
    message: string
  }> {
    return request('/api/user/redeem-code', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ code }),
    })
  },

  /** Upload payment slip receipt screenshot for OCR verification */
  async uploadSlip(file: File, amount: number, method: 'kbz' | 'wave' | 'aya' | 'uab' | 'cb'): Promise<{
    success: boolean
    slip_id: string
    status: string
    amount: number
    method?: string
    submitted_at?: string
    message: string
  }> {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('amount', String(amount))
    formData.append('method', method)

    return request('/api/user/topup-slip', {
      method: 'POST',
      body: formData,
    })
  },

  /** Queue a replacement request for an active key */
  async replaceKey(keyId: string): Promise<{
    success: boolean
    order_id: string
    status: string
    message: string
  }> {
    return request(`/api/user/keys/${encodeURIComponent(keyId)}/replace`, {
      method: 'POST',
    })
  },

  /** User purchase and slip history */
  async getHistory(): Promise<{
    purchases: PurchaseRecord[]
    slips: SlipRecord[]
  }> {
    return request('/api/user/history', { method: 'GET' })
  },

  /** 7-day points leaderboard */
  async getLeaderboard(): Promise<{
    period?: string
    mode?: string
    rows: LeaderboardRow[]
    me?: { rank: number | null; name: string; points: number } | null
    total_players?: number
  }> {
    return request('/api/user/leaderboard', { method: 'GET' })
  },

  /** Request short-lived ticket for SSE stream */
  async getSseTicket(): Promise<string | null> {
    try {
      const res = await request<{ ticket: string }>('/api/user/events/ticket', { method: 'POST' })
      return res.ticket || null
    } catch {
      return null
    }
  },

  /** Build SSE EventSource URL with ticket */
  getEventsUrl(ticket: string): string {
    return `${BASE_URL}/api/user/events?ticket=${encodeURIComponent(ticket)}`
  },

  /** Lightweight data version check */
  async getVersion(): Promise<number> {
    try {
      const res = await request<{ version: number }>('/api/user/version', { method: 'GET' })
      return res.version || 0
    } catch {
      return 0
    }
  },
}
