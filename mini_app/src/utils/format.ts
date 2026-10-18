import type { Member, TelegramUser, VpnKey } from '../types'

export const clamp = (value: number, min = 0, max = 100): number => Math.max(min, Math.min(max, value))
export const percentUsed = (key: Pick<VpnKey, 'used' | 'quota'>): number => key.quota > 0 ? clamp(Math.round(key.used / key.quota * 100)) : 0
export const formatNumber = (value: number): string => value.toLocaleString('en-US', { maximumFractionDigits: 2 })
export const twoDigits = (value: number): string => String(value).padStart(2, '0')
export function memberFromUser(user: TelegramUser): Member {
  const name = [user.first_name, user.last_name].filter(Boolean).join(' ').trim() || user.username || 'Member'
  return { name, id: String(user.id), initials: name.split(/\s+/).slice(0, 2).map(word => Array.from(word)[0] ?? '').join('').toUpperCase() || 'M' }
}
