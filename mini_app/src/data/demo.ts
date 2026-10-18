import type { FluidPalette, Plan, Tab } from '../types'

export const plans: Plan[] = [
  { name: 'Starter', quota: 25, description: 'စတင်သုံးစွဲရန်', icon: 'leaf', price: null },
  { name: 'Basic', quota: 50, description: 'အများဆုံးရွေးချယ်မှု', icon: 'zap', price: null },
  { name: 'VIP', quota: 150, description: 'Heavy user အတွက်', icon: 'crown', price: null },
]
export const tabs: Tab[] = [
  { id: 'overview', title: 'Overview', shortTitle: 'Overview', description: 'Wallet · active key · quick access', icon: 'home' },
  { id: 'keys', title: 'My Keys', shortTitle: 'My Keys', description: 'Key status · copy · connect', icon: 'key' },
  { id: 'shop', title: 'Shop & Top-Up', shortTitle: 'Shop', description: 'Plans · payment · receipt upload', icon: 'bag' },
  { id: 'history', title: 'History & Rewards', shortTitle: 'Rewards', description: 'Orders · check-in · leaderboard', icon: 'history' },
]
export const palettes: readonly FluidPalette[] = [
  { accent: '#2aefbd', second: '#20d9f5', rgb: '42,239,189', top: '#087d86', bottom: '#073b53', bg: '#102a32' },
  { accent: '#b391ff', second: '#8572ff', rgb: '179,145,255', top: '#6840b3', bottom: '#32205f', bg: '#28203f' },
  { accent: '#43d9ff', second: '#688cff', rgb: '67,217,255', top: '#126d9f', bottom: '#133753', bg: '#14283d' },
]
export function paletteAt(index: number): FluidPalette { return palettes[index % palettes.length]! }
