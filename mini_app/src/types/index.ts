import type { IconName } from './icons'

export type TabId = 'overview' | 'keys' | 'shop' | 'history'
export type KeyStatus = 'active' | 'expiring' | 'expired'
export type KeyFilter = 'all' | KeyStatus
export type PlanName = 'Starter' | 'Basic' | 'VIP'
export type PaymentMethod = 'kbz' | 'wave'
export type TopUpAmount = number | 'custom'
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
}
export interface Plan { name: PlanName; quota: number; description: string; icon: IconName; price: number | null }
export interface TelegramUser { id: number | string; first_name?: string; last_name?: string; username?: string }
export interface Member { name: string; id: string; initials: string }
export interface Receipt { name: string; url: string; file: File }
export interface Tab { id: TabId; title: string; shortTitle: string; description: string; icon: IconName }
export type AppDialog =
  | { kind: 'usage'; keyId: string }
  | { kind: 'connect'; keyId: string }
  | { kind: 'replace'; keyId: string }
  | { kind: 'key-qr'; keyId: string }
  | { kind: 'purchase'; plan: PlanName }
  | { kind: 'payment'; method: PaymentMethod; amount: number }
  | { kind: 'manual-copy'; value: string }
  | { kind: 'profile' }
  | { kind: 'leaderboard' }
  | { kind: 'history' }
export interface Toast { message: string; icon: IconName; visible: boolean }
export interface FluidPalette { accent: string; second: string; rgb: string; top: string; bottom: string; bg: string }
