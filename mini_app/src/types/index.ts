import type { IconName } from './icons'

export type TabId = 'overview' | 'keys' | 'shop' | 'history'
export type KeyStatus = 'active' | 'expiring' | 'expired'
export type KeyFilter = 'all' | KeyStatus
export type PlanName = 'Starter' | 'Basic' | 'VIP' | string
export type PaymentMethod = 'kbz' | 'wave' | 'aya' | 'uab' | 'cb'
export type VpnAppId = 'outline' | 'v2box' | 'incy'
export type TopUpAmount = number | 'custom'
export interface LeaderboardMe {
  rank: number | null
  name: string
  points: number
}
export interface VpnKey {
  id: string
  server: string
  location: string
  country: string
  plan: PlanName
  quota: number
  used: number
  expires: string
  left: string
  status: KeyStatus
  connected: boolean
  key: string
  go_url?: string
}
export interface Plan {
  name: PlanName
  quota: number
  description: string
  icon: IconName
  price: number | null
  code?: string
  quotaLabel?: string
  manual?: boolean
  months?: number
}
export interface TelegramUser { id: number | string; first_name?: string; last_name?: string; username?: string }
export interface Member { name: string; id: string; initials: string }
export interface Receipt { name: string; url: string; file: File }
export interface Tab { id: TabId; title: string; shortTitle: string; description: string; icon: IconName }

export interface ServerOption {
  id: string
  name: string
  location: string
  country: string
  flag: string
}

export interface PaymentMethodInfo {
  name: string
  account_name: string
  phone: string
  type: string
}

export interface PurchaseRecord {
  order_id: string
  plan_name: string
  disp_gb?: string
  price?: string
  date?: string
  status?: string
}

export interface SlipRecord {
  slip_id?: string
  amount: number
  method: string
  status: string
  submitted_at?: string
}

export interface LeaderboardRow {
  rank: number
  name: string
  points: number
  is_you: boolean
}

export interface BootstrapData {
  user: {
    id: string
    name: string
    username?: string
    initials: string
  }
  wallet: {
    balance: number
    main_balance: number
    bonus_balance: number
    points: number
    claimed_today: boolean
    can_claim: boolean
    streak_days: number
    cooldown_remaining: number
    cooldown_hours: number
    starter_cost?: number
    has_topped_up?: boolean
    can_redeem_points?: boolean
  }
  keys: VpnKey[]
  plans: Array<{
    code: string
    name: PlanName
    quota: string
    price: number
    description: string
    symbol: string
    manual?: boolean
    months?: number
  }>
  servers: ServerOption[]
  payment_methods: Record<string, PaymentMethodInfo>
}

export type AppDialog =
  | { kind: 'usage'; keyId: string }
  | { kind: 'connect'; keyId: string }
  | { kind: 'replace'; keyId: string }
  | { kind: 'key-qr'; keyId: string }
  | { kind: 'purchase'; plan: PlanName }
  | { kind: 'payment'; method: PaymentMethod; amount: number }
  | {
      kind: 'claim-reward'
      status: 'loading' | 'success'
      awarded?: number
      newBalance?: number
      streakDays?: number
      isStreakBonus?: boolean
      cooldownHours?: number
      message?: string
    }
  | { kind: 'manual-copy'; value: string }
  | { kind: 'profile' }
  | { kind: 'leaderboard' }
  | { kind: 'history' }
export interface Toast { message: string; icon: IconName; visible: boolean }
export interface FluidPalette { accent: string; second: string; rgb: string; top: string; bottom: string; bg: string }
