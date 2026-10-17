import type { FluidPalette, Plan, Tab, TelegramUser, VpnKey } from '../types'

export const demoUser: TelegramUser = { first_name: 'Aung', last_name: 'Aung', id: 78429105 }
export const demoKeys: VpnKey[] = [
  { id: 'k1', server: 'Server 1', location: 'Singapore', country: 'SG', plan: 'VIP', quota: 150, used: 94.5, expires: '2026-11-05', left: '19 days left', status: 'expiring', connected: false, key: 'demo-vpn-key-vip-150gb' },
  { id: 'k2', server: 'Server 2', location: 'Tokyo', country: 'JP', plan: 'Basic', quota: 50, used: 14.5, expires: '2026-12-12', left: '56 days left', status: 'active', connected: true, key: 'demo-vpn-key-basic-50gb' },
  { id: 'k4', server: 'Server 4', location: 'Frankfurt', country: 'DE', plan: 'Starter', quota: 25, used: 22, expires: '2026-12-16', left: '60 days left', status: 'active', connected: false, key: 'demo-vpn-key-starter-25gb' },
  { id: 'k3', server: 'Server 3', location: 'Singapore', country: 'SG', plan: 'Starter', quota: 25, used: 25, expires: '2026-10-02', left: 'Expired', status: 'expired', connected: false, key: 'demo-vpn-key-expired' },
]
export const plans: Plan[] = [
  { name: 'Starter', quota: 25, description: 'စတင်သုံးစွဲရန်', icon: 'leaf', price: null },
  { name: 'Basic', quota: 50, description: 'အများဆုံးရွေးချယ်မှု', icon: 'zap', price: null },
  { name: 'VIP', quota: 150, description: 'Heavy user အတွက်', icon: 'crown', price: null },
]
export const tabs: Tab[] = [
  { id: 'overview', title: 'Overview', shortTitle: 'Overview', description: 'Wallet · active key · quick access', icon: 'home' },
  { id: 'keys', title: 'My Keys', shortTitle: 'My Keys', description: 'Key status · copy · connect · QR', icon: 'key' },
  { id: 'shop', title: 'Shop & Top-Up', shortTitle: 'Shop', description: 'Plans · payment · receipt upload', icon: 'bag' },
  { id: 'history', title: 'History & Rewards', shortTitle: 'Rewards', description: 'Orders · check-in · leaderboard', icon: 'history' },
]
export const palettes: readonly FluidPalette[] = [
  { accent: '#2aefbd', second: '#20d9f5', rgb: '42,239,189', top: '#087d86', bottom: '#073b53', bg: '#102a32' },
  { accent: '#b391ff', second: '#8572ff', rgb: '179,145,255', top: '#6840b3', bottom: '#32205f', bg: '#28203f' },
  { accent: '#43d9ff', second: '#688cff', rgb: '67,217,255', top: '#126d9f', bottom: '#133753', bg: '#14283d' },
]
export function paletteAt(index: number): FluidPalette { return palettes[index % palettes.length]! }
