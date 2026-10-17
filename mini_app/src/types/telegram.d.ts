import type { TelegramUser, VpnKey } from './index'

export interface TelegramWebApp {
  initDataUnsafe?: { user?: TelegramUser }
  isVerticalSwipesEnabled?: boolean
  disableVerticalSwipes?: () => void
  enableVerticalSwipes?: () => void
}
export interface TunnelBridge {
  updateKeyUsage: (id: string, usedGB: number) => boolean
  setUser: (user: TelegramUser) => void
  setKeys: (keys: VpnKey[]) => void
}
declare global {
  interface Window {
    Telegram?: { WebApp?: TelegramWebApp }
    TunnelUI?: TunnelBridge
  }
  interface WindowEventMap {
    'tunnel:usage': CustomEvent<{ id: string; usedGB: number }>
  }
}
