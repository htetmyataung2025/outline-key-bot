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
  return (
    window.Telegram?.WebApp?.initData ||
    (typeof localStorage !== 'undefined' ? localStorage.getItem('dev_init_data') || '' : '')
  )
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
  /** Check if running with real Telegram WebApp credentials or in local dev mode */
  hasAuth(): boolean {
    return Boolean(getTelegramInitData()) || Boolean(import.meta.env.DEV)
  },

  /** Consolidated user bootstrap */
  async getBootstrap(): Promise<BootstrapData> {
    return request<BootstrapData>('/api/user/bootstrap', { method: 'GET' })
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
    key_details: VpnKey
    remaining_balance: number
    message: string
  }> {
    return request('/api/user/purchase', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ plan_code: planCode, server_id: serverId }),
    })
  },

  /** Upload payment slip receipt screenshot for OCR verification */
  async uploadSlip(file: File, amount: number, method: 'kbz' | 'wave'): Promise<{
    success: boolean
    slip_id: string
    status: string
    amount: number
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
    period: string
    rows: LeaderboardRow[]
  }> {
    return request('/api/user/leaderboard', { method: 'GET' })
  },
}
